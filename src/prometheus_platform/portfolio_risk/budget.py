"""Presupuesto de capital entre estrategias con un tope de CVaR (PQ-83, ADR-0012).

Extiende la optimización del capítulo 6 (``research/simulation.optimal_allocation``, una sola
estrategia contra la stablecoin) a **varias estrategias con sus correlaciones**:

1. **Escenarios conjuntos.** Se remuestrean por bloques los retornos diarios **del desarrollo** de
   todas las estrategias **a la vez** (las mismas fechas para todas), así un año simulado conserva
   la correlación y las rachas. Los bloques son de 21 días, el bloque del capítulo 6.
2. **Quiebra del exchange conjunta.** En cada año simulado, cada exchange quiebra con su
   probabilidad anual y **todas** las estrategias que operan en él pierden lo que tienen ahí. Es el
   riesgo de cola que el backtest no contiene.
3. **Optimización.** Se recorren las asignaciones de una rejilla (pasos del 5 %): cada estrategia
   recibe una fracción del capital y el resto queda en efectivo al 4 % (stablecoin). Se elige la de
   mayor retorno esperado con ``CVaR95 <= cvar_limit`` y el capital de cada exchange por debajo de
   su tope.
4. **Tope por exchange.** La mayor fracción que puede estar en un exchange sin que su quiebra, por
   sí sola, supere el presupuesto de CVaR. Se calibra con la **mayor** entre la probabilidad de
   quiebra supuesta y la de equilibrio del capítulo 6, que es la que el carry puede pagar.

Todo es puro (numpy) y determinista con semilla: no lee archivos ni conoce el runner.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
DAYS_PER_YEAR = 365
BLOCK_DAYS = 21  # el bloque del capítulo 6 (63 liquidaciones de 8 h)
TAIL = 0.05  # CVaR al 95 %
HURDLE = 0.04  # stablecoin
SEED = 42


def cvar95(returns: FloatArray) -> float:
    """Pérdida media del peor 5 % (positiva si se pierde)."""
    if returns.size == 0:
        raise ValueError("CVaR de una serie vacía")
    var = np.quantile(returns, TAIL)
    return -float(returns[returns <= var].mean())


def joint_annual_scenarios(
    daily: Mapping[str, FloatArray],
    *,
    n_paths: int = 10_000,
    block: int = BLOCK_DAYS,
    seed: int = SEED,
) -> dict[str, FloatArray]:
    """Retornos anuales simulados por estrategia, con bloques **comunes** a todas.

    ``daily`` trae los retornos diarios del desarrollo, alineados por fecha (misma longitud).
    """
    if not daily:
        raise ValueError("Hace falta al menos una estrategia")
    lengths = {len(r) for r in daily.values()}
    if len(lengths) != 1:
        raise ValueError(f"Los retornos deben estar alineados por fecha: longitudes {lengths}")
    (n_days,) = lengths
    if n_days < block:
        raise ValueError(f"Hacen falta al menos {block} días de historia, hay {n_days}")
    rng = np.random.default_rng(seed)
    n_blocks = -(-DAYS_PER_YEAR // block)  # techo: se recorta a 365 días
    starts = rng.integers(0, n_days - block + 1, size=(n_paths, n_blocks))
    index = (starts[:, :, None] + np.arange(block)).reshape(n_paths, -1)[:, :DAYS_PER_YEAR]
    return {
        name: np.prod(1 + np.asarray(r, dtype=np.float64)[index], axis=1) - 1
        for name, r in daily.items()
    }


def apply_exchange_failures(
    annual: Mapping[str, FloatArray],
    exchange_of: Mapping[str, str],
    failure_probability: Mapping[str, float],
    *,
    seed: int = SEED,
) -> dict[str, FloatArray]:
    """Cada exchange quiebra con su probabilidad anual; sus estrategias lo pierden **todo** ese año.

    La misma quiebra golpea a todas las estrategias de ese exchange en el mismo escenario.
    """
    rng = np.random.default_rng(seed + 1)
    n_paths = len(next(iter(annual.values())))
    failed = {
        exchange: rng.random(n_paths) < failure_probability.get(exchange, 0.0)
        for exchange in sorted(set(exchange_of.values()))
    }
    return {
        name: np.where(failed[exchange_of[name]], -1.0, returns) for name, returns in annual.items()
    }


def exchange_cap(
    *, cvar_limit: float, assumed_probability: float, break_even_probability: float
) -> float:
    """Fracción máxima en un exchange para que su quiebra sola no supere el presupuesto de CVaR.

    Si un exchange quiebra con probabilidad p < 5 %, la quiebra (pérdida total de x) ocupa p/5 % de
    la cola, y su CVaR95 es ``x · p / 0,05``. Con p ≥ 5 % es ``x``. Se usa la mayor de las dos
    probabilidades: la supuesta y la de equilibrio del capítulo 6.
    """
    p = max(assumed_probability, break_even_probability)
    if not 0 < cvar_limit < 1 or not 0 <= p <= 1:
        raise ValueError("cvar_limit en (0, 1) y probabilidades en [0, 1]")
    if p == 0:
        return 1.0
    return min(1.0, cvar_limit * TAIL / p) if p < TAIL else cvar_limit


@dataclass(frozen=True, slots=True)
class Budget:
    weights: dict[str, float]  # fracción del capital por estrategia
    cash: float  # fracción en efectivo al 4 %
    expected_return: float
    cvar95: float
    by_exchange: dict[str, float] = field(default_factory=dict)


def optimize_budget(  # noqa: PLR0913 - keyword-only: cada argumento es una restricción
    scenarios: Mapping[str, FloatArray],
    exchange_of: Mapping[str, str],
    *,
    caps: Mapping[str, float],
    cvar_limit: float,
    hurdle: float = HURDLE,
    step: float = 0.05,
) -> Budget:
    """Mayor retorno esperado con CVaR95 ≤ ``cvar_limit`` y cada exchange bajo su tope.

    Rejilla exhaustiva sobre el símplex (con pocas estrategias es exacta en la rejilla y fácil de
    auditar). Un empate se resuelve a favor de **más efectivo**: ante la duda, menos riesgo. El
    100 % en efectivo siempre cumple (su CVaR es ``-hurdle``), así que siempre hay solución.
    """
    if not 0 < cvar_limit < 1 or hurdle < 0:
        raise ValueError("cvar_limit en (0, 1) y hurdle no negativo")
    names = sorted(scenarios)
    if set(names) - set(exchange_of):
        raise ValueError(f"Falta el exchange de {sorted(set(names) - set(exchange_of))}")
    steps = round(1 / step)
    if not np.isclose(steps * step, 1):
        raise ValueError(f"El paso debe dividir 1: {step}")
    matrix = np.column_stack([scenarios[n] for n in names])
    best: Budget | None = None
    for combo in itertools.product(range(steps + 1), repeat=len(names)):
        if sum(combo) > steps:
            continue
        w = np.array(combo, dtype=np.float64) * step
        by_exchange: dict[str, float] = {}
        for name, weight in zip(names, w, strict=True):
            exchange = exchange_of[name]
            by_exchange[exchange] = by_exchange.get(exchange, 0.0) + float(weight)
        if any(v > caps.get(e, 1.0) + 1e-9 for e, v in by_exchange.items()):
            continue
        cash = 1 - float(w.sum())
        portfolio = matrix @ w + cash * hurdle
        risk = cvar95(portfolio)
        if risk > cvar_limit + 1e-12:
            continue
        candidate = Budget(
            weights={n: float(x) for n, x in zip(names, w, strict=True)},
            cash=cash,
            expected_return=float(portfolio.mean()),
            cvar95=risk,
            by_exchange=by_exchange,
        )
        if best is None or _rank(candidate) > _rank(best):
            best = candidate
    if best is None:  # imposible: el 100 % en efectivo siempre cumple
        raise RuntimeError("Sin asignación factible: revisa los topes y el CVaR")
    return best


def _rank(budget: Budget) -> tuple[float, float]:
    """Mayor retorno esperado y, en empate, más efectivo. Se redondea para que el ruido de coma
    flotante (0,04000000000000002) no rompa un empate a favor del riesgo."""
    return round(budget.expected_return, 10), budget.cash


def frontier(
    scenarios: Mapping[str, FloatArray], *, hurdle: float = HURDLE, steps: int = 21
) -> list[dict[str, float]]:
    """Para el informe: retorno esperado y CVaR de repartir w a partes iguales entre estrategias."""
    names = sorted(scenarios)
    matrix = np.column_stack([scenarios[n] for n in names])
    rows = []
    for w in np.linspace(0, 1, steps):
        portfolio = matrix.mean(axis=1) * w + (1 - w) * hurdle
        rows.append(
            {
                "w_estrategias": float(w),
                "retorno_esperado": float(portfolio.mean()),
                "cvar95": cvar95(portfolio),
            }
        )
    return rows


def cvar_contributions(
    scenarios: Mapping[str, FloatArray], weights: Mapping[str, float], *, hurdle: float = HURDLE
) -> dict[str, float]:
    """Contribución de cada estrategia (y del efectivo) al CVaR95 de la cartera (Euler).

    En los escenarios de la cola de la cartera, cada parte aporta su pérdida media ponderada. Las
    contribuciones suman el CVaR95 de la cartera (PQ-84).
    """
    names = sorted(weights)
    cash = 1 - sum(weights.values())
    parts = {n: weights[n] * np.asarray(scenarios[n], dtype=np.float64) for n in names}
    n_paths = len(next(iter(scenarios.values()))) if scenarios else 1
    parts["efectivo"] = np.full(n_paths, cash * hurdle)
    portfolio = np.sum(list(parts.values()), axis=0)
    tail = portfolio <= np.quantile(portfolio, TAIL)
    return {name: -float(values[tail].mean()) for name, values in parts.items()}


def bootstrap_bands(  # noqa: PLR0913 - keyword-only: parámetros del remuestreo
    daily: FloatArray,
    horizon_days: int,
    *,
    n_paths: int = 2_000,
    block: int = BLOCK_DAYS,
    seed: int = SEED,
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> FloatArray:
    """Bandas del capital acumulado (inicio = 1) para cada día de 1 a ``horizon_days``.

    Remuestrea por bloques los retornos diarios del desarrollo, como los escenarios del
    presupuesto. Devuelve una matriz (cuantiles, días).
    """
    returns = np.asarray(daily, dtype=np.float64)
    if horizon_days < 1:
        raise ValueError("El horizonte debe ser de al menos un día")
    if returns.size < block:
        raise ValueError(f"Hacen falta al menos {block} días de historia")
    rng = np.random.default_rng(seed)
    n_blocks = -(-horizon_days // block)
    starts = rng.integers(0, returns.size - block + 1, size=(n_paths, n_blocks))
    index = (starts[:, :, None] + np.arange(block)).reshape(n_paths, -1)[:, :horizon_days]
    paths = np.cumprod(1 + returns[index], axis=1)
    return np.asarray(np.quantile(paths, quantiles, axis=0), dtype=np.float64)
