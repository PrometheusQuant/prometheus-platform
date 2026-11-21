"""Evaluación de la Estrategia 2, tendencia, en el periodo de desarrollo (PQ-68).

Ejecuta exactamente lo pre-registrado (``docs/estrategias/02-tendencia/pre-registro.md``, §5 a §8):

1. **Las 12 configuraciones** (T1 y T2, L por sigma*) con ``trend.run_and_register``: cada una deja
   su fila en el registro compartido **antes** de evaluarse, y N sale de ahí. Se ejecutan las dos
   hipótesis juntas para que N y V[SR] no dependan del orden en que se evalúan.
2. **CPCV** con 6 grupos y 2 de prueba (15 particiones), purge de 150 días y embargo del 1 %. Se
   elige la configuración con mejor Sharpe medio de prueba.
3. **PBO** por CSCV de 16 bloques sobre la matriz días por 6 configuraciones de cada hipótesis.
4. **Deflated Sharpe** con N = todos los ensayos de tendencia registrados (≥ 12) y V[SR] del
   registro; t-estadístico de la media diaria.
5. **Gates G1 a G4** contra B1 (comprar y mantener BTC y ETH al 50 % en spot) y B2 (4 % anual).
   B3 (la misma señal sin volatility targeting) solo se informa.

Los benchmarks y la sensibilidad de costes maker se calculan con ``trend.run_config`` y no se
registran: no eligen nada. **Nunca toca el holdout**: los datos se recortan al cargarlos y cada
simulación termina en ``HOLDOUT_START``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.backtest import MAIN_COSTS, MAKER_COSTS, CostModel
from prometheus_platform.research.carry_evaluation import (
    DSR_GATE,
    PBO_GATE,
    STABLECOIN_HURDLE,
    T_GATE,
    ExperimentRegistry,
    Gate,
    HypothesisEvaluation,
    TrialRecord,
)
from prometheus_platform.research.panel import hourly_prices, load_silver
from prometheus_platform.research.trend import (
    EVALUATION_START,
    FAMILY,
    L_GRID,
    SIGMA_GRID,
    Hypothesis,
    SymbolMarket,
    TrendConfig,
    run_and_register,
    run_config,
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

SYMBOLS = ("BTCUSDT", "ETHUSDT")  # §3
PRE_REGISTERED_TRIALS = len(Hypothesis) * len(L_GRID) * len(SIGMA_GRID)  # §5: N = 12
PURGE_DAYS = 150  # §8: ventana máxima de 120 días más la volatilidad de 30
EMBARGO = 0.01
CSCV_BLOCKS = 16


@dataclass
class TrendEvaluation(HypothesisEvaluation):
    """La evaluación del carry más lo que el pre-registro de tendencia pide informar (§8)."""

    b3_name: str = ""
    b3: Performance | None = None
    secondary: dict[str, float] = field(default_factory=dict)


def load_market(silver_root: Path, symbol: str) -> SymbolMarket:
    """Velas y funding del silver, **recortados al desarrollo** antes de nada.

    La vela que abre a las 23:00 del 30-06 se conserva: cierra en ``HOLDOUT_START`` y da la última
    valoración del desarrollo. La liquidación de ``HOLDOUT_START`` ya es del holdout (KE-014).
    """
    spot, perp, funding = load_silver(silver_root, symbol)
    hourly = hourly_prices(spot, perp).filter(pl.col("open_time") < HOLDOUT_START)
    settlements = funding.filter(pl.col("funding_time") < HOLDOUT_START).select(
        "funding_time", "funding_rate"
    )
    return SymbolMarket(symbol, hourly, settlements)


class _Capture:
    """Pasa cada ensayo al registro y guarda una copia para el informe."""

    def __init__(self, registry: ExperimentRegistry) -> None:
        self._registry = registry
        self.familia = getattr(registry, "familia", FAMILY)
        self.logged: dict[str, TrialRecord] = {}

    def log_trial(self, trial: TrialRecord) -> None:
        self._registry.log_trial(trial)  # primero el registro: si falla, el ensayo no se usa
        self.logged[trial.name] = trial

    def trials(self) -> list[TrialRecord]:
        return self._registry.trials()


def configs(hypothesis: Hypothesis) -> list[TrendConfig]:
    return [TrendConfig(lookback, sigma, hypothesis) for lookback in L_GRID for sigma in SIGMA_GRID]


def evaluate_family(
    data: Sequence[SymbolMarket],
    registry: ExperimentRegistry,
    *,
    costs: CostModel = MAIN_COSTS,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
) -> dict[Hypothesis, TrendEvaluation]:
    """Registra las 12 configuraciones y evalúa T1 y T2 con el N resultante."""
    capture = _Capture(registry)
    daily: dict[str, pl.DataFrame] = {}
    for hypothesis in Hypothesis:
        for config in configs(hypothesis):
            daily[config.name] = run_and_register(
                data, config, costs, capture, costs_label="principal", start=start, end=end
            )
    trials = registry.trials()
    n_trials = max(len(trials), PRE_REGISTERED_TRIALS)
    sharpes = np.array([t.metrics["sharpe_daily"] for t in trials if "sharpe_daily" in t.metrics])
    var_sharpe = float(np.var(sharpes, ddof=1)) if sharpes.size > 1 else 0.0

    b1_frame, _ = run_config(
        data, TrendConfig(1, 1.0, buy_and_hold=True), costs, start=start, end=end
    )
    return {
        h: _evaluate(
            h,
            data,
            {c.name: daily[c.name] for c in configs(h)},
            capture.logged,
            b1_frame,
            n_trials=n_trials,
            var_sharpe=var_sharpe,
            costs=costs,
            window=(start, end),
        )
        for h in Hypothesis
    }


def _evaluate(  # noqa: PLR0913 - keyword-only salvo los datos de la hipótesis
    hypothesis: Hypothesis,
    data: Sequence[SymbolMarket],
    daily: dict[str, pl.DataFrame],
    logged: dict[str, TrialRecord],
    b1_frame: pl.DataFrame,
    *,
    n_trials: int,
    var_sharpe: float,
    costs: CostModel,
    window: tuple[datetime, datetime],
) -> TrendEvaluation:
    names = sorted(daily)
    aligned = daily[names[0]].select("date", pl.col("ret").alias(names[0]))
    for name in names[1:]:
        aligned = aligned.join(daily[name].select("date", pl.col("ret").alias(name)), on="date")
    matrix = aligned.select(names).to_numpy()
    test_sharpes = cpcv_test_sharpes(matrix, splits(matrix.shape[0]))
    cpcv_mean = {n: float(test_sharpes[:, j].mean()) for j, n in enumerate(names)}
    selected = max(names, key=lambda n: (cpcv_mean[n], n))  # empate: orden estable por nombre
    sel_returns = matrix[:, names.index(selected)]
    sel_perf = performance(sel_returns)

    b1_aligned = aligned.select("date").join(b1_frame, on="date", how="left")
    b1_returns = b1_aligned["ret"].fill_null(0.0).to_numpy()
    b1_perf = performance(b1_returns)

    dsr = deflated_sharpe_ratio(
        sel_perf.sharpe_daily,
        n_obs=sel_perf.days,
        skew=sel_perf.skew,
        kurtosis=sel_perf.kurtosis,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
    )
    pbo = probability_of_backtest_overfitting(matrix, n_blocks=CSCV_BLOCKS)
    gates = [
        Gate("G1", f"Deflated Sharpe > {DSR_GATE} (N = {n_trials})", dsr, dsr > DSR_GATE),
        Gate("G2", f"PBO < {PBO_GATE}", pbo, pbo < PBO_GATE),
        Gate("G3", f"t > {T_GATE}", sel_perf.t_stat, sel_perf.t_stat > T_GATE),
        Gate(
            "G4",
            f"Sharpe > B1 ({b1_perf.sharpe:.2f}) y CAGR > {STABLECOIN_HURDLE:.0%}",
            sel_perf.sharpe,
            sel_perf.sharpe > b1_perf.sharpe and sel_perf.cagr > STABLECOIN_HURDLE,
        ),
    ]

    chosen = next(c for c in configs(hypothesis) if c.name == selected)
    start, end = window
    b3_config = TrendConfig(chosen.lookback, chosen.sigma_target, hypothesis, vol_targeting=False)
    b3_frame, _ = run_config(data, b3_config, costs, start=start, end=end)
    b3_returns = aligned.select("date").join(b3_frame, on="date", how="left")["ret"]
    metrics = logged[selected].metrics
    maker_frame, _ = run_config(data, chosen, MAKER_COSTS, start=start, end=end)
    idle = 1 - metrics["tiempo_invertido"]
    return TrendEvaluation(
        hypothesis=str(hypothesis),
        symbols=tuple(d.symbol for d in data),
        returns={n: matrix[:, j] for j, n in enumerate(names)},
        dates=[str(d) for d in aligned["date"].to_list()],
        cpcv_mean_sharpe=cpcv_mean,
        selected=selected,
        selected_performance=sel_perf,
        benchmark=b1_perf,
        benchmark_returns=b1_returns,
        pbo=pbo,
        dsr=dsr,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
        gates=gates,
        decomposition={
            "precio": metrics["pnl_precio"],
            "funding": metrics["pnl_funding"],
            "costes": -metrics["costes"],
            "tiempo_invertido": metrics["tiempo_invertido"],
        },
        sensitivity={
            "sharpe_maker": performance(maker_frame["ret"].to_numpy()).sharpe,
            # Aproximación: el efectivo ocioso medio rinde un 4 % anual (§4, solo sensibilidad).
            "sharpe_efectivo_4pct": sharpe_daily(
                sel_returns + idle * STABLECOIN_HURDLE / DAYS_PER_YEAR
            )
            * math.sqrt(DAYS_PER_YEAR),
        },
        b3_name=b3_config.name,
        b3=performance(b3_returns.fill_null(0.0).to_numpy()),
        secondary={
            "sigma_objetivo": chosen.sigma_target,
            "vol_realizada": metrics["vol_realizada"],
            "rotacion_anual": metrics["rotacion_anual"],
            "peor_dia": metrics["peor_dia"],
            "tiempo_invertido": metrics["tiempo_invertido"],
        },
    )


def splits(n_obs: int) -> list[Split]:
    return cpcv_splits(n_obs, n_groups=6, n_test_groups=2, purge=PURGE_DAYS, embargo=EMBARGO)
