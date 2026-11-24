"""Vista de cartera multiestrategia (PQ-84): capital, PnL y CVaR por estrategia, y bandas."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from streamlit.testing.v1 import AppTest
from tests.contract.example_strategies import BTC

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.dashboard import portfolio, style
from prometheus_platform.api.paper.report import StrategyRow, build_view, strategy_breakdown
from prometheus_platform.domain.events import PortfolioValued
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.portfolio_risk.budget import bootstrap_bands, cvar95, cvar_contributions
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

from .test_dashboard import APP
from .test_strategy_executor import BTC_PRICE, CARRY, Rig, at

D = Decimal
SPOT, PERP = spot_instrument(CARRY), perp_instrument(CARRY)


def test_marks_survive_the_journal_and_old_lines_still_parse(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "diario.jsonl")
    marks = {SPOT: D("160.5"), PERP: D("160.4"), BTC: D(200)}
    journal.append(
        PortfolioValued(
            occurred_at=datetime(2026, 11, 1, tzinfo=UTC),
            equity=D(1000),
            cash=D(1000),
            gross_notional=D(0),
            marks=PortfolioValued.encode_marks(marks),
        )
    )
    old = json.loads((tmp_path / "diario.jsonl").read_text().splitlines()[0])
    del old["marks"]  # así eran los diarios antes de PQ-84
    with (tmp_path / "diario.jsonl").open("a") as fh:
        fh.write(json.dumps(old) + "\n")
    new, legacy = journal.replay()
    assert isinstance(new, PortfolioValued)
    assert isinstance(legacy, PortfolioValued)
    assert new.mark_prices() == marks
    assert legacy.mark_prices() == {}


def test_a_line_missing_a_required_field_is_still_corrupt(tmp_path: Path) -> None:
    from prometheus_platform.adapters.jsonl_journal import JournalCorruptError  # noqa: PLC0415

    journal = JsonlEventJournal(tmp_path / "diario.jsonl")
    journal.append(
        PortfolioValued(
            occurred_at=datetime(2026, 11, 1, tzinfo=UTC),
            equity=D(1),
            cash=D(1),
            gross_notional=D(0),
        )
    )
    line = json.loads((tmp_path / "diario.jsonl").read_text())
    for required in ("event_id", "equity"):
        broken = {k: v for k, v in line.items() if k != required}
        (tmp_path / "roto.jsonl").write_text(json.dumps(broken) + "\n")
        with pytest.raises(JournalCorruptError):
            list(JsonlEventJournal(tmp_path / "roto.jsonl").replay())
    (tmp_path / "roto.jsonl").write_text(json.dumps({**line, "desconocido": 1}) + "\n")
    with pytest.raises(JournalCorruptError):
        list(JsonlEventJournal(tmp_path / "roto.jsonl").replay())


def run_rig(tmp_path: Path) -> Rig:
    """Carry y SmaTrend operando; luego el precio de BTC sube un 5 %."""
    rig = Rig(tmp_path)
    high = D("0.0003")
    from prometheus_platform.domain.model import FundingRate  # noqa: PLC0415

    rig.market.funding[CARRY] = [
        FundingRate(instrument=PERP, funding_time=t, rate=high)
        for t in (at(0, 0) - timedelta(hours=16), at(0, 0) - timedelta(hours=8), at(0, 0))
    ]
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    rig.market.price["BTCUSDT"] = (BTC_PRICE * D("1.05"),) * 2
    rig.market.funding[CARRY].append(FundingRate(instrument=PERP, funding_time=at(8, 0), rate=high))
    rig.tick_at(at(8, 30))
    return rig


def test_strategy_pnl_adds_up_to_the_portfolio_pnl(tmp_path: Path) -> None:
    rig = run_rig(tmp_path)
    view = build_view(rig.journal.replay())
    rows = {r.strategy: r for r in strategy_breakdown(view)}
    assert set(rows) == {"carry-h2", "sma-ejemplo"}
    assert all(not r.approximate for r in rows.values())
    total = sum((r.pnl for r in rows.values()), D(0))
    assert view.equity is not None
    assert view.initial_equity is not None
    assert total == pytest.approx(view.equity - view.initial_equity, abs=D("1e-9"))
    assert rows["carry-h2"].funding > 0  # cobró la liquidación de las 08:00
    assert rows["sma-ejemplo"].funding == 0
    btc = rig.broker.positions()[BTC]
    assert rows["sma-ejemplo"].exposure == pytest.approx(btc * BTC_PRICE * D("1.05"))
    assert rows["sma-ejemplo"].pnl > 0  # subió un 5 %


def test_positions_without_marks_are_valued_at_the_last_fill(tmp_path: Path) -> None:
    rig = run_rig(tmp_path)
    view = build_view(rig.journal.replay())
    view.marks.clear()  # como un diario anterior a PQ-84
    assert all(r.approximate for r in strategy_breakdown(view))


def test_an_instrument_without_signals_belongs_to_the_runner_of_its_symbol(tmp_path: Path) -> None:
    """El carry que aún no operó: su funding es suyo, no «sin asignar»."""
    from prometheus_platform.domain.events import FundingSettled, RunnerStarted  # noqa: PLC0415

    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    events = [
        RunnerStarted(
            occurred_at=t0, broker="simulado", strategy_id="carry-h2", symbols="SOLUSDT", params=""
        ),
        FundingSettled(
            occurred_at=t0,
            symbol="SOLUSDT",
            funding_time=t0,
            rate=D(0),
            interval_hours=8,
            amount=D(0),
            action="mantener",
            s_k="",
            target_open=False,
            was_open=False,
            rebalance=False,
        ),
    ]
    (only,) = strategy_breakdown(build_view(events))
    assert only.strategy == "carry-h2"


def row(strategy: str, exposure: str) -> StrategyRow:
    return StrategyRow(strategy, "BINANCE", D(exposure), D(0), D(0), D(0), approximate=False)


def test_paper_weights_count_the_hedged_carry_once() -> None:
    weights = portfolio.paper_weights(
        [row("carry-h2", "980"), row("sma-ejemplo", "200"), row("sin asignar", "5")], D(1000)
    )
    assert weights == {"carry-h2": pytest.approx(0.49), "sma-ejemplo": pytest.approx(0.2)}
    assert portfolio.paper_weights([row("carry-h2", "980")], D(0)) == {}


BUDGET = {"presupuesto": {"carry-H2": 0.0}, "efectivo": 1.0, "hurdle": 0.04}
# 2 % de quiebras (-100 %) y el resto repartido entre +1 % y +11 % (sin empates en la cola).
SCENARIOS = pl.DataFrame(
    {"carry-H2": np.concatenate([np.full(20, -1.0), np.linspace(0.01, 0.11, 980)])}
)


def test_allocation_table_compares_the_budget_with_the_paper() -> None:
    table = portfolio.allocation_table(BUDGET, {"carry-h2": 0.49})
    assert table.to_dicts() == [
        {"estrategia": "carry-h2", "recomendado": "0 %", "en paper ahora": "49 %"},
        {"estrategia": "efectivo", "recomendado": "100 %", "en paper ahora": "51 %"},
    ]


def test_cvar_table_shows_the_tail_risk_of_the_current_paper() -> None:
    table = {
        r["parte"]: r for r in portfolio.cvar_table(BUDGET, SCENARIOS, {"carry-h2": 0.5}).to_dicts()
    }
    assert table["carry-h2"]["con el presupuesto"] == "0,00 %"
    assert table["total (CVaR95)"]["con el presupuesto"] == "-4,00 %"  # todo en efectivo
    # Con la mitad en el carry, el CVaR es el de esa cartera (la cola incluye las 20 quiebras).
    carry = SCENARIOS["carry-H2"].to_numpy()
    expected = cvar95(0.5 * carry + 0.5 * 0.04)
    assert expected > 0.1  # la quiebra domina la cola
    assert table["total (CVaR95)"]["con el paper ahora"] == style.pct(expected, 2)


def test_cvar_contributions_add_up_to_the_portfolio_cvar() -> None:
    rng = np.random.default_rng(0)
    scenarios = {"a": rng.normal(0.05, 0.2, 5000), "b": rng.normal(0.02, 0.05, 5000)}
    weights = {"a": 0.3, "b": 0.4}
    parts = cvar_contributions(scenarios, weights)
    portfolio_returns = 0.3 * scenarios["a"] + 0.4 * scenarios["b"] + 0.3 * 0.04
    assert sum(parts.values()) == pytest.approx(cvar95(portfolio_returns))
    assert set(parts) == {"a", "b", "efectivo"}


def test_bands_widen_with_the_horizon_and_keep_their_order() -> None:
    daily = np.random.default_rng(1).normal(0.0002, 0.003, 500)
    q05, q50, q95 = bootstrap_bands(daily, 60)
    assert q05.shape == (60,)
    assert np.all(q05 <= q50)
    assert np.all(q50 <= q95)
    assert (q95[-1] - q05[-1]) > (q95[0] - q05[0])
    with pytest.raises(ValueError, match="horizonte"):
        bootstrap_bands(daily, 0)
    with pytest.raises(ValueError, match="21 días"):
        bootstrap_bands(daily[:10], 5)


def test_development_returns_drop_the_holdout_day() -> None:
    dates = [HOLDOUT_START - timedelta(days=2), HOLDOUT_START - timedelta(days=1), HOLDOUT_START]
    frame = pl.DataFrame({"date": [str(d) for d in dates], "k9": [0.01, 0.02, 9.0]})
    assert portfolio.development_returns(frame, "k9").tolist() == [0.01, 0.02]


def test_paper_curve_is_daily_and_joins_the_bands() -> None:
    t0 = datetime(2026, 11, 1, 12, tzinfo=UTC)
    valuations = [
        PortfolioValued(
            occurred_at=t0 + timedelta(hours=h), equity=D(1000 + h), cash=D(0), gross_notional=D(0)
        )
        for h in (0, 6, 30, 54)
    ]
    paper = portfolio.daily_paper_equity(valuations)
    assert paper.to_dicts() == [
        {"día": 0, "paper": pytest.approx(1.006)},  # última valoración del primer día
        {"día": 1, "paper": pytest.approx(1.030)},
        {"día": 2, "paper": pytest.approx(1.054)},
    ]
    frame = portfolio.bands_frame(paper, np.full(100, 0.001))
    assert frame.columns == ["día", "backtest p5", "backtest mediana", "backtest p95", "paper"]
    assert frame.height == 3
    assert frame["backtest mediana"][2] == pytest.approx(1.001**2)
    assert portfolio.bands_frame(paper.head(1), np.full(100, 0.001)).is_empty()


def test_the_portfolio_tab_renders_with_a_live_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = tmp_path / "lake"
    run_rig(lake / "paper")
    budget_dir = lake / "research" / "budget"
    budget_dir.mkdir(parents=True)
    (budget_dir / "summary.json").write_text(
        json.dumps(
            {
                **BUDGET,
                "tope_por_exchange": {"binance": 0.125},
                "cvar95": -0.04,
                "retorno_esperado": 0.04,
            }
        )
    )
    SCENARIOS.write_parquet(budget_dir / "scenarios.parquet")
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    at_ = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at_.exception
    tab = at_.tabs[7]
    assert tab.label == "¿Cómo se reparte? Cartera"
    assert len(tab.dataframe) == 3  # presupuesto, capital por estrategia y CVaR
    assert {m.label for m in tab.metric} == {
        "Tope por exchange",
        "CVaR95 recomendado",
        "Retorno esperado",
    }
