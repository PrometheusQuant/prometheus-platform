"""Métricas de rendimiento y protocolo anti-sobreajuste (PQ-25).

- ``performance``: Sharpe anualizado (√365), CAGR, drawdown máximo, Calmar, t-estadístico.
- ``cpcv_splits``: validación cruzada combinatoria purgada (López de Prado, 2018, cap. 12), con
  *purge* alrededor de cada bloque de prueba y embargo posterior.
- ``probability_of_backtest_overfitting``: PBO con CSCV (Bailey, Borwein, López de Prado y
  Zhu, 2017).
- ``deflated_sharpe_ratio``: DSR (Bailey y López de Prado, 2014). Corrige el Sharpe por el número
  de ensayos N, la asimetría y la curtosis.

Solo usa la librería estándar y numpy: cada fórmula se puede revisar contra el paper.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
from numpy.typing import NDArray

DAYS_PER_YEAR = 365
EULER_MASCHERONI = 0.5772156649015329
_NORMAL = NormalDist()
_FLAT = 1e-12  # desviación por debajo de la cual una serie se considera constante

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Performance:
    sharpe: float  # anualizado
    sharpe_daily: float
    cagr: float
    max_drawdown: float
    calmar: float
    t_stat: float
    skew: float
    kurtosis: float  # no excesiva: 3 para la normal
    days: int


def sharpe_daily(returns: FloatArray) -> float:
    sd = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    return float(np.mean(returns)) / sd if sd > _FLAT else 0.0


def performance(returns: FloatArray) -> Performance:
    """Métricas sobre retornos diarios netos (pre-registro §8)."""
    n = int(returns.size)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 días de retornos")
    sr = sharpe_daily(returns)
    equity = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.min(equity / peak - 1))
    years = n / DAYS_PER_YEAR
    cagr = float(equity[-1] ** (1 / years) - 1)
    sd = float(np.std(returns, ddof=1))
    centered = returns - np.mean(returns)
    skew = float(np.mean(centered**3) / sd**3) if sd > _FLAT else 0.0
    kurt = float(np.mean(centered**4) / sd**4) if sd > _FLAT else 3.0
    return Performance(
        sharpe=sr * math.sqrt(DAYS_PER_YEAR),
        sharpe_daily=sr,
        cagr=cagr,
        max_drawdown=max_dd,
        calmar=cagr / abs(max_dd) if max_dd < 0 else math.inf,
        t_stat=sr * math.sqrt(n),
        skew=skew,
        kurtosis=kurt,
        days=n,
    )


# --- CPCV ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Split:
    train: NDArray[np.int64]
    test: NDArray[np.int64]
    test_groups: tuple[int, ...]


def cpcv_splits(
    n_obs: int, n_groups: int = 6, n_test_groups: int = 2, purge: int = 8, embargo: float = 0.01
) -> list[Split]:
    """Particiones de CPCV: C(n_groups, n_test_groups) combinaciones de bloques de prueba.

    Del entrenamiento se quitan ``purge`` observaciones antes y después de cada bloque de prueba
    y un embargo de ``embargo * n_obs`` observaciones después de cada bloque.
    """
    bounds = np.array_split(np.arange(n_obs), n_groups)
    embargo_n = math.ceil(embargo * n_obs)
    splits = []
    for combo in itertools.combinations(range(n_groups), n_test_groups):
        test = np.concatenate([bounds[g] for g in combo])
        banned = np.zeros(n_obs, dtype=bool)
        for g in combo:
            lo = max(int(bounds[g][0]) - purge, 0)
            hi = min(int(bounds[g][-1]) + purge + embargo_n + 1, n_obs)
            banned[lo:hi] = True
        train = np.flatnonzero(~banned)
        splits.append(Split(train=train, test=test, test_groups=combo))
    return splits


def cpcv_test_sharpes(returns: FloatArray, splits: list[Split]) -> FloatArray:
    """Sharpe anualizado de prueba por partición (filas) y configuración (columnas).

    ``returns`` tiene forma (días, configuraciones).
    """
    out = np.empty((len(splits), returns.shape[1]))
    for i, split in enumerate(splits):
        block = returns[split.test]
        for j in range(returns.shape[1]):
            out[i, j] = sharpe_daily(block[:, j]) * math.sqrt(DAYS_PER_YEAR)
    return out


# --- PBO (CSCV) ---------------------------------------------------------------------------


def probability_of_backtest_overfitting(returns: FloatArray, n_blocks: int = 16) -> float:
    """PBO: frecuencia con la que la mejor configuración dentro de muestra cae por debajo de la
    mediana fuera de muestra (logit ≤ 0), sobre todas las mitades de ``n_blocks`` bloques."""
    if n_blocks % 2:
        raise ValueError("n_blocks debe ser par")
    blocks = np.array_split(np.arange(returns.shape[0]), n_blocks)
    n_configs = returns.shape[1]
    logits = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_idx = np.concatenate([blocks[b] for b in combo])
        oos_idx = np.concatenate([blocks[b] for b in range(n_blocks) if b not in combo])
        is_sr = [sharpe_daily(returns[is_idx, j]) for j in range(n_configs)]
        oos_sr = np.array([sharpe_daily(returns[oos_idx, j]) for j in range(n_configs)])
        best = int(np.argmax(is_sr))
        rank = (np.sum(oos_sr < oos_sr[best]) + 1) / (n_configs + 1)  # rango relativo en (0, 1)
        logits.append(math.log(rank / (1 - rank)))
    return float(np.mean(np.array(logits) <= 0))


# --- Deflated Sharpe ----------------------------------------------------------------------


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """SR₀: máximo esperado del Sharpe entre N ensayos sin habilidad (Bailey y López de Prado)."""
    if n_trials < 2:
        return 0.0
    g = EULER_MASCHERONI
    return math.sqrt(var_sharpe) * (
        (1 - g) * _NORMAL.inv_cdf(1 - 1 / n_trials)
        + g * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe_ratio(  # noqa: PLR0913 - son las seis variables de la fórmula del paper
    sharpe: float,
    *,
    n_obs: int,
    skew: float,
    kurtosis: float,
    n_trials: int,
    var_sharpe: float,
) -> float:
    """Probabilidad de que el Sharpe verdadero supere al máximo esperado por azar.

    ``sharpe`` y ``var_sharpe`` en la misma frecuencia que las observaciones (diaria).
    """
    sr0 = expected_max_sharpe(n_trials, var_sharpe)
    denom = math.sqrt(1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2)
    return _NORMAL.cdf((sharpe - sr0) * math.sqrt(n_obs - 1) / denom)
