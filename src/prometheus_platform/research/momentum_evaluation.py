"""Evaluación del momentum transversal en el periodo de desarrollo (PQ-114).

Ejecuta exactamente lo pre-registrado (``docs/estrategias/03-momentum-transversal/pre-registro.md``,
§5 a §8):

1. **Las 6 configuraciones** (X1 y X2, L de 7, 14 y 28 días) con ``momentum.run_and_register``:
   cada una deja su fila en el registro compartido **antes** de evaluarse. Se ejecutan las dos
   hipótesis juntas para que N y V[SR] no dependan del orden.
2. **CPCV** con 6 grupos y 2 de prueba, purge de 35 días y embargo del 1 %. Se elige la L con mejor
   Sharpe medio de prueba, por hipótesis.
3. **PBO** por CSCV de 16 bloques sobre la matriz días por 3 configuraciones de cada hipótesis.
4. **Deflated Sharpe** con N = todos los ensayos de la familia ``tendencia`` registrados.
5. **Gates G1 a G4.** G4 de X1: CAGR neto > 4 %. G4 de X2: Sharpe neto > B1 y CAGR neto > 4 %.

Siempre informa el drawdown, el peor mes, la rotación, la descomposición en precio, funding y
costes, la sensibilidad maker y la correlación diaria con el carry H2 y con la tendencia (§8).
**Nunca toca el holdout**: los datos se recortan al cargarlos y la simulación termina en
``HOLDOUT_START``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

from prometheus_platform.data_platform.silver import silver_path
from prometheus_platform.domain.datasets import DatasetKind, Market
from prometheus_platform.domain.protocol import HOLDOUT_START
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
from prometheus_platform.research.momentum import (
    EVALUATION_START,
    L_GRID,
    MAKER_COSTS,
    Hypothesis,
    MomentumConfig,
    MomentumCosts,
    SymbolMarket,
    run_and_register,
    run_config,
)
from prometheus_platform.research.validation import (
    Split,
    cpcv_splits,
    cpcv_test_sharpes,
    deflated_sharpe_ratio,
    performance,
    probability_of_backtest_overfitting,
)

PRE_REGISTERED_TRIALS = len(Hypothesis) * len(L_GRID)  # §5: 6
PURGE_DAYS = 35  # §8: la ventana máxima de 28 días más la semana de tenencia
EMBARGO = 0.01
CSCV_BLOCKS = 16


@dataclass
class MomentumEvaluation(HypothesisEvaluation):
    """La evaluación común más lo que el pre-registro del momentum pide informar (§8)."""

    secondary: dict[str, float] = field(default_factory=dict)
    correlations: dict[str, float | None] = field(default_factory=dict)


def load_market(silver_root: Path, symbol: str, *, until: datetime = HOLDOUT_START) -> SymbolMarket:
    """Velas del perpetuo y funding del silver, **recortados a ``until``** antes de nada."""
    perp = pl.read_parquet(silver_path(silver_root, DatasetKind.KLINES, symbol, Market.USDM, "1h"))
    funding = pl.read_parquet(silver_path(silver_root, DatasetKind.FUNDING_RATE, symbol))
    hourly = perp.filter(pl.col("open_time") < until).select("open_time", "open", "close")
    settlements = funding.filter(pl.col("funding_time") < until).select(
        "funding_time", "funding_rate"
    )
    return SymbolMarket(symbol, hourly, settlements)


class _Capture:
    """Pasa cada ensayo al registro y guarda una copia para el informe."""

    def __init__(self, registry: ExperimentRegistry) -> None:
        self._registry = registry
        self.familia = getattr(registry, "familia", "tendencia")
        self.logged: dict[str, TrialRecord] = {}

    def log_trial(self, trial: TrialRecord) -> None:
        self._registry.log_trial(trial)  # primero el registro: si falla, el ensayo no se usa
        self.logged[trial.name] = trial

    def trials(self) -> list[TrialRecord]:
        return self._registry.trials()


def configs(hypothesis: Hypothesis) -> list[MomentumConfig]:
    return [MomentumConfig(lookback, hypothesis) for lookback in L_GRID]


def splits(n_obs: int) -> list[Split]:
    return cpcv_splits(n_obs, n_groups=6, n_test_groups=2, purge=PURGE_DAYS, embargo=EMBARGO)


def evaluate_family(  # noqa: PLR0913 - keyword-only salvo los datos
    data: Sequence[SymbolMarket],
    registry: ExperimentRegistry,
    *,
    costs: MomentumCosts,
    others: Mapping[str, pl.DataFrame] | None = None,
    start: datetime = EVALUATION_START,
    end: datetime = HOLDOUT_START,
) -> dict[Hypothesis, MomentumEvaluation]:
    """Registra las 6 configuraciones y evalúa X1 y X2 con el N resultante.

    ``others``: retornos diarios (``date``, ``ret``) de otras estrategias, para las correlaciones.
    """
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
        data, MomentumConfig(1, equal_weight=True), costs, start=start, end=end
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
            others=others or {},
            window=(start, end),
        )
        for h in Hypothesis
    }


def worst_month(dates: Sequence[datetime], returns: np.ndarray) -> float:
    """Peor mes calendario. Cada fecha es el cierre del día: su retorno es del día anterior."""
    frame = pl.DataFrame({"date": list(dates), "ret": returns})
    day = pl.col("date") - pl.duration(days=1)
    monthly = frame.group_by(day.dt.strftime("%Y-%m")).agg(
        ((1 + pl.col("ret")).product() - 1).alias("m")
    )
    worst = monthly["m"].min()
    return float(worst) if isinstance(worst, int | float) else float("nan")


def correlation(aligned: pl.DataFrame, returns: np.ndarray, other: pl.DataFrame) -> float | None:
    """Correlación diaria en los días comunes; ``None`` si hay menos de 30."""
    joined = (
        aligned.select(pl.col("date").cast(pl.Date))
        .with_columns(pl.Series("x", returns))
        .join(other.select("date", pl.col("ret").alias("y")), on="date", how="inner")
        .drop_nulls()
    )
    if joined.height < 30:
        return None
    return float(np.corrcoef(joined["x"].to_numpy(), joined["y"].to_numpy())[0, 1])


def _evaluate(  # noqa: PLR0913 - keyword-only salvo los datos de la hipótesis
    hypothesis: Hypothesis,
    data: Sequence[SymbolMarket],
    daily: dict[str, pl.DataFrame],
    logged: dict[str, TrialRecord],
    b1_frame: pl.DataFrame,
    *,
    n_trials: int,
    var_sharpe: float,
    others: Mapping[str, pl.DataFrame],
    window: tuple[datetime, datetime],
) -> MomentumEvaluation:
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

    b1_joined = aligned.select("date").join(b1_frame, on="date", how="left")
    b1_returns = b1_joined["ret"].fill_null(0.0).to_numpy()
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
    if hypothesis is Hypothesis.X1:
        g4 = Gate(
            "G4",
            f"CAGR > {STABLECOIN_HURDLE:.0%}",
            sel_perf.cagr,
            sel_perf.cagr > STABLECOIN_HURDLE,
        )
    else:
        g4 = Gate(
            "G4",
            f"Sharpe > B1 ({b1_perf.sharpe:.2f}) y CAGR > {STABLECOIN_HURDLE:.0%}",
            sel_perf.sharpe,
            sel_perf.sharpe > b1_perf.sharpe and sel_perf.cagr > STABLECOIN_HURDLE,
        )
    gates = [
        Gate("G1", f"Deflated Sharpe > {DSR_GATE} (N = {n_trials})", dsr, dsr > DSR_GATE),
        Gate("G2", f"PBO < {PBO_GATE}", pbo, pbo < PBO_GATE),
        Gate("G3", f"t > {T_GATE}", sel_perf.t_stat, sel_perf.t_stat > T_GATE),
        g4,
    ]

    chosen = next(c for c in configs(hypothesis) if c.name == selected)
    start, end = window
    maker_frame, _ = run_config(data, chosen, MAKER_COSTS, start=start, end=end)
    metrics = logged[selected].metrics
    dates = aligned["date"].to_list()
    return MomentumEvaluation(
        hypothesis=str(hypothesis),
        symbols=tuple(d.symbol for d in data),
        returns={n: matrix[:, j] for j, n in enumerate(names)},
        dates=[str(d) for d in dates],
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
        },
        sensitivity={"sharpe_maker": performance(maker_frame["ret"].to_numpy()).sharpe},
        secondary={
            "L": float(chosen.lookback),
            "peor_mes": worst_month(dates, sel_returns),
            "peor_dia": metrics["peor_dia"],
            "rotacion_anual": metrics["rotacion_anual"],
            "vol_realizada": metrics["vol_realizada"],
            "deslistados": metrics["deslistados"],
            "lunes_incompletos": metrics["lunes_incompletos"],
        },
        correlations={
            name: correlation(aligned, sel_returns, frame) for name, frame in others.items()
        },
    )


def other_returns(research_dir: Path) -> dict[str, pl.DataFrame]:
    """Retornos diarios de la configuración elegida del carry H2 y de la tendencia T1 y T2."""
    out: dict[str, pl.DataFrame] = {}
    sources = (("carry H2", "carry/H2"), ("tendencia T1", "trend/T1"), ("tendencia T2", "trend/T2"))
    for label, sub in sources:
        summary_path = research_dir / sub / "summary.json"
        returns_path = research_dir / sub / "daily_returns.parquet"
        if not summary_path.exists() or not returns_path.exists():
            continue
        selected = json.loads(summary_path.read_text(encoding="utf-8")).get("selected")
        frame = pl.read_parquet(returns_path)
        if selected not in frame.columns:
            continue
        out[label] = frame.select(
            pl.col("date").cast(pl.String).str.slice(0, 10).str.to_date().alias("date"),
            pl.col(selected).alias("ret"),
        )
    return out
