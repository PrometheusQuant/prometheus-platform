"""Modelo predictivo del funding (PQ-32, capítulo 5).

Pregunta: ¿predice un modelo de ML el funding de la **próxima** liquidación mejor que los
baselines ingenuos? Si no, el pre-registro del carry se queda con su señal simple (``S_k``).

- **Regresión:** objetivo = tasa anualizada siguiente. Baselines: persistencia (la tasa actual) y
  media ``S_9``. Modelos: Ridge, Random Forest y Gradient Boosting (``HistGradientBoosting``).
- **Clasificación:** ¿la siguiente tasa superará θ = 20 %? Baseline: la regla ``S_9 ≥ θ``.
  Modelos: regresión logística, Random Forest y Gradient Boosting.
- **Validación:** walk-forward temporal (``TimeSeriesSplit`` con hueco) **solo en el periodo de
  desarrollo**. GridSearch anidado: cada pliegue ajusta hiperparámetros solo con su pasado.
- **Colas:** las features y el objetivo de entrenamiento se winsorizan con los cuantiles del pliegue
  de entrenamiento (sin fuga). Las métricas se calculan sobre el objetivo real.
- **Dos formulaciones** (``target_mode``): ``"level"`` predice la tasa siguiente directamente (v1);
  ``"residual"`` predice el cambio sobre la persistencia y suma la tasa actual (v2). Con colas
  extremas, la v1 no puede reproducir los valores atípicos que la persistencia sí arrastra.
- **Significancia:** test de Diebold-Mariano del mejor modelo frente a la persistencia.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any

import numpy as np
import polars as pl
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = (
    "annualized",
    "s_3",
    "s_9",
    "s_21",
    "annualized_lag1",
    "annualized_lag2",
    "annualized_lag3",
    "annualized_std_21",
    "basis",
    "basis_change_3",
    "spot_return_24h",
    "spot_vol_7d",
    "funding_interval_hours",
)
TARGET = "target_next_annualized"
THRESHOLD = 0.20
SEED = 42
WINSOR = (0.01, 0.99)

FloatArray = np.ndarray


@dataclass(frozen=True)
class ModelSpec:
    name: str
    factory: Callable[[], BaseEstimator]
    grid: dict[str, list[Any]]
    justification: str


def regression_specs() -> list[ModelSpec]:
    return [
        ModelSpec(
            "ridge",
            lambda: make_pipeline(StandardScaler(), Ridge()),
            {"ridge__alpha": [0.1, 1.0, 10.0, 100.0]},
            "Lineal regularizado: interpretable, difícil de sobreajustar; captura la persistencia.",
        ),
        ModelSpec(
            "random_forest",
            lambda: RandomForestRegressor(n_estimators=100, random_state=SEED, n_jobs=-1),
            {"max_depth": [4, 8], "min_samples_leaf": [20, 100]},
            "No lineal y robusto a colas pesadas y escalas distintas (basis vs. tasas).",
        ),
        ModelSpec(
            "gradient_boosting",
            lambda: HistGradientBoostingRegressor(random_state=SEED),
            {"learning_rate": [0.03, 0.1], "max_depth": [3, None], "l2_regularization": [0.0, 1.0]},
            "Estado del arte en datos tabulares (Gu, Kelly y Xiu, 2020); maneja nulos.",
        ),
    ]


def classification_specs() -> list[ModelSpec]:
    return [
        ModelSpec(
            "logistic",
            lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
            {"logisticregression__C": [0.01, 0.1, 1.0, 10.0]},
            "Baseline probabilístico lineal y calibrado.",
        ),
        ModelSpec(
            "random_forest",
            lambda: RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=-1),
            {"max_depth": [4, 8], "min_samples_leaf": [20, 100]},
            "No lineal y robusto a colas pesadas.",
        ),
        ModelSpec(
            "gradient_boosting",
            lambda: HistGradientBoostingClassifier(random_state=SEED),
            {"learning_rate": [0.03, 0.1], "max_depth": [3, None]},
            "Estado del arte en datos tabulares.",
        ),
    ]


@dataclass
class RegressionResult:
    name: str
    tuned: bool
    rmse: float
    mae: float
    r2: float
    best_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    name: str
    tuned: bool
    auc: float
    f1: float
    confusion: list[list[int]]
    best_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelStudy:
    rows: int
    folds: int
    regression: list[RegressionResult]
    classification: list[ClassificationResult]
    diebold_mariano: dict[str, float | str]
    justification: dict[str, str]
    roc_points: dict[str, tuple[list[float], list[float]]] = field(default_factory=dict)


def prepare(panel: pl.DataFrame) -> tuple[FloatArray, FloatArray, pl.DataFrame]:
    """Matriz X, objetivo y y el panel ordenado por tiempo, sin filas incompletas."""
    clean = panel.drop_nulls([*FEATURES, TARGET]).sort("funding_time")
    x = clean.select(FEATURES).cast(pl.Float64).to_numpy()
    y = clean[TARGET].cast(pl.Float64).to_numpy()
    return x, y, clean


def _winsor_bounds(values: FloatArray) -> tuple[FloatArray, FloatArray]:
    return np.quantile(values, WINSOR[0], axis=0), np.quantile(values, WINSOR[1], axis=0)


def _metrics(y: FloatArray, pred: FloatArray) -> tuple[float, float, float]:
    err = y - pred
    rmse = float(np.sqrt(np.mean(err**2)))
    mae = float(np.mean(np.abs(err)))
    r2 = 1 - float(np.sum(err**2) / np.sum((y - y.mean()) ** 2))
    return rmse, mae, r2


def diebold_mariano(
    errors_model: FloatArray, errors_baseline: FloatArray
) -> dict[str, float | str]:
    """DM con pérdida cuadrática y horizonte 1 (Diebold y Mariano, 1995). DM < 0: gana el modelo."""
    d = errors_model**2 - errors_baseline**2
    stat = float(d.mean() / (d.std(ddof=1) / math.sqrt(d.size)))
    p_value = 2 * (1 - NormalDist().cdf(abs(stat)))
    return {"dm": stat, "p_value": p_value}


def run_study(  # noqa: PLR0913, PLR0915 - guion completo del experimento; keyword-only
    panel: pl.DataFrame,
    *,
    n_folds: int = 5,
    gap: int = 15,
    regression: list[ModelSpec] | None = None,
    classification: list[ModelSpec] | None = None,
    target_mode: str = "residual",
) -> ModelStudy:
    if target_mode not in ("level", "residual"):
        raise ValueError(f"target_mode inválido: {target_mode!r}")
    x, y, _ = prepare(panel)
    reg_specs = regression if regression is not None else regression_specs()
    clf_specs = classification if classification is not None else classification_specs()
    outer = TimeSeriesSplit(n_splits=n_folds, gap=gap)
    inner = TimeSeriesSplit(n_splits=3, gap=gap)
    idx = {name: FEATURES.index(name) for name in ("annualized", "s_9")}

    oos_idx: list[FloatArray] = []
    preds: dict[str, list[FloatArray]] = {}
    probs: dict[str, list[FloatArray]] = {}
    params: dict[str, list[dict[str, Any]]] = {}

    def keep(store: dict[str, list[FloatArray]], key: str, value: FloatArray) -> None:
        store.setdefault(key, []).append(value)

    for train, test in outer.split(x):
        oos_idx.append(test)
        lo, hi = _winsor_bounds(x[train])
        x_train, x_test = np.clip(x[train], lo, hi), np.clip(x[test], lo, hi)
        base_train = x[train, idx["annualized"]] if target_mode == "residual" else 0.0
        base_test = x[test, idx["annualized"]] if target_mode == "residual" else 0.0
        y_lo, y_hi = np.quantile(y[train] - base_train, WINSOR)
        y_train = np.clip(y[train] - base_train, y_lo, y_hi)
        label_train = y[train] >= THRESHOLD

        keep(preds, "persistencia", x[test, idx["annualized"]])
        keep(preds, "media_s9", x[test, idx["s_9"]])
        keep(probs, "regla_s9", (x[test, idx["s_9"]] >= THRESHOLD).astype(float))
        for spec in reg_specs:
            default = clone(spec.factory()).fit(x_train, y_train)
            keep(preds, f"{spec.name}:default", base_test + default.predict(x_test))
            search = GridSearchCV(
                spec.factory(), spec.grid, cv=inner, scoring="neg_root_mean_squared_error"
            )
            search.fit(x_train, y_train)
            keep(preds, f"{spec.name}:tuned", base_test + search.predict(x_test))
            params.setdefault(f"reg:{spec.name}", []).append(search.best_params_)
        for spec in clf_specs:
            default = clone(spec.factory()).fit(x_train, label_train)
            keep(probs, f"{spec.name}:default", default.predict_proba(x_test)[:, 1])
            search = GridSearchCV(spec.factory(), spec.grid, cv=inner, scoring="roc_auc")
            search.fit(x_train, label_train)
            keep(probs, f"{spec.name}:tuned", search.predict_proba(x_test)[:, 1])
            params.setdefault(f"clf:{spec.name}", []).append(search.best_params_)

    test_idx = np.concatenate(oos_idx)
    y_oos = y[test_idx]
    label_oos = y_oos >= THRESHOLD

    reg_results = []
    for key, chunks in preds.items():
        rmse, mae, r2 = _metrics(y_oos, np.concatenate(chunks))
        name, _, mode = key.partition(":")
        reg_results.append(
            RegressionResult(
                name, mode == "tuned", rmse, mae, r2, _last(params, f"reg:{name}", mode)
            )
        )
    clf_results, roc_points = [], {}
    for key, chunks in probs.items():
        prob = np.concatenate(chunks)
        name, _, mode = key.partition(":")
        predicted = prob >= 0.5
        clf_results.append(
            ClassificationResult(
                name,
                mode == "tuned",
                float(roc_auc_score(label_oos, prob)),
                float(f1_score(label_oos, predicted)),
                confusion_matrix(label_oos, predicted, labels=[False, True]).tolist(),
                _last(params, f"clf:{name}", mode),
            )
        )
        roc_points[key] = _roc(label_oos, prob)

    learned = [r for r in reg_results if r.name not in ("persistencia", "media_s9")]
    best = min(learned, key=lambda r: r.rmse)
    best_key = f"{best.name}:{'tuned' if best.tuned else 'default'}"
    dm = diebold_mariano(
        y_oos - np.concatenate(preds[best_key]), y_oos - np.concatenate(preds["persistencia"])
    )
    dm["best_model"] = best_key
    dm["target_mode"] = target_mode
    return ModelStudy(
        rows=int(y.size),
        folds=n_folds,
        regression=sorted(reg_results, key=lambda r: r.rmse),
        classification=sorted(clf_results, key=lambda r: -r.auc),
        diebold_mariano=dm,
        justification={s.name: s.justification for s in [*reg_specs, *clf_specs]},
        roc_points=roc_points,
    )


def _last(params: dict[str, list[dict[str, Any]]], key: str, mode: str) -> dict[str, Any]:
    return params[key][-1] if mode == "tuned" and key in params else {}


def _roc(labels: FloatArray, prob: FloatArray) -> tuple[list[float], list[float]]:
    from sklearn.metrics import roc_curve  # noqa: PLC0415

    fpr, tpr, _ = roc_curve(labels, prob)
    step = max(len(fpr) // 200, 1)
    return fpr[::step].tolist(), tpr[::step].tolist()
