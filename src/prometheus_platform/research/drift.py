"""Estadísticos de drift (CRISP-ML(Q) F6, PQ-86): datos y calibración del modelo.

Funciones puras sobre arrays. Los umbrales están aquí y en ``docs/runbooks/drift.md``: si uno
cambia, cambian los dos en el mismo PR.

- **Datos:** PSI (*population stability index*) del funding anualizado en vivo frente al
  desarrollo, con los deciles del desarrollo como tramos. Convención habitual en riesgo de crédito:
  < 0,10 estable, 0,10-0,25 cambio moderado, ≥ 0,25 cambio grande (alerta). El KS de dos muestras
  acompaña como contraste formal, pero no decide: con cientos de liquidaciones casi cualquier
  diferencia es «significativa», mientras que el PSI mide el tamaño del cambio.
- **Modelo:** calibración del clasificador «¿la siguiente tasa superará el 20 %?» con el error de
  calibración esperado (ECE, 10 tramos de probabilidad). Alerta si ECE ≥ 0,10: el modelo dice
  «80 %» y pasa bastante menos (o más). El Brier y el AUC acompañan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import ks_2samp
from sklearn.metrics import roc_auc_score

FloatArray = np.ndarray

PSI_ALERT = 0.25
PSI_WARN = 0.10
ECE_ALERT = 0.10
MIN_LIVE = 30  # menos observaciones en vivo no dicen nada
PSI_BINS = 10
CALIBRATION_BINS = 10
SMOOTHING = 0.5  # se suma a cada conteo (Jeffreys): un tramo vacío no da log(0) ni un PSI infinito


def population_stability(reference: FloatArray, live: FloatArray, bins: int = PSI_BINS) -> float:
    """PSI de ``live`` frente a ``reference``, con los cuantiles de ``reference`` como tramos."""
    ref = np.asarray(reference, dtype=np.float64)
    cur = np.asarray(live, dtype=np.float64)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    n_bins = edges.size - 1  # con muchos empates (funding en la tasa base) quedan menos tramos
    expected = (np.histogram(ref, edges)[0] + SMOOTHING) / (ref.size + SMOOTHING * n_bins)
    actual = (np.histogram(cur, edges)[0] + SMOOTHING) / (cur.size + SMOOTHING * n_bins)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


@dataclass(frozen=True)
class DataDrift:
    symbol: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    reference_median: float
    live_median: float
    n_reference: int
    n_live: int

    @property
    def alert(self) -> bool:
        return self.psi >= PSI_ALERT

    @property
    def level(self) -> str:
        if self.alert:
            return "cambio grande"
        return "cambio moderado" if self.psi >= PSI_WARN else "estable"


def data_drift(symbol: str, reference: FloatArray, live: FloatArray) -> DataDrift:
    ref = np.asarray(reference, dtype=np.float64)
    cur = np.asarray(live, dtype=np.float64)
    if cur.size < MIN_LIVE:
        raise ValueError(f"{symbol}: hacen falta al menos {MIN_LIVE} liquidaciones en vivo")
    ks = ks_2samp(ref, cur)
    return DataDrift(
        symbol=symbol,
        psi=population_stability(ref, cur),
        ks_statistic=float(ks.statistic),
        ks_pvalue=float(ks.pvalue),
        reference_median=float(np.median(ref)),
        live_median=float(np.median(cur)),
        n_reference=int(ref.size),
        n_live=int(cur.size),
    )


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    count: int
    mean_probability: float
    observed_rate: float


@dataclass(frozen=True)
class Calibration:
    ece: float
    brier: float
    auc: float | None  # None si en vivo solo hubo una clase
    positive_rate: float
    n: int
    bins: tuple[CalibrationBin, ...]

    @property
    def alert(self) -> bool:
        return self.ece >= ECE_ALERT


def calibration(
    labels: FloatArray, probs: FloatArray, n_bins: int = CALIBRATION_BINS
) -> Calibration:
    """ECE (media ponderada de |probabilidad media - frecuencia observada| por tramo) y Brier."""
    y = np.asarray(labels, dtype=bool)
    p = np.asarray(probs, dtype=np.float64)
    edges = np.linspace(0, 1, n_bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    bins, ece = [], 0.0
    for b in range(n_bins):
        mask = which == b
        if not mask.any():
            continue
        mean_p, rate = float(p[mask].mean()), float(y[mask].mean())
        ece += mask.sum() / p.size * abs(mean_p - rate)
        bins.append(CalibrationBin(edges[b], edges[b + 1], int(mask.sum()), mean_p, rate))
    auc = float(roc_auc_score(y, p)) if 0 < y.sum() < y.size else None
    return Calibration(
        ece=float(ece),
        brier=float(np.mean((p - y) ** 2)),
        auc=auc,
        positive_rate=float(y.mean()),
        n=int(y.size),
        bins=tuple(bins),
    )
