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


# --- Método para pre-registros nuevos (PQ-122) ---------------------------------------------------
# La revisión adversarial de la tendencia (PQ-68) encontró limitaciones de método. No se corrigen
# en los pre-registros ya ejecutados (sería ajustar el método a los datos): estas funciones son las
# que deben usar los pre-registros **nuevos**. Las de arriba quedan como estaban.


@dataclass(frozen=True)
class CpcvSelection:
    """Selección fuera de muestra real en CPCV: en cada partición se elige con el entrenamiento."""

    chosen: NDArray[np.int64]  # configuración elegida en cada partición (índice de columna)
    oos_sharpe: FloatArray  # Sharpe anualizado de prueba de la elegida, por partición
    in_sample_sharpe: FloatArray  # Sharpe anualizado de entrenamiento de la elegida

    @property
    def median_oos(self) -> float:
        return float(np.median(self.oos_sharpe))

    @property
    def share_oos_losing(self) -> float:
        """Parte de las particiones donde la elegida no ganó fuera de muestra (Sharpe ≤ 0)."""
        return float(np.mean(self.oos_sharpe <= 0))


def cpcv_select_out_of_sample(returns: FloatArray, splits: list[Split]) -> CpcvSelection:
    """Elige en el entrenamiento de cada partición y mide en su prueba.

    ``cpcv_test_sharpes`` mira solo ``split.test``: con 6 grupos y 2 de prueba, cada día cae en
    prueba 5 de 15 veces, así que «el mejor Sharpe medio de prueba» equivale a elegir con toda la
    muestra. Aquí la elección de cada partición no ve su prueba. Empates: la primera columna.
    """
    chosen = np.empty(len(splits), dtype=np.int64)
    oos = np.empty(len(splits))
    ins = np.empty(len(splits))
    annual = math.sqrt(DAYS_PER_YEAR)
    for i, split in enumerate(splits):
        train = returns[split.train]
        train_sr = np.array([sharpe_daily(train[:, j]) for j in range(returns.shape[1])])
        best = int(np.argmax(train_sr))
        chosen[i] = best
        ins[i] = train_sr[best] * annual
        oos[i] = sharpe_daily(returns[split.test, best]) * annual
    return CpcvSelection(chosen=chosen, oos_sharpe=oos, in_sample_sharpe=ins)


def deflated_sharpe_family_and_global(
    perf: Performance, *, n_family: int, n_global: int, var_sharpe: float
) -> tuple[float, float]:
    """El Deflated Sharpe con el N de la familia (el del gate) y con el N global del registro."""
    if n_global < n_family:
        raise ValueError(f"El N global ({n_global}) no puede ser menor que el de la familia")
    family, overall = (
        deflated_sharpe_ratio(
            perf.sharpe_daily,
            n_obs=perf.days,
            skew=perf.skew,
            kurtosis=perf.kurtosis,
            n_trials=n,
            var_sharpe=var_sharpe,
        )
        for n in (n_family, n_global)
    )
    return family, overall


def newey_west_t(returns: FloatArray, lags: int | None = None) -> float:
    """t de la media con error estándar de Newey-West (robusto a autocorrelación).

    Por defecto, ``lags = floor(4 · (n / 100)^(2/9))`` (Newey y West, 1994). Con retornos sin
    autocorrelación se parece a ``SR · √n``; con autocorrelación positiva es menor.
    """
    n = int(returns.size)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 observaciones")
    if lags is None:
        lags = math.floor(4 * (n / 100) ** (2 / 9))
    centered = returns - np.mean(returns)
    variance = float(np.dot(centered, centered)) / n
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1 - lag / (lags + 1)  # núcleo de Bartlett
        variance += 2 * weight * float(np.dot(centered[lag:], centered[:-lag])) / n
    if variance <= _FLAT**2:
        return 0.0
    return float(np.mean(returns)) / math.sqrt(variance / n)


def annual_turnover(traded: FloatArray, equity: FloatArray) -> float:
    """Rotación anual como fracción del capital: Σ(nocional negociado / capital del día) por año.

    ``traded`` y ``equity`` son diarios y del mismo largo. Así una cartera que duplica o pierde la
    mitad del capital no infla ni desinfla su rotación (en la tendencia se medía sobre C inicial).
    """
    if traded.shape != equity.shape or traded.size == 0:
        raise ValueError("traded y equity deben ser diarios y del mismo largo")
    if np.any(equity <= 0):
        raise ValueError("El capital debe ser positivo para medir la rotación")
    return float(np.sum(traded / equity)) * DAYS_PER_YEAR / traded.size


def idle_cash_returns(
    returns: FloatArray, mean_invested_weight: float, hurdle: float
) -> FloatArray:
    """Sensibilidad con el efectivo ocioso remunerado: suma ``(1 - peso medio) * hurdle`` diario.

    Usa el **peso medio invertido**, no la fracción de tiempo invertido: una cartera siempre dentro
    con la mitad del capital tiene la mitad ociosa.
    """
    if not 0 <= mean_invested_weight <= 1:
        raise ValueError("El peso medio invertido debe estar en [0, 1]")
    return returns + (1 - mean_invested_weight) * hurdle / DAYS_PER_YEAR


@dataclass(frozen=True)
class SharpeDifference:
    z: float
    p_value: float  # una cola: H1, el Sharpe de la estrategia es mayor que el del benchmark


def sharpe_difference_test(strategy: FloatArray, benchmark: FloatArray) -> SharpeDifference:
    """Jobson-Korkie con la corrección de Memmel (2003) para comparar dos Sharpe de igual periodo.

    ``Var(SR1 - SR2) = [2(1 - rho) + (SR1^2 + SR2^2 - 2 SR1 SR2 rho^2) / 2] / n``, con Sharpe
    por periodo y ``rho`` la correlación de las dos series.
    Es la prueba para los gates que piden «mejor que el benchmark».
    """
    if strategy.shape != benchmark.shape or strategy.size < 3:
        raise ValueError("Las dos series deben tener el mismo largo (al menos 3 días)")
    n = strategy.size
    sr1, sr2 = sharpe_daily(strategy), sharpe_daily(benchmark)
    rho = float(np.corrcoef(strategy, benchmark)[0, 1])
    variance = (2 * (1 - rho) + 0.5 * (sr1**2 + sr2**2 - 2 * sr1 * sr2 * rho**2)) / n
    if variance <= 0:
        return SharpeDifference(z=0.0, p_value=0.5)
    z = (sr1 - sr2) / math.sqrt(variance)
    return SharpeDifference(z=z, p_value=1 - _NORMAL.cdf(z))
