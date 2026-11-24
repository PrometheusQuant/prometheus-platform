"""Explicabilidad del clasificador del capítulo 5 (PQ-74).

Dos preguntas, dos herramientas:

1. **¿Qué variables importan al modelo?** Importancia por permutación (scikit-learn), calculada
   **en los pliegues de validación** del walk-forward del desarrollo, nunca sobre el
   entrenamiento. Se reentrena el bosque en cada pliegue con los hiperparámetros ya elegidos por
   GridSearch. No se elige nada, así que no es un ensayo y no suma a N. Si al barajar una variable
   cae el AUC fuera de muestra, el modelo depende de verdad de ella.
2. **¿Por qué predice esto hoy?** Atribución local por sustitución: para cada variable se calcula
   cuánto cambia la probabilidad si esa variable tuviera su valor *típico* (la mediana del
   desarrollo) y el resto quedara igual. Se lee así: «con un valor habitual del funding actual,
   la probabilidad bajaría al 18 %».

**Por qué no SHAP.** Arrastra `numba` y `llvmlite`, con ruedas frágiles en ARM (la VM Ampere de
PQ-56), para responder lo mismo. La permutación viene en scikit-learn y la sustitución se explica
en una frase.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import TimeSeriesSplit

from prometheus_platform.research.funding_model import FEATURES, SEED, THRESHOLD, WINSOR, prepare

FloatArray = npt.NDArray[np.float64]

# Nombres para personas no técnicas (el dashboard no muestra nombres de columnas).
LABELS = {
    "annualized": "funding actual (anualizado)",
    "s_3": "media de las 3 últimas liquidaciones",
    "s_9": "media de las 9 últimas liquidaciones",
    "s_21": "media de las 21 últimas liquidaciones",
    "annualized_lag1": "funding de la liquidación anterior",
    "annualized_lag2": "funding de hace 2 liquidaciones",
    "annualized_lag3": "funding de hace 3 liquidaciones",
    "annualized_std_21": "variabilidad reciente del funding",
    "basis": "diferencia entre el perpetuo y el spot (basis)",
    "basis_change_3": "cambio reciente del basis",
    "spot_return_24h": "retorno del precio en 24 h",
    "spot_vol_7d": "volatilidad del precio en 7 días",
    "funding_interval_hours": "intervalo entre liquidaciones",
}


def label(feature: str) -> str:
    return LABELS.get(feature, feature)


@dataclass(frozen=True, slots=True)
class FeatureImportance:
    feature: str
    mean: float  # caída media del AUC de validación al barajar la variable
    std: float  # dispersión entre pliegues y repeticiones

    @property
    def label(self) -> str:
        return label(self.feature)


def validation_importance(
    panel: pl.DataFrame,
    params: dict[str, Any],
    *,
    n_folds: int = 5,
    gap: int = 15,
    n_repeats: int = 5,
) -> list[FeatureImportance]:
    """Importancia por permutación sobre los pliegues de validación, de mayor a menor."""
    x, y, _ = prepare(panel)
    labels = y >= THRESHOLD
    drops: list[FloatArray] = []
    for train, test in TimeSeriesSplit(n_splits=n_folds, gap=gap).split(x):
        if len(set(labels[test])) < 2 or len(set(labels[train])) < 2:
            continue  # sin las dos clases el AUC no está definido
        lo, hi = np.quantile(x[train], WINSOR[0], axis=0), np.quantile(x[train], WINSOR[1], axis=0)
        model = RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=-1, **params)
        model.fit(np.clip(x[train], lo, hi), labels[train])
        result = permutation_importance(
            model,
            np.clip(x[test], lo, hi),
            labels[test],
            scoring="roc_auc",
            n_repeats=n_repeats,
            random_state=SEED,
            n_jobs=-1,
        )
        drops.append(
            np.asarray(result["importances"], dtype=np.float64)
        )  # (variables, repeticiones)
    if not drops:
        raise ValueError("Ningún pliegue de validación tiene las dos clases")
    stacked = np.concatenate(drops, axis=1)
    ranked = [
        FeatureImportance(name, float(stacked[i].mean()), float(stacked[i].std()))
        for i, name in enumerate(FEATURES)
    ]
    return sorted(ranked, key=lambda imp: -imp.mean)


@dataclass(frozen=True, slots=True)
class Contribution:
    feature: str
    value: float  # valor de hoy
    typical: float  # mediana del desarrollo
    delta: float  # probabilidad de hoy menos la probabilidad con el valor típico

    @property
    def label(self) -> str:
        return label(self.feature)


def local_contributions(
    model: RandomForestClassifier, row: FloatArray, reference: FloatArray
) -> list[Contribution]:
    """Cuánto aporta cada variable a la probabilidad de hoy frente a su valor típico."""
    positive = list(model.classes_).index(True)
    base = float(model.predict_proba(row[None, :])[0, positive])
    variants = np.repeat(row[None, :], len(FEATURES), axis=0)
    variants[np.arange(len(FEATURES)), np.arange(len(FEATURES))] = reference
    probs = model.predict_proba(variants)[:, positive]
    contributions = [
        Contribution(name, float(row[i]), float(reference[i]), base - float(probs[i]))
        for i, name in enumerate(FEATURES)
    ]
    return sorted(contributions, key=lambda c: -abs(c.delta))


def _pct(value: float) -> str:
    """Porcentaje con espacio, como se escribe en español: «90 %»."""
    return f"{value * 100:.0f} %"


def explain_in_words(
    symbol: str, probability: float, contributions: Sequence[Contribution], top: int = 2
) -> str:
    """Una frase para una persona no técnica, con las variables que más mueven la predicción."""
    relevant = [c for c in contributions[:top] if abs(c.delta) >= 0.01]
    if not relevant:
        return (
            f"{symbol}: probabilidad de funding alto del {_pct(probability)}. Ninguna variable se "
            "aleja lo suficiente de lo habitual como para mover la predicción."
        )
    parts = [
        f"con un valor habitual de «{c.label}», la probabilidad "
        f"{'bajaría' if c.delta > 0 else 'subiría'} al {_pct(probability - c.delta)}"
        for c in relevant
    ]
    return (
        f"{symbol}: probabilidad de funding alto del {_pct(probability)}; " + "; ".join(parts) + "."
    )
