"""Overlay de sentimiento sobre el momentum transversal (PQ-128).

Ejecuta lo pre-registrado en ``docs/estrategias/05-sentimiento/pre-registro.md``:

- **Filtro (§3 y §4):** en el rebalanceo del lunes D, si el último valor del Crypto Fear & Greed
  Index conocido a las 00:00 UTC de D es ≤ 25 (miedo extremo), la cartera pasa a efectivo esa
  semana. Conocido = ``knowledge_time`` ≤ D 00:00; como el valor del día X se conoce a la 01:00 de
  X, el último conocido es el del domingo. Si el último conocido tiene más de 7 días, la semana va
  **sin filtro**.
- **Ensayos (§5):** S1 sobre X1 y S2 sobre X2, cada uno con la *L* que eligió la CPCV del momentum
  (PQ-114). Son 2 ensayos de la familia ``tendencia``, registrados antes de evaluar.
- **Evaluación (§8):** la misma CPCV del momentum; PBO sobre la base y el overlay; Deflated Sharpe
  con el N de la familia; G1 a G4 como la base y **G5**: el overlay bate a su base en el periodo
  completo y en la mediana de los caminos de prueba de la CPCV.

La base se recalcula con ``run_config`` y no se registra: ya es un ensayo de PQ-114.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research import momentum_evaluation as me
from prometheus_platform.research.carry_evaluation import (
    DSR_GATE,
    PBO_GATE,
    STABLECOIN_HURDLE,
    T_GATE,
    ExperimentRegistry,
    Gate,
    HypothesisEvaluation,
)
from prometheus_platform.research.momentum import (
    EVALUATION_START,
    MONDAY,
    Hypothesis,
    MomentumConfig,
    MomentumCosts,
    SymbolMarket,
    run_and_register,
    run_config,
)
from prometheus_platform.research.validation import (
    cpcv_test_sharpes,
    deflated_sharpe_ratio,
    performance,
    probability_of_backtest_overfitting,
)

EXTREME_FEAR = 25  # §3: límite de la propia clasificación de la fuente
MAX_AGE = timedelta(days=7)  # §3: con un valor más viejo, la semana va sin filtro
OVERLAYS: dict[str, Hypothesis] = {"S1": Hypothesis.X1, "S2": Hypothesis.X2}


def mondays(start: datetime, end: datetime) -> list[datetime]:
    """Lunes 00:00 UTC en ``[start, end)``."""
    day = start
    while day.weekday() != MONDAY:
        day += timedelta(days=1)
    out = []
    while day < end:
        out.append(day)
        day += timedelta(days=7)
    return out


def out_mondays(fng: pl.DataFrame, decisions: Sequence[datetime]) -> frozenset[datetime]:
    """Lunes en efectivo: el último valor conocido a esa hora es ≤ 25 y tiene ≤ 7 días."""
    known = fng.sort("knowledge_time")
    times = known["knowledge_time"].to_list()
    values = known["value"].to_list()
    out = set()
    for at in decisions:
        i = bisect_right(times, at) - 1  # el último con knowledge_time ≤ la decisión
        if i < 0 or at - times[i] > MAX_AGE:
            continue  # sin dato reciente: la semana va sin filtro
        if values[i] <= EXTREME_FEAR:
            out.add(at)
    return frozenset(out)


@dataclass
class OverlayEvaluation(HypothesisEvaluation):
    base_name: str = ""
    base_returns: np.ndarray = field(default_factory=lambda: np.array([]))
    secondary: dict[str, float] = field(default_factory=dict)
    correlations: dict[str, float | None] = field(default_factory=dict)


def selected_lookback(research_dir: Path, hypothesis: Hypothesis) -> int:
    """La *L* que eligió la CPCV del momentum (PQ-114); nunca se vuelve a elegir (§5)."""
    path = research_dir / "momentum" / str(hypothesis) / "summary.json"
    name = json.loads(path.read_text(encoding="utf-8"))["selected"]
    prefix = f"{hypothesis}-L"
    if not name.startswith(prefix):
        raise ValueError(f"Configuración inesperada en {path}: {name}")
    return int(name.removeprefix(prefix))


def _week_mask(dates: Sequence[datetime], weeks: frozenset[datetime]) -> np.ndarray:
    """Días cuyo retorno cae en una semana en efectivo. Cada fecha es el cierre del día."""
    mask = np.zeros(len(dates), dtype=bool)
    for i, d in enumerate(dates):
        day = d - timedelta(days=1)  # el retorno etiquetado en d es del día anterior
        monday = (day - timedelta(days=day.weekday())).replace(hour=0, minute=0, second=0)
        mask[i] = monday in weeks
    return mask


def evaluate(  # noqa: PLR0913 - keyword-only salvo los datos
    data: Sequence[SymbolMarket],
    registry: ExperimentRegistry,
    fng: pl.DataFrame,
    *,
    lookbacks: Mapping[Hypothesis, int],
    costs: MomentumCosts,
    others: Mapping[str, pl.DataFrame] | None = None,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
) -> dict[str, OverlayEvaluation]:
    """Registra S1 y S2 y los evalúa con el N de la familia resultante."""
    out = out_mondays(fng, mondays(start, end))
    configs = {
        name: MomentumConfig(lookbacks[hyp], hyp, out=out, overlay=name)
        for name, hyp in OVERLAYS.items()
    }
    daily: dict[str, pl.DataFrame] = {}
    results = {}
    for name, config in configs.items():
        daily[name] = run_and_register(
            data, config, costs, registry, costs_label="principal", start=start, end=end
        )
        results[name] = run_config(data, config, costs, start=start, end=end)[1]
    trials = registry.trials()
    n_trials = len(trials)
    sharpes = np.array([t.metrics["sharpe_daily"] for t in trials if "sharpe_daily" in t.metrics])
    var_sharpe = float(np.var(sharpes, ddof=1)) if sharpes.size > 1 else 0.0
    b1_frame, _ = run_config(
        data, MomentumConfig(1, equal_weight=True), costs, start=start, end=end
    )
    evaluations = {}
    for name, config in configs.items():
        base_config = MomentumConfig(config.lookback, config.hypothesis)
        base_frame, base_result = run_config(data, base_config, costs, start=start, end=end)
        evaluations[name] = _evaluate(
            name,
            config,
            data=data,
            overlay_frame=daily[name],
            base_frame=base_frame,
            b1_frame=b1_frame,
            n_trials=n_trials,
            var_sharpe=var_sharpe,
            extra_costs=results[name].costs - base_result.costs,
            others=others or {},
        )
    return evaluations


def _evaluate(  # noqa: PLR0913 - keyword-only salvo la configuración
    name: str,
    config: MomentumConfig,
    *,
    data: Sequence[SymbolMarket],
    overlay_frame: pl.DataFrame,
    base_frame: pl.DataFrame,
    b1_frame: pl.DataFrame,
    n_trials: int,
    var_sharpe: float,
    extra_costs: float,
    others: Mapping[str, pl.DataFrame],
) -> OverlayEvaluation:
    base_name = MomentumConfig(config.lookback, config.hypothesis).name
    aligned = base_frame.select("date", pl.col("ret").alias(base_name)).join(
        overlay_frame.select("date", pl.col("ret").alias(name)), on="date"
    )
    matrix = aligned.select(base_name, name).to_numpy()
    base_returns, returns = matrix[:, 0], matrix[:, 1]
    test = cpcv_test_sharpes(matrix, me.splits(matrix.shape[0]))
    perf, base_perf = performance(returns), performance(base_returns)
    b1_returns = aligned.select("date").join(b1_frame, on="date", how="left")["ret"]
    b1_perf = performance(b1_returns.fill_null(0.0).to_numpy())
    dsr = deflated_sharpe_ratio(
        perf.sharpe_daily,
        n_obs=perf.days,
        skew=perf.skew,
        kurtosis=perf.kurtosis,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
    )
    pbo = probability_of_backtest_overfitting(matrix, n_blocks=me.CSCV_BLOCKS)
    if config.hypothesis is Hypothesis.X1:
        g4 = Gate("G4", f"CAGR > {STABLECOIN_HURDLE:.0%}", perf.cagr, perf.cagr > STABLECOIN_HURDLE)
    else:
        g4 = Gate(
            "G4",
            f"Sharpe > B1 ({b1_perf.sharpe:.2f}) y CAGR > {STABLECOIN_HURDLE:.0%}",
            perf.sharpe,
            perf.sharpe > b1_perf.sharpe and perf.cagr > STABLECOIN_HURDLE,
        )
    median_base, median_overlay = float(np.median(test[:, 0])), float(np.median(test[:, 1]))
    g5_passed = perf.sharpe > base_perf.sharpe and median_overlay > median_base
    gates = [
        Gate("G1", f"Deflated Sharpe > {DSR_GATE} (N = {n_trials})", dsr, dsr > DSR_GATE),
        Gate("G2", f"PBO < {PBO_GATE}", pbo, pbo < PBO_GATE),
        Gate("G3", f"t > {T_GATE}", perf.t_stat, perf.t_stat > T_GATE),
        g4,
        Gate(
            "G5",
            f"Sharpe > base ({base_perf.sharpe:.2f}) y mediana CPCV > base ({median_base:.2f})",
            perf.sharpe - base_perf.sharpe,
            g5_passed,
        ),
    ]
    dates = aligned["date"].to_list()
    weeks = config.out
    in_weeks = _week_mask(dates, weeks)
    decisions = mondays(dates[0] - timedelta(days=1), dates[-1])
    return OverlayEvaluation(
        hypothesis=name,
        symbols=tuple(d.symbol for d in data),
        returns={name: returns, base_name: base_returns},
        dates=[str(d) for d in dates],
        cpcv_mean_sharpe={base_name: float(test[:, 0].mean()), name: float(test[:, 1].mean())},
        selected=name,
        selected_performance=perf,
        benchmark=b1_perf,
        benchmark_returns=b1_returns.fill_null(0.0).to_numpy(),
        pbo=pbo,
        dsr=dsr,
        n_trials=n_trials,
        var_sharpe=var_sharpe,
        gates=gates,
        decomposition={},
        sensitivity={},
        base_name=base_name,
        base_returns=base_returns,
        secondary={
            "semanas_fuera": float(sum(1 for d in decisions if d in weeks)),
            "lunes_evaluados": float(len(decisions)),
            "retorno_base_en_semanas_fuera": float(np.prod(1 + base_returns[in_weeks]) - 1),
            "sharpe_base": base_perf.sharpe,
            "cagr_base": base_perf.cagr,
            "caida_max": perf.max_drawdown,
            "caida_max_base": base_perf.max_drawdown,
            "peor_mes": me.worst_month(dates, returns),
            "peor_mes_base": me.worst_month(dates, base_returns),
            "costes_extra": extra_costs,
            "mediana_cpcv": median_overlay,
            "mediana_cpcv_base": median_base,
        },
        correlations={
            label: me.correlation(aligned, returns, frame) for label, frame in others.items()
        },
    )
