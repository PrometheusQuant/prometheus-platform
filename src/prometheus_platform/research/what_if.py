"""Simulador «¿y si…?» para el jurado (PQ-58, Proyecto Integrador 7.3).

Reutiliza el Monte Carlo del capítulo 6 sin cambiar el modelo: cadena de Markov de régimen
por bloques de 21 días, ajustada **solo con el periodo de desarrollo** de H2. Lo que el usuario
mueve es su situación: capital, horizonte y riesgo de quiebra del exchange.

El umbral θ solo se elige entre los del pre-registro (10, 20 y 30 %). Un control libre invitaría
a «optimizar» en vivo, que es justo el sobreajuste que la plataforma existe para evitar. Nada de
lo que se haga aquí es un ensayo ni suma a N.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from prometheus_platform.research import carry_evaluation as ce
from prometheus_platform.research.panel import development_only
from prometheus_platform.research.simulation import (
    BLOCK,
    SETTLEMENTS_PER_YEAR,
    CarryRules,
    FloatArray,
    WeeklyRegimeModel,
    development_sequences,
    fit_weekly_model,
    run_carry,
)

PRE_REGISTERED_THETAS = (0.10, 0.20, 0.30)
HORIZONS_YEARS = (1, 3)
HURDLE = 0.04
WARMUP = 30
PATHS = 2_000
SEED = 2026


@dataclass(frozen=True)
class WhatIf:
    capital: float
    years: int
    failure_probability: float  # anual
    theta: float = 0.20

    def __post_init__(self) -> None:
        if self.capital <= 0:
            raise ValueError("El capital debe ser positivo")
        if self.years not in HORIZONS_YEARS:
            raise ValueError(f"Horizonte fuera de {HORIZONS_YEARS}")
        if not 0 <= self.failure_probability < 1:
            raise ValueError("La probabilidad de quiebra debe estar en [0, 1)")
        if self.theta not in PRE_REGISTERED_THETAS:
            raise ValueError(f"θ solo puede ser uno de los pre-registrados {PRE_REGISTERED_THETAS}")


@dataclass(frozen=True)
class WhatIfResult:
    final_capital: FloatArray  # una por trayectoria, en USD
    stablecoin_capital: float
    median: float
    p5: float
    p95: float
    prob_loss: float
    prob_beats_stablecoin: float
    cvar95_loss: float  # pérdida media en el peor 5 %, en USD (positiva)
    invested_fraction: float
    horizon_failure_probability: float


def development_rate_sequences(data_dir: Path, hypothesis: str = "H2") -> list[FloatArray]:
    """Tasas anualizadas del desarrollo, una secuencia por símbolo (igual que el cap. 6)."""
    panels = [
        development_only(ce.load_symbol(data_dir / "silver", s).settlements)
        for s in ce.HYPOTHESES[hypothesis]
    ]
    return development_sequences(panels)


def fit_model(sequences: list[FloatArray]) -> WeeklyRegimeModel:
    return fit_weekly_model(sequences, BLOCK)


def simulate(
    model: WeeklyRegimeModel, scenario: WhatIf, *, paths: int = PATHS, seed: int = SEED
) -> WhatIfResult:
    rng = np.random.default_rng(seed)
    steps = scenario.years * SETTLEMENTS_PER_YEAR + WARMUP
    rates = model.simulate(n_paths=paths, n_steps=steps, rng=rng)
    result = run_carry(rates, CarryRules(theta=scenario.theta), warmup=WARMUP)
    growth = 1 + result.annual_returns  # rendimiento acumulado de todo el horizonte

    # Quiebra: probabilidad de que ocurra en algún momento del horizonte; se pierde todo el capital
    # que está en el exchange (supuesto conservador del cap. 6).
    horizon_p = 1 - (1 - scenario.failure_probability) ** scenario.years
    failed = rng.random(paths) < horizon_p
    final = np.where(failed, 0.0, scenario.capital * growth)

    stablecoin = scenario.capital * (1 + HURDLE) ** scenario.years
    p5 = float(np.quantile(final, 0.05))
    tail = final[final <= p5]
    return WhatIfResult(
        final_capital=final,
        stablecoin_capital=stablecoin,
        median=float(np.median(final)),
        p5=p5,
        p95=float(np.quantile(final, 0.95)),
        prob_loss=float((final < scenario.capital).mean()),
        prob_beats_stablecoin=float((final > stablecoin).mean()),
        cvar95_loss=float(scenario.capital - tail.mean()),
        invested_fraction=float(result.invested_fraction.mean()),
        horizon_failure_probability=horizon_p,
    )


def histogram(values: FloatArray, bins: int = 30) -> tuple[FloatArray, FloatArray]:
    """Conteos y centros de clase, para graficar sin depender de la librería de gráficos."""
    counts, edges = np.histogram(values, bins=bins)
    return counts.astype(np.float64), (edges[:-1] + edges[1:]) / 2
