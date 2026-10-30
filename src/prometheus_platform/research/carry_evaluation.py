"""Evaluación del carry en el periodo de desarrollo (PQ-23, PQ-24, PQ-25).

Ejecuta exactamente lo pre-registrado (``docs/estrategias/01-carry/pre-registro.md``, §5 a §8 y
enmiendas 1 y 2):

1. Las 9 configuraciones (k por θ) de una hipótesis, recorridas con Optuna ``GridSampler`` y
   registradas una a una en el registro de experimentos (N sale del registro).
2. CPCV (6 grupos, 2 de prueba, purge de 8 días, embargo del 1 %): se elige la configuración con
   mayor Sharpe medio de prueba (enm. 1.7).
3. PBO por CSCV de 16 bloques, Deflated Sharpe con N y V[SR] del registro, t-estadístico.
4. Gates G1 a G4 contra los benchmarks B1 (siempre activo) y B2 (4 % anual).

**Nunca toca el holdout**: toda simulación termina antes de ``HOLDOUT_START``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import optuna
import polars as pl

from prometheus_platform.research.backtest import (
    ALT_COSTS,
    MAIN_COSTS,
    MAKER_COSTS,
    CarryConfig,
    CostModel,
    SymbolResult,
    portfolio_returns,
    simulate_symbol,
)
from prometheus_platform.research.panel import (
    HOLDOUT_START,
    hourly_prices,
    load_silver,
    settlement_features,
)
from prometheus_platform.research.validation import (
    DAYS_PER_YEAR,
    Performance,
    Split,
    cpcv_splits,
    cpcv_test_sharpes,
    deflated_sharpe_ratio,
    performance,
    probability_of_backtest_overfitting,
    sharpe_daily,
)

HYPOTHESES: dict[str, tuple[str, ...]] = {
    "H1": ("BTCUSDT", "ETHUSDT"),
    "H2": ("SOLUSDT", "BNBUSDT", "XRPUSDT"),
}
K_GRID = (3, 9, 21)
THETA_GRID = (0.10, 0.20, 0.30)
SMOKE_TEST_TRIALS = 2  # enmienda 2: ejecuciones de la prueba de humo que cuentan en N
STABLECOIN_HURDLE = 0.04
DSR_GATE, PBO_GATE, T_GATE = 0.95, 0.5, 3.0


@dataclass
class TrialRecord:
    hypothesis: str
    name: str
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)


class ExperimentRegistry(Protocol):
    """Registro append-only de ensayos. Cada ensayo ejecutado se registra, sin excepciones."""

    def log_trial(self, trial: TrialRecord) -> None: ...

    def trials(self) -> list[TrialRecord]: ...


@dataclass
class SymbolData:
    symbol: str
    hourly: pl.DataFrame
    settlements: pl.DataFrame


@dataclass
class Gate:
    name: str
    criterion: str
    value: float
    passed: bool


@dataclass
class HypothesisEvaluation:
    hypothesis: str
    symbols: tuple[str, ...]
    returns: dict[str, np.ndarray]  # config -> retornos diarios
    dates: list[str]
    cpcv_mean_sharpe: dict[str, float]
    selected: str
    selected_performance: Performance
    benchmark: Performance
    benchmark_returns: np.ndarray
    pbo: float
    dsr: float
    n_trials: int
    var_sharpe: float
    gates: list[Gate]
    decomposition: dict[str, float]
    sensitivity: dict[str, float]

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)


def costs_for(symbol: str) -> CostModel:
    return MAIN_COSTS if symbol in HYPOTHESES["H1"] else ALT_COSTS


def load_symbol(silver_root: Path, symbol: str) -> SymbolData:
    spot, perp, funding = load_silver(silver_root, symbol)
    hourly = hourly_prices(spot, perp)
    return SymbolData(symbol, hourly, settlement_features(funding, hourly))


def run_config(
    data: Sequence[SymbolData], config: CarryConfig, costs: CostModel | None = None
) -> tuple[pl.DataFrame, list[SymbolResult]]:
    """Cartera de una configuración: el capital se reparte a partes iguales entre símbolos (§4)."""
    share = 1.0 / len(data)
    results = [
        simulate_symbol(
            d.symbol,
            d.hourly,
            d.settlements,
            config=config,
            costs=costs or costs_for(d.symbol),
            capital=share,
            end=HOLDOUT_START,
        )
        for d in data
    ]
    return portfolio_returns(results, share), results


def evaluate_hypothesis(
    hypothesis: str, data: Sequence[SymbolData], registry: ExperimentRegistry
) -> HypothesisEvaluation:
    configs = {c.name: c for c in (CarryConfig(k, t) for k in K_GRID for t in THETA_GRID)}
    daily: dict[str, pl.DataFrame] = {}
    results: dict[str, list[SymbolResult]] = {}

    def objective(trial: optuna.Trial) -> float:
        config = CarryConfig(
            int(trial.suggest_categorical("k", list(K_GRID))),
            float(trial.suggest_categorical("theta", list(THETA_GRID))),
        )
        frame, res = run_config(data, config)
        daily[config.name], results[config.name] = frame, res
        returns = frame["ret"].to_numpy()
        mean_test = float(np.mean(cpcv_test_sharpes(returns[:, None], _splits(len(returns)))))
        perf = performance(returns)
        registry.log_trial(
            TrialRecord(
                hypothesis=hypothesis,
                name=config.name,
                params={"k": str(config.k), "theta": str(config.theta)},
                metrics={
                    "cpcv_mean_test_sharpe": mean_test,
                    "sharpe": perf.sharpe,
                    "sharpe_daily": perf.sharpe_daily,
                    "cagr": perf.cagr,
                    "max_drawdown": perf.max_drawdown,
                },
                tags={"period": "desarrollo", "costs": "principal"},
            )
        )
        return mean_test

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.GridSampler({"k": list(K_GRID), "theta": list(THETA_GRID)}, seed=0)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=len(configs))

    # Matriz días por configuraciones alineada por fecha.
    names = sorted(daily)
    aligned = daily[names[0]].select("date", pl.col("ret").alias(names[0]))
    for name in names[1:]:
        aligned = aligned.join(daily[name].select("date", pl.col("ret").alias(name)), on="date")
    matrix = aligned.select(names).to_numpy()
    splits = _splits(matrix.shape[0])
    test_sharpes = cpcv_test_sharpes(matrix, splits)
    cpcv_mean = {n: float(test_sharpes[:, j].mean()) for j, n in enumerate(names)}
    selected = max(cpcv_mean, key=lambda n: cpcv_mean[n])
    sel_returns = matrix[:, names.index(selected)]
    sel_perf = performance(sel_returns)

    benchmark_frame, _ = run_config(data, CarryConfig(9, 0.0, always_on=True))
    benchmark_aligned = aligned.select("date").join(benchmark_frame, on="date", how="left")
    bench_returns = benchmark_aligned["ret"].fill_null(0.0).to_numpy()
    bench_perf = performance(bench_returns)

    trials = registry.trials()
    # Pre-registro §5: N ≥ 18 (las dos hipótesis), más los ensayos de la prueba de humo.
    n_trials = max(len(trials), len(HYPOTHESES) * len(K_GRID) * len(THETA_GRID)) + SMOKE_TEST_TRIALS
    daily_sharpes = np.array(
        [t.metrics["sharpe_daily"] for t in trials if "sharpe_daily" in t.metrics]
    )
    var_sharpe = float(np.var(daily_sharpes, ddof=1)) if daily_sharpes.size > 1 else 0.0
    dsr = deflated_sharpe_ratio(
        sel_perf.sharpe_daily,
        n_obs=sel_perf.days,
        skew=sel_perf.skew,
        kurtosis=sel_perf.kurtosis,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
    )
    pbo = probability_of_backtest_overfitting(matrix)

    gates = [
        Gate("G1", f"Deflated Sharpe > {DSR_GATE} (N = {n_trials})", dsr, dsr > DSR_GATE),
        Gate("G2", f"PBO < {PBO_GATE}", pbo, pbo < PBO_GATE),
        Gate("G3", f"t > {T_GATE}", sel_perf.t_stat, sel_perf.t_stat > T_GATE),
        Gate(
            "G4",
            f"Sharpe > B1 ({bench_perf.sharpe:.2f}) y CAGR > {STABLECOIN_HURDLE:.0%}",
            sel_perf.sharpe,
            sel_perf.sharpe > bench_perf.sharpe and sel_perf.cagr > STABLECOIN_HURDLE,
        ),
    ]

    sel_results = results[selected]
    decomposition = {
        "funding": sum(r.funding_pnl for r in sel_results),
        "precio": sum(r.price_pnl for r in sel_results),
        "costes": -sum(r.costs for r in sel_results),
        "ciclos": float(sum(r.cycles for r in sel_results)),
        "tiempo_invertido": sum(r.hours_invested for r in sel_results)
        / max(sum(r.hours_total for r in sel_results), 1),
    }
    maker_frame, _ = run_config(data, configs[selected], MAKER_COSTS)
    idle = 1 - decomposition["tiempo_invertido"]
    sensitivity = {
        "sharpe_maker": performance(maker_frame["ret"].to_numpy()).sharpe,
        # Aproximación: el efectivo ocioso medio rinde un 4 % anual.
        "sharpe_efectivo_4pct": sharpe_daily(sel_returns + idle * STABLECOIN_HURDLE / DAYS_PER_YEAR)
        * math.sqrt(DAYS_PER_YEAR),
    }
    return HypothesisEvaluation(
        hypothesis=hypothesis,
        symbols=tuple(d.symbol for d in data),
        returns={n: matrix[:, j] for j, n in enumerate(names)},
        dates=[str(d) for d in aligned["date"].to_list()],
        cpcv_mean_sharpe=cpcv_mean,
        selected=selected,
        selected_performance=sel_perf,
        benchmark=bench_perf,
        benchmark_returns=bench_returns,
        pbo=pbo,
        dsr=dsr,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
        gates=gates,
        decomposition=decomposition,
        sensitivity=sensitivity,
    )


def _splits(n_obs: int) -> list[Split]:
    return cpcv_splits(n_obs, n_groups=6, n_test_groups=2, purge=8, embargo=0.01)
