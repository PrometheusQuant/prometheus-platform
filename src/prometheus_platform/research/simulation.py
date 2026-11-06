"""Simulación del carry (PQ-33, capítulo 6): Markov de regímenes, bondad de ajuste y Monte Carlo.

1. **Regímenes del funding** (negativo, base, alto) y su **cadena de Markov**, con la matriz de
   transición *contada* en el periodo de desarrollo (nunca supuesta) y una prueba χ² de que la
   memoria importa (H0: el régimen siguiente es independiente del actual).
2. **Pseudoaleatorios (6.1):** dentro de cada régimen se ajustan distribuciones candidatas y se
   elige la de menor estadístico KS; se informan KS y χ². La tasa base del contrato (10,95 %
   anual) se modela como masa puntual, porque el EDA mostró que concentra más de la mitad de las
   observaciones.
3. **Monte Carlo (6.2):** años simulados con la regla de H2 (k = 9, θ = 20 %, histéresis θ/2,
   salida con tasa negativa), costes del pre-registro y un escenario de **quiebra del exchange**,
   el riesgo de cola que el backtest no contiene.
4. **Optimización:** fracción del capital en el carry (el resto rinde lo que una stablecoin) que
   maximiza el retorno esperado con un tope de CVaR.

Todo es reproducible (semilla) y usa solo el periodo de desarrollo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy import stats

BASE_RATE = 0.1095  # 0,01 % cada 8 h, anualizado: la tasa por defecto del contrato
POINT_MASSES = (BASE_RATE, 0.0)  # en el régimen base: la tasa del contrato y el funding cero
HIGH_THRESHOLD = 0.20  # coincide con el θ elegido para H2
SETTLEMENTS_PER_YEAR = 3 * 365
SEED = 42
MIN_FIT_SAMPLES = 20  # mínimo razonable para ajustar una distribución y probarla

FloatArray = NDArray[np.float64]


class Regime(IntEnum):
    NEGATIVE = 0
    BASE = 1
    HIGH = 2


REGIME_NAMES = {Regime.NEGATIVE: "negativo", Regime.BASE: "base", Regime.HIGH: "alto"}


def classify(rates: FloatArray) -> NDArray[np.int64]:
    """Régimen de cada tasa anualizada."""
    return np.where(
        rates < 0, Regime.NEGATIVE, np.where(rates < HIGH_THRESHOLD, Regime.BASE, Regime.HIGH)
    ).astype(np.int64)


# --- 1. Cadena de Markov --------------------------------------------------------------------


@dataclass
class MarkovChain:
    counts: NDArray[np.int64]
    transition: FloatArray
    stationary: FloatArray
    chi2: float
    chi2_p_value: float
    expected_duration: FloatArray  # liquidaciones que dura en promedio cada régimen


def fit_markov(sequences: list[FloatArray]) -> MarkovChain:
    """Cuenta transiciones dentro de cada símbolo, nunca entre el fin de uno y el inicio de otro."""
    counts = np.zeros((3, 3), dtype=np.int64)
    for rates in sequences:
        regimes = classify(rates)
        np.add.at(counts, (regimes[:-1], regimes[1:]), 1)
    rows = counts.sum(axis=1, keepdims=True)
    transition = np.divide(counts, rows, out=np.zeros_like(counts, dtype=float), where=rows > 0)
    # Distribución estacionaria: autovector izquierdo de autovalor 1.
    values, vectors = np.linalg.eig(transition.T)
    stationary = np.real(vectors[:, np.argmin(np.abs(values - 1))])
    stationary = stationary / stationary.sum()
    # χ² de independencia: ¿el régimen siguiente depende del actual?
    observed = counts[rows.ravel() > 0][:, counts.sum(axis=0) > 0]
    chi2, p_value, _, _ = stats.chi2_contingency(observed)
    with np.errstate(divide="ignore"):
        duration = 1 / (1 - np.diag(transition))
    return MarkovChain(counts, transition, stationary, float(chi2), float(p_value), duration)


# --- 2. Distribuciones por régimen -----------------------------------------------------------


@dataclass
class FitResult:
    distribution: str
    params: tuple[float, ...]
    ks_statistic: float
    ks_p_value: float
    chi2_statistic: float
    chi2_p_value: float


@dataclass
class RegimeModel:
    regime: Regime
    n: int
    point_mass: dict[float, float]  # valor exacto -> probabilidad (solo régimen base)
    offset: float  # se modela y = signo * (tasa - offset) > 0
    sign: float
    fits: list[FitResult] = field(default_factory=list)
    empirical: FloatArray = field(default_factory=lambda: np.array([]))

    @property
    def best(self) -> FitResult:
        return min(self.fits, key=lambda f: f.ks_statistic)

    def sample(self, rng: np.random.Generator, size: int, *, parametric: bool = True) -> FloatArray:
        u = rng.random(size)
        point_value = np.full(size, np.nan)
        cumulative = 0.0
        for value, probability in self.point_mass.items():
            point_value[(u >= cumulative) & (u < cumulative + probability)] = value
            cumulative += probability
        point = ~np.isnan(point_value)
        if parametric:
            dist = getattr(stats, self.best.distribution)(*self.best.params)
            y = np.asarray(dist.rvs(size=size, random_state=rng), dtype=float)
        else:
            y = rng.choice(self.empirical, size=size)
        rates = self.offset + self.sign * np.abs(y)
        if self.regime is Regime.BASE:
            rates = np.clip(rates, 0.0, HIGH_THRESHOLD - 1e-9)
        return np.where(point, point_value, rates)


CANDIDATES = {
    Regime.NEGATIVE: ("expon", "lognorm", "gamma", "weibull_min"),
    Regime.BASE: ("uniform", "beta", "truncnorm"),
    Regime.HIGH: ("expon", "lognorm", "gamma", "genpareto"),
}


def _chi2_gof(y: FloatArray, dist: Any, n_params: int, bins: int = 10) -> tuple[float, float]:
    """χ² con clases equiprobables según la distribución ajustada."""
    edges = dist.ppf(np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    observed, _ = np.histogram(y, bins=edges)
    expected = np.full(bins, y.size / bins)
    statistic = float(((observed - expected) ** 2 / expected).sum())
    dof = max(bins - 1 - n_params, 1)
    return statistic, float(stats.chi2.sf(statistic, dof))


def _fit_one(name: str, y: FloatArray, regime: Regime) -> FitResult:
    family = getattr(stats, name)
    if name == "beta":
        # La beta exige valores estrictamente dentro de (0, 0,2); hay tasas exactamente en 0.
        inner = np.clip(y, 1e-9, HIGH_THRESHOLD - 1e-9)
        params = family.fit(inner, floc=0, fscale=HIGH_THRESHOLD)
    elif name == "uniform":
        params = (0.0, HIGH_THRESHOLD)
    elif name == "truncnorm":
        mu, sd = float(y.mean()), float(y.std())
        params = ((0 - mu) / sd, (HIGH_THRESHOLD - mu) / sd, mu, sd)
    elif regime is Regime.BASE:
        params = family.fit(y)
    else:
        params = family.fit(y, floc=0)
    dist = family(*params)
    ks = stats.kstest(y, dist.cdf)
    chi2, chi2_p = _chi2_gof(y, dist, len(params))
    return FitResult(
        name, tuple(float(p) for p in params), float(ks.statistic), float(ks.pvalue), chi2, chi2_p
    )


def fit_regimes(rates: FloatArray) -> dict[Regime, RegimeModel]:
    regimes = classify(rates)
    models: dict[Regime, RegimeModel] = {}
    for regime in Regime:
        values = rates[regimes == regime]
        masses = (
            {v: np.isclose(values, v, atol=1e-9) for v in POINT_MASSES}
            if regime is Regime.BASE
            else {}
        )
        point = np.zeros(values.size, bool)
        for mask in masses.values():
            point |= mask
        continuous = values[~point]
        if regime is Regime.NEGATIVE:
            offset, sign, y = 0.0, -1.0, -continuous
        elif regime is Regime.HIGH:
            offset, sign, y = HIGH_THRESHOLD, 1.0, continuous - HIGH_THRESHOLD
        else:
            offset, sign, y = 0.0, 1.0, continuous
        y = y[y > 0] if regime is not Regime.BASE else y
        model = RegimeModel(
            regime,
            int(values.size),
            {v: float(mask.mean()) for v, mask in masses.items()},
            offset,
            sign,
            empirical=y,
        )
        if y.size >= MIN_FIT_SAMPLES:
            model.fits = [_fit_one(name, y, regime) for name in CANDIDATES[regime]]
        models[regime] = model
    return models


# --- 3. Monte Carlo --------------------------------------------------------------------------


@dataclass(frozen=True)
class CarryRules:
    k: int = 9
    theta: float = 0.20
    round_trip_cost: float = 0.0050  # fracción del nocional, 4 patas (H2: 0,15 % + 0,10 % por lado)
    notional_fraction: float = 0.5  # 1x: la mitad del capital en cada pata


@dataclass
class MonteCarloResult:
    annual_returns: FloatArray
    invested_fraction: FloatArray
    cycles: FloatArray

    def summary(self, hurdle: float) -> dict[str, float]:
        r = self.annual_returns
        var95 = float(np.quantile(r, 0.05))
        return {
            "media": float(r.mean()),
            "mediana": float(np.median(r)),
            "p5": var95,
            "p95": float(np.quantile(r, 0.95)),
            "var95": -var95,
            "cvar95": -float(r[r <= var95].mean()),
            "prob_bajo_hurdle": float((r < hurdle).mean()),
            "prob_perdida": float((r < 0).mean()),
            "tiempo_invertido": float(self.invested_fraction.mean()),
            "ciclos": float(self.cycles.mean()),
        }


def simulate_rates(  # noqa: PLR0913 - keyword-only: parámetros de la simulación
    chain: MarkovChain,
    models: dict[Regime, RegimeModel],
    *,
    n_paths: int,
    n_steps: int,
    rng: np.random.Generator,
    parametric: bool = True,
) -> FloatArray:
    """Trayectorias de tasas anualizadas: régimen por Markov y tasa según su distribución."""
    cumulative = np.cumsum(chain.transition, axis=1)
    regimes = np.empty((n_paths, n_steps), dtype=np.int64)
    regimes[:, 0] = rng.choice(3, size=n_paths, p=chain.stationary)
    for t in range(1, n_steps):
        u = rng.random(n_paths)
        regimes[:, t] = (u[:, None] > cumulative[regimes[:, t - 1]]).sum(axis=1)
    rates = np.empty((n_paths, n_steps))
    for regime in Regime:
        mask = regimes == regime
        rates[mask] = models[regime].sample(rng, int(mask.sum()), parametric=parametric)
    return rates


def regime_spells(sequences: list[FloatArray]) -> dict[Regime, list[FloatArray]]:
    """Rachas históricas consecutivas de cada régimen, dentro de cada símbolo."""
    spells: dict[Regime, list[FloatArray]] = {r: [] for r in Regime}
    for rates in sequences:
        regimes = classify(rates)
        breaks = np.flatnonzero(np.diff(regimes)) + 1
        for chunk, labels in zip(np.split(rates, breaks), np.split(regimes, breaks), strict=True):
            spells[Regime(int(labels[0]))].append(chunk)
    return spells


@dataclass
class SojournTest:
    """¿Las duraciones de las rachas son geométricas, como supone una Markov de primer orden?"""

    regime: Regime
    spells: int
    mean_observed: float
    mean_geometric: float
    p95_observed: float
    p95_geometric: float
    chi2: float
    p_value: float


def sojourn_tests(chain: MarkovChain, spells: dict[Regime, list[FloatArray]]) -> list[SojournTest]:
    """χ² de las duraciones observadas frente a la geométrica implícita en la diagonal."""
    results = []
    for regime in Regime:
        lengths = np.array([len(x) for x in spells[regime]])
        if lengths.size < MIN_FIT_SAMPLES:
            continue
        p_leave = 1 - chain.transition[regime, regime]
        geometric = stats.geom(p_leave)
        edges = np.unique(
            np.concatenate([[0.5], geometric.ppf(np.linspace(0.1, 0.9, 9)) + 0.5, [np.inf]])
        )
        observed, _ = np.histogram(lengths, bins=edges)
        expected = lengths.size * np.diff(geometric.cdf(np.minimum(edges, 1e9)))
        keep = expected > 0
        statistic = float(((observed[keep] - expected[keep]) ** 2 / expected[keep]).sum())
        dof = max(int(keep.sum()) - 2, 1)
        results.append(
            SojournTest(
                regime,
                int(lengths.size),
                float(lengths.mean()),
                float(geometric.mean()),
                float(np.quantile(lengths, 0.95)),
                float(geometric.ppf(0.95)),
                statistic,
                float(stats.chi2.sf(statistic, dof)),
            )
        )
    return results


def simulate_rates_semimarkov(
    chain: MarkovChain,
    spells: dict[Regime, list[FloatArray]],
    *,
    n_paths: int,
    n_steps: int,
    rng: np.random.Generator,
) -> FloatArray:
    """Modelo v3 (semi-Markov): el régimen siguiente sale de la cadena de saltos estimada (la matriz
    sin su diagonal, renormalizada) y cada racha es una racha histórica **completa** del régimen,
    con su duración real. Así se respetan las rachas largas que una Markov de primer orden no ve."""
    jump = chain.transition * (1 - np.eye(3))
    jump = jump / np.maximum(jump.sum(axis=1, keepdims=True), 1e-12)
    out = np.empty((n_paths, n_steps))
    for path in range(n_paths):
        t, regime = 0, int(rng.choice(3, p=chain.stationary))
        while t < n_steps:
            pool = spells[Regime(regime)]
            spell = pool[int(rng.integers(len(pool)))] if pool else np.array([BASE_RATE])
            length = min(spell.size, n_steps - t)
            out[path, t : t + length] = spell[:length]
            t += length
            regime = int(rng.choice(3, p=jump[regime]))
    return out


WEEK = 21  # liquidaciones de 8 h en una semana
BLOCK = 63  # 21 días: el bloque más corto que reproduce la historia (ver el informe del cap. 6)
MIN_BLOCKS_PER_REGIME = 40


@dataclass
class WeeklyRegimeModel:
    """Modelo v4: cadena de Markov sobre el régimen de cada **semana** (fase de mercado) y, dentro
    de cada régimen, semanas históricas completas tomadas al azar (*block bootstrap*)."""

    chain: MarkovChain
    weeks: dict[Regime, list[FloatArray]]
    block: int = WEEK

    def simulate(self, *, n_paths: int, n_steps: int, rng: np.random.Generator) -> FloatArray:
        n_weeks = -(-n_steps // self.block)
        cumulative = np.cumsum(self.chain.transition, axis=1)
        states = np.empty((n_paths, n_weeks), dtype=np.int64)
        states[:, 0] = rng.choice(3, size=n_paths, p=self.chain.stationary)
        for w in range(1, n_weeks):
            u = rng.random(n_paths)
            states[:, w] = (u[:, None] > cumulative[states[:, w - 1]]).sum(axis=1)
        out = np.empty((n_paths, n_weeks * self.block))
        for regime in Regime:
            pool = self.weeks[regime] or [np.full(self.block, BASE_RATE)]
            stacked = np.stack(pool)
            paths, slots = np.nonzero(states == regime)
            picks = stacked[rng.integers(len(pool), size=paths.size)]
            for offset in range(self.block):
                out[paths, slots * self.block + offset] = picks[:, offset]
        return out[:, :n_steps]


def weekly_blocks(
    sequences: list[FloatArray], block: int = WEEK
) -> tuple[list[FloatArray], dict[Regime, list[FloatArray]]]:
    """Corta cada símbolo en bloques completos y clasifica cada bloque por su tasa media."""
    weekly_means: list[FloatArray] = []
    weeks: dict[Regime, list[FloatArray]] = {r: [] for r in Regime}
    for rates in sequences:
        n = rates.size // block
        blocks = rates[: n * block].reshape(n, block)
        means = blocks.mean(axis=1)
        weekly_means.append(means)
        for chunk, regime in zip(blocks, classify(means), strict=True):
            weeks[Regime(int(regime))].append(chunk)
    return weekly_means, weeks


def fit_weekly_model(sequences: list[FloatArray], block: int = WEEK) -> WeeklyRegimeModel:
    weekly_means, weeks = weekly_blocks(sequences, block)
    return WeeklyRegimeModel(fit_markov(weekly_means), weeks, block)


def run_carry(rates: FloatArray, rules: CarryRules, *, warmup: int) -> MonteCarloResult:
    """Aplica la regla de H2 a cada trayectoria; las ``warmup`` primeras solo alimentan la señal."""
    n_paths, n_steps = rates.shape
    kernel = np.ones(rules.k) / rules.k
    signal = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="full")[: r.size], 1, rates)
    invested = np.zeros(n_paths, dtype=bool)
    capital = np.ones(n_paths)
    invested_steps = np.zeros(n_paths)
    cycles = np.zeros(n_paths)
    per_settlement = rules.notional_fraction / SETTLEMENTS_PER_YEAR
    for t in range(warmup, n_steps):
        # Funding de la liquidación t si la posición ya estaba abierta.
        capital += np.where(invested, rates[:, t] * per_settlement * capital, 0.0)
        enter = ~invested & (signal[:, t] >= rules.theta)
        leave = invested & ((signal[:, t] < rules.theta / 2) | (rates[:, t] < 0))
        traded = enter | leave
        capital -= np.where(
            traded, capital * rules.notional_fraction * rules.round_trip_cost / 2, 0.0
        )
        cycles += enter
        invested = (invested | enter) & ~leave
        invested_steps += invested
    return MonteCarloResult(capital - 1, invested_steps / (n_steps - warmup), cycles)


def apply_exchange_failure(
    returns: FloatArray, annual_probability: float, loss: float, rng: np.random.Generator
) -> FloatArray:
    """Escenario de cola: con probabilidad p en el año, el exchange quiebra y se pierde ``loss``."""
    failed = rng.random(returns.size) < annual_probability
    return np.where(failed, (1 + returns) * (1 - loss) - 1, returns)


def optimal_allocation(
    carry_returns: FloatArray, hurdle: float, cvar_limit: float, steps: int = 21
) -> list[dict[str, float]]:
    """Frontera: para cada fracción w en el carry (1 - w en stablecoin), retorno esperado y CVaR."""
    frontier = []
    for w in np.linspace(0, 1, steps):
        r = w * carry_returns + (1 - w) * hurdle
        var95 = np.quantile(r, 0.05)
        cvar = -float(r[r <= var95].mean())
        frontier.append(
            {
                "w_carry": float(w),
                "retorno_esperado": float(r.mean()),
                "cvar95": cvar,
                "cumple": cvar <= cvar_limit,
            }
        )
    return frontier


def development_sequences(panels: list[pl.DataFrame]) -> list[FloatArray]:
    return [p.sort("funding_time")["annualized"].drop_nulls().to_numpy() for p in panels]


# --- 4. Estudio completo ---------------------------------------------------------------------


@dataclass
class ValidationRow:
    model: str
    cycles: float
    mean_return: float
    invested: float


@dataclass
class SimulationStudy:
    chain: MarkovChain
    regime_models: dict[Regime, RegimeModel]
    sojourn: list[SojournTest]
    block_model: WeeklyRegimeModel
    validation: list[ValidationRow]
    historical: ValidationRow
    baseline: MonteCarloResult
    scenarios: dict[str, dict[str, float]]
    frontier: list[dict[str, float]]
    tail_returns: FloatArray
    break_even_failure: (
        float  # p anual de quiebra con la que el carry rinde igual que la stablecoin
    )


def historical_benchmark(sequences: list[FloatArray], rules: CarryRules) -> ValidationRow:
    """La regla aplicada a la historia real: lo que el simulador debe reproducir."""
    cycles, returns, invested = [], [], []
    for rates in sequences:
        result = run_carry(rates[None, :], rules, warmup=rules.k)
        years = rates.size / SETTLEMENTS_PER_YEAR
        cycles.append(result.cycles[0] / years)
        returns.append((1 + result.annual_returns[0]) ** (1 / years) - 1)
        invested.append(result.invested_fraction[0])
    return ValidationRow(
        "historia real", float(np.mean(cycles)), float(np.mean(returns)), float(np.mean(invested))
    )


def run_simulation_study(  # noqa: PLR0913 - keyword-only: parámetros del estudio
    sequences: list[FloatArray],
    *,
    rules: CarryRules | None = None,
    n_paths: int = 10_000,
    hurdle: float = 0.04,
    exchange_failure: tuple[float, ...] = (0.02, 0.05),
    cvar_limit: float = 0.05,
    seed: int = SEED,
) -> SimulationStudy:
    rules = rules or CarryRules()
    rng = np.random.default_rng(seed)
    steps, warmup = SETTLEMENTS_PER_YEAR + 30, 30
    chain = fit_markov(sequences)
    models = fit_regimes(np.concatenate(sequences))
    spells = regime_spells(sequences)
    block_model = fit_weekly_model(sequences, BLOCK)

    def validate(name: str, rates: FloatArray) -> tuple[ValidationRow, MonteCarloResult]:
        result = run_carry(rates, rules, warmup=warmup)
        summary = result.summary(hurdle)
        row = ValidationRow(name, summary["ciclos"], summary["media"], summary["tiempo_invertido"])
        return row, result

    small = max(n_paths // 5, 100)  # los modelos descartados se validan con menos trayectorias
    v1 = simulate_rates(chain, models, n_paths=small, n_steps=steps, rng=rng)
    v2 = simulate_rates_semimarkov(chain, spells, n_paths=small, n_steps=steps, rng=rng)
    validation = [
        validate("v1 Markov de 1er orden + distribuciones ajustadas", v1)[0],
        validate("v2 semi-Markov (rachas históricas)", v2)[0],
    ]
    final_row, baseline = validate(
        f"v3 Markov de régimen por bloques de {BLOCK // 3} días",
        block_model.simulate(n_paths=n_paths, n_steps=steps, rng=rng),
    )
    validation.append(final_row)

    scenarios = {"sin quiebra del exchange": baseline.summary(hurdle)}
    stressed_returns = {}
    for probability in exchange_failure:
        returns = apply_exchange_failure(baseline.annual_returns, probability, 1.0, rng)
        stressed_returns[probability] = returns
        stressed = MonteCarloResult(returns, baseline.invested_fraction, baseline.cycles)
        scenarios[f"quiebra con p = {probability:.0%} anual"] = stressed.summary(hurdle)
    # La frontera usa el escenario de quiebra más moderado: el riesgo de la stablecoin no se modela.
    tail = stressed_returns[min(exchange_failure)]
    # E[r] con quiebra = (1 - p)(1 + m) - 1; se iguala al hurdle y se despeja p.
    mean = float(baseline.annual_returns.mean())
    break_even = max(0.0, 1 - (1 + hurdle) / (1 + mean))
    return SimulationStudy(
        chain=chain,
        regime_models=models,
        sojourn=sojourn_tests(chain, spells),
        block_model=block_model,
        validation=validation,
        historical=historical_benchmark(sequences, rules),
        baseline=baseline,
        scenarios=scenarios,
        frontier=optimal_allocation(tail, hurdle, cvar_limit),
        tail_returns=tail,
        break_even_failure=break_even,
    )
