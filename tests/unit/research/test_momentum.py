"""Momentum transversal (PQ-114): motor y evaluación, con datos sintéticos.

Ningún test usa datos reales: no son ensayos y no suman a N.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research import momentum as mo
from prometheus_platform.research import momentum_evaluation as me
from prometheus_platform.research.carry_evaluation import TrialRecord

from .test_trend import Registry

UTC = HOLDOUT_START.tzinfo
MONDAY = datetime(2024, 1, 1, tzinfo=UTC)  # el 2024-01-01 fue lunes
COSTS = mo.MomentumCosts(perp_fee=0.0005, slippage=0.0005)


def market(
    symbol: str,
    prices: np.ndarray,
    *,
    start: datetime,
    rate: float = 0.0,
    until: int | None = None,
) -> mo.SymbolMarket:
    """Velas horarias con ``open`` = ``close`` anterior; funding cada 8 h a ``rate``."""
    n = len(prices) if until is None else until
    times = [start + timedelta(hours=i) for i in range(n)]
    opens = np.concatenate([[prices[0]], prices[: n - 1]])
    hourly = pl.DataFrame(
        {"open_time": times, "open": opens[:n], "close": prices[:n]},
        schema={"open_time": pl.Datetime("ms", "UTC"), "open": pl.Float64, "close": pl.Float64},
    )
    funding_times = [
        t + timedelta(hours=1) for t in times if (t + timedelta(hours=1)).hour % 8 == 0
    ]
    settlements = pl.DataFrame(
        {"funding_time": funding_times, "funding_rate": [rate] * len(funding_times)},
        schema={"funding_time": pl.Datetime("ms", "UTC"), "funding_rate": pl.Float64},
    )
    return mo.SymbolMarket(symbol, hourly, settlements)


def trending(drift_per_day: float, days: int) -> np.ndarray:
    hours = np.arange(days * 24)
    return 100 * np.exp(drift_per_day / 24 * hours)


# --- Ranking y pesos ---------------------------------------------------------------------------


def closes_with_returns(returns: dict[str, float], lookback: int) -> dict[str, list[float]]:
    return {s: [100.0] * lookback + [100.0 * (1 + r)] for s, r in returns.items()}


def test_x1_is_long_the_top_third_and_short_the_bottom_third() -> None:
    returns = {"A": 0.30, "B": 0.20, "C": 0.10, "D": 0.0, "E": -0.10, "F": -0.20}
    weights = mo.target_weights(
        closes_with_returns(returns, 7), sorted(returns), mo.MomentumConfig(7)
    )
    assert weights == {"A": 0.25, "B": 0.25, "E": -0.25, "F": -0.25}
    assert sum(abs(w) for w in weights.values()) == pytest.approx(1.0)  # 1x bruto


def test_x2_is_long_only_with_one_x() -> None:
    returns = {"A": 0.30, "B": 0.20, "C": 0.10, "D": 0.0, "E": -0.10, "F": -0.20}
    config = mo.MomentumConfig(7, mo.Hypothesis.X2)
    assert mo.target_weights(closes_with_returns(returns, 7), sorted(returns), config) == {
        "A": 0.5,
        "B": 0.5,
    }


def test_ties_are_broken_by_symbol_and_short_histories_are_left_out() -> None:
    closes = closes_with_returns({"C": 0.1, "A": 0.1, "B": 0.1}, 7)
    closes["Z"] = [100.0, 150.0]  # sin L días de historia: no entra al ranking
    weights = mo.target_weights(closes, ["A", "B", "C", "Z"], mo.MomentumConfig(7))
    assert weights == {"A": 0.5, "C": -0.5}


def test_fewer_than_three_eligible_symbols_means_cash() -> None:
    closes = closes_with_returns({"A": 0.1, "B": -0.1}, 7)
    assert mo.target_weights(closes, ["A", "B"], mo.MomentumConfig(7)) == {}


def test_b1_is_the_whole_eligible_universe_long() -> None:
    closes = closes_with_returns({"A": 0.1, "B": -0.1, "C": 0.0, "D": 0.2}, 7)
    weights = mo.target_weights(closes, ["A", "B", "C"], mo.MomentumConfig(7, equal_weight=True))
    assert weights == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})


# --- Simulación --------------------------------------------------------------------------------


def universe(days: int = 60, rate: float = 0.0) -> list[mo.SymbolMarket]:
    start = MONDAY - timedelta(days=days - 28)
    drifts = {"AAA": 0.004, "BBB": 0.002, "CCC": 0.0, "DDD": -0.001, "EEE": -0.002, "FFF": -0.004}
    return [market(s, trending(d, days), start=start, rate=rate) for s, d in drifts.items()]


def run(data: list[mo.SymbolMarket], config: mo.MomentumConfig, **kw: object) -> mo.MomentumResult:
    end = MONDAY + timedelta(days=28)
    return mo.simulate(
        data,
        config=config,
        costs=COSTS,
        start=MONDAY,
        end=end,
        **kw,  # type: ignore[arg-type]
    )


def test_rebalances_only_on_mondays_and_pays_costs() -> None:
    result = run(universe(), mo.MomentumConfig(7))
    assert result.rebalances == 4  # cuatro lunes en 28 días
    assert result.costs > 0
    assert result.traded_notional > 0
    assert result.daily_equity["date"][0] == MONDAY
    # X1 neutral en dólares con tendencias limpias: gana la pata larga y la corta.
    assert result.daily_equity["equity"][-1] > 1.0


def test_longs_pay_and_shorts_collect_positive_funding() -> None:
    flat = mo.simulate(
        universe(rate=0.0),
        config=mo.MomentumConfig(7, mo.Hypothesis.X2),
        costs=COSTS,
        start=MONDAY,
        end=MONDAY + timedelta(days=14),
    )
    paid = mo.simulate(
        universe(rate=0.001),
        config=mo.MomentumConfig(7, mo.Hypothesis.X2),
        costs=COSTS,
        start=MONDAY,
        end=MONDAY + timedelta(days=14),
    )
    assert flat.funding_pnl == 0.0
    assert paid.funding_pnl < 0  # X2 solo larga: siempre paga con tasa positiva


def test_the_decision_does_not_look_ahead() -> None:
    """Cambiar los precios desde el lunes 01:00 no cambia lo que se decidió el lunes a las 00:00."""
    base = universe()
    shocked = []
    for m in base:
        h = m.hourly.with_columns(
            pl.when(pl.col("open_time") >= MONDAY + timedelta(hours=1))
            .then(pl.col("close") * (3.0 if m.symbol == "FFF" else 1.0))
            .otherwise(pl.col("close"))
            .alias("close")
        )
        shocked.append(mo.SymbolMarket(m.symbol, h, m.settlements))
    config = mo.MomentumConfig(7)
    end = MONDAY + timedelta(hours=2)
    a = mo.simulate(base, config=config, costs=COSTS, start=MONDAY - timedelta(days=1), end=end)
    b = mo.simulate(shocked, config=config, costs=COSTS, start=MONDAY - timedelta(days=1), end=end)
    assert a.traded_notional == pytest.approx(b.traded_notional, rel=1e-9)


def test_a_delisted_symbol_is_closed_and_never_replaced() -> None:
    data = universe()
    start = data[0].hourly["open_time"][0]
    cut = int((MONDAY + timedelta(days=9) - start).total_seconds() // 3600)
    data[0] = market("AAA", trending(0.004, 60), start=start, until=cut)  # deja de cotizar
    result = run(data, mo.MomentumConfig(7))
    assert [s for s, _ in result.delisted] == ["AAA"]


def test_the_development_cannot_read_the_holdout() -> None:
    with pytest.raises(ValueError, match="holdout"):
        mo.simulate(
            universe(),
            config=mo.MomentumConfig(7),
            costs=COSTS,
            start=MONDAY,
            end=HOLDOUT_START + timedelta(days=1),
        )


def test_main_costs_charge_ten_basis_points_on_the_low_volume_symbols() -> None:
    costs = mo.main_costs(["DOTUSDT"])
    assert costs.rate("DOTUSDT") == pytest.approx(0.0015)
    assert costs.rate("BTCUSDT") == pytest.approx(0.0010)


def test_benchmarks_are_not_registered_and_trials_go_to_the_trend_family() -> None:
    with pytest.raises(ValueError, match="benchmark"):
        mo.run_and_register(
            universe(),
            mo.MomentumConfig(1, equal_weight=True),
            COSTS,
            Registry(),
            costs_label="principal",
        )
    with pytest.raises(ValueError, match="familia"):
        mo.run_and_register(
            universe(), mo.MomentumConfig(7), COSTS, Registry("carry"), costs_label="principal"
        )


# --- Evaluación --------------------------------------------------------------------------------

EVAL_DAYS = 160
EVAL_START = HOLDOUT_START - timedelta(days=EVAL_DAYS - 35)


def noisy_universe() -> list[mo.SymbolMarket]:
    start = HOLDOUT_START - timedelta(days=EVAL_DAYS)
    out = []
    for seed, symbol in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]):
        rng = np.random.default_rng(seed)
        prices = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.004, EVAL_DAYS * 24)))
        out.append(market(symbol, prices, start=start, rate=0.0001))
    return out


@pytest.fixture(scope="module")
def evaluated() -> tuple[Registry, dict[mo.Hypothesis, me.MomentumEvaluation]]:
    registry = Registry()
    registry.log_trial(TrialRecord("T1", "tendencia-previa", metrics={"sharpe_daily": 0.02}))
    days = pl.datetime_range(
        EVAL_START, HOLDOUT_START, interval="1d", eager=True, time_zone="UTC"
    ).dt.date()
    other = pl.DataFrame({"date": days, "ret": np.linspace(-0.01, 0.01, len(days))})
    return registry, me.evaluate_family(
        noisy_universe(), registry, costs=COSTS, others={"otra": other}, start=EVAL_START
    )


def test_registers_the_six_configurations_and_counts_the_whole_family(
    evaluated: tuple[Registry, dict[mo.Hypothesis, me.MomentumEvaluation]],
) -> None:
    registry, evaluations = evaluated
    names = [t.name for t in registry.items[1:]]
    assert names == ["X1-L7", "X1-L14", "X1-L28", "X2-L7", "X2-L14", "X2-L28"]
    for evaluation in evaluations.values():
        assert evaluation.n_trials == 7  # las 6 más la de tendencia ya registrada
        assert [g.name for g in evaluation.gates] == ["G1", "G2", "G3", "G4"]
        assert evaluation.selected in evaluation.cpcv_mean_sharpe
        assert set(evaluation.decomposition) == {"precio", "funding", "costes"}
        assert "otra" in evaluation.correlations


def test_x1_and_x2_have_their_own_g4(
    evaluated: tuple[Registry, dict[mo.Hypothesis, me.MomentumEvaluation]],
) -> None:
    _, evaluations = evaluated
    assert "B1" not in evaluations[mo.Hypothesis.X1].gates[3].criterion
    assert "B1" in evaluations[mo.Hypothesis.X2].gates[3].criterion


def test_evaluation_never_reaches_the_holdout(
    evaluated: tuple[Registry, dict[mo.Hypothesis, me.MomentumEvaluation]],
) -> None:
    _, evaluations = evaluated
    for evaluation in evaluations.values():
        assert max(evaluation.dates) <= str(HOLDOUT_START)


def test_cpcv_purges_35_days() -> None:
    splits = me.splits(600)
    assert len(splits) == 15  # 6 grupos, 2 de prueba


def test_worst_month_compounds_the_daily_returns() -> None:
    dates = [datetime(2024, 1, d, tzinfo=UTC) for d in (1, 2)] + [datetime(2024, 2, 1, tzinfo=UTC)]
    assert me.worst_month(dates, np.array([-0.1, -0.1, 0.05])) == pytest.approx(-0.19)


def test_cli_registers_in_the_ticket_lane_and_writes_both_hypotheses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "boris")
    data = {m.symbol: m for m in noisy_universe()}
    universe_file = tmp_path / cli.MOMENTUM_UNIVERSE_FILE
    universe_file.parent.mkdir(parents=True)
    universe_file.write_text(
        json.dumps({"universo": sorted(data), "menor_volumen_10pb": ["FFF"]}), encoding="utf-8"
    )
    monkeypatch.setattr(me, "load_market", lambda _root, symbol: data[symbol])
    monkeypatch.setattr(me, "evaluate_family", partial(me.evaluate_family, start=EVAL_START))

    assert cli.main(["research", "momentum"]) == 0
    out = capsys.readouterr().out
    assert "X1: elegida=X1-L" in out
    assert "X2: elegida=X2-L" in out
    structlog.reset_defaults()

    for hypothesis in ("X1", "X2"):
        summary = json.loads(
            (tmp_path / f"lake/research/momentum/{hypothesis}/summary.json").read_text()
        )
        assert summary["n_trials"] == 6
        assert "peor_mes" in summary["secondary"]
        assert "correlations" in summary
    rows = list(read_rows(tmp_path / "docs/estrategias/ensayos"))
    assert len(rows) == 6
    assert {r.carril for r in rows} == {"boris"}
    assert {r.familia for r in rows} == {"tendencia"}
