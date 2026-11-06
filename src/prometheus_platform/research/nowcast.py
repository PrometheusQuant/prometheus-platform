"""«¿Qué predice hoy?»: el clasificador del capítulo 5 aplicado a los datos más recientes (PQ-58).

- **Entrenamiento:** solo el periodo de desarrollo, con el mismo preprocesado del estudio (winsor
  1-99 % con los límites del entrenamiento) y los hiperparámetros que eligió GridSearch
  (``data/research/funding_model/residual/summary.json``). No se reentrena con datos posteriores.
- **Predicción:** la última liquidación de cada símbolo. **Solo** si es posterior al fin del
  holdout: mostrar predicciones sobre fechas del holdout sería mirarlo. Con datos viejos se pide la
  ingesta de la API (PQ-65) en lugar de predecir.
- **Explicación:** importancia de las variables del bosque (impureza). La explicación por
  predicción (SHAP o permutación) es PQ-74.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestClassifier

from prometheus_platform.domain.protocol import HOLDOUT_END
from prometheus_platform.research import carry_evaluation as ce
from prometheus_platform.research.funding_model import (
    FEATURES,
    SEED,
    THRESHOLD,
    WINSOR,
    prepare,
)
from prometheus_platform.research.panel import development_only

MODEL_NAME = "random_forest"


class StaleDataError(ValueError):
    """Los datos más recientes no pasan del fin del holdout: no se predice."""


@dataclass(frozen=True)
class Nowcast:
    symbol: str
    funding_time: datetime
    annualized_now: float
    probability_high: float

    @property
    def regime(self) -> str:
        return "alto (≥ 20 %)" if self.probability_high >= 0.5 else "normal o bajo"


@dataclass(frozen=True)
class TrainedModel:
    model: RandomForestClassifier
    low: np.ndarray
    high: np.ndarray
    params: dict[str, int]


@dataclass(frozen=True)
class Forecast:
    rows: list[Nowcast]
    importance: list[tuple[str, float]]
    params: dict[str, int]


def tuned_params(data_dir: Path) -> dict[str, int]:
    """Hiperparámetros del bosque ajustado en el estudio. Sin artefacto no se adivina."""
    path = data_dir / "research" / "funding_model" / "residual" / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    for entry in summary.get("classification", []):
        if entry.get("name") == MODEL_NAME and entry.get("tuned"):
            return {k: int(v) for k, v in entry["best_params"].items()}
    raise ValueError(f"{path}: no hay un {MODEL_NAME} ajustado")


def _symbols() -> list[str]:
    return [s for group in ce.HYPOTHESES.values() for s in group]


def development_panel(data_dir: Path) -> pl.DataFrame:
    return pl.concat(
        [development_only(ce.load_symbol(data_dir / "silver", s).settlements) for s in _symbols()],
        how="diagonal_relaxed",
    )


def latest_rows(data_dir: Path) -> pl.DataFrame:
    """Última liquidación completa (todas las variables) de cada símbolo."""
    rows = []
    for symbol in _symbols():
        panel = ce.load_symbol(data_dir / "silver", symbol).settlements
        last = panel.drop_nulls(list(FEATURES)).sort("funding_time").tail(1)
        rows.append(last.with_columns(pl.lit(symbol).alias("symbol")))
    return pl.concat(rows, how="diagonal_relaxed")


def train(panel: pl.DataFrame, params: dict[str, int]) -> TrainedModel:
    x, y, _ = prepare(panel)
    lo, hi = np.quantile(x, WINSOR[0], axis=0), np.quantile(x, WINSOR[1], axis=0)
    model = RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=-1, **params)
    model.fit(np.clip(x, lo, hi), y >= THRESHOLD)
    return TrainedModel(model, lo, hi, params)


def forecast(trained: TrainedModel, latest: pl.DataFrame) -> Forecast:
    newest = latest["funding_time"].max()
    if not isinstance(newest, datetime) or newest <= HOLDOUT_END:
        raise StaleDataError(
            f"el dato más reciente ({newest!s:.10}) no pasa del fin del holdout"
            f" ({HOLDOUT_END:%Y-%m-%d})"
        )
    fresh = latest.filter(pl.col("funding_time") > HOLDOUT_END)
    model = trained.model
    x = np.clip(fresh.select(FEATURES).cast(pl.Float64).to_numpy(), trained.low, trained.high)
    probs = model.predict_proba(x)[:, list(model.classes_).index(True)]
    rows = [
        Nowcast(symbol, at, float(now), float(p))
        for symbol, at, now, p in zip(
            fresh["symbol"], fresh["funding_time"], fresh["annualized"], probs, strict=True
        )
    ]
    ranked = sorted(zip(FEATURES, model.feature_importances_, strict=True), key=lambda kv: -kv[1])
    return Forecast(rows, [(name, float(v)) for name, v in ranked], trained.params)
