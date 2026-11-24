"""Evaluación de Polymarket (PQ-93) sobre datos sintéticos: reglas del pre-registro PQ-87."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from tests.unit.research.polymarket_data import D0, raw_market, silver_markets, silver_prices

from prometheus_platform.research import polymarket_evaluation as pe
from prometheus_platform.research.carry_evaluation import TrialRecord
from prometheus_platform.research.polymarket_evaluation import (
    BANDS,
    EVALUATION,
    HOLDOUT,
    Bet,
    Category,
    Period,
    bet_stats,
    build_bets,
    correlation,
    daily_pnl,
    evaluate,
    fee_rate,
    run_and_register,
    universe,
)

DAY = 86_400
B80 = BANDS[1]
SHORT = Period("corto", D0, D0 + timedelta(days=30), D0 + timedelta(days=30))


class Registry:
    familia = pe.FAMILY

    def __init__(self) -> None:
        self.logged: list[TrialRecord] = []

    def log_trial(self, trial: TrialRecord) -> None:
        self.logged.append(trial)

    def trials(self) -> list[TrialRecord]:
        return list(self.logged)


# --- Comisiones y universo --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fee_type", "tags", "rate"),
    [
        ("politics_fees", [], 0.04),
        ("crypto_fees", ["Politics"], 0.07),
        (None, ["Politics", "Crypto"], 0.07),  # varias categorías: la más cara
        (None, ["Geopolitics"], 0.0),
        (None, ["All", "Weird"], 0.07),  # desconocida: 0,07
        ("unknown_fees", ["Sports"], 0.05),
    ],
)
def test_fee_rate_follows_section_6(fee_type: str | None, tags: list[str], rate: float) -> None:
    assert fee_rate(fee_type, tags) == rate


def test_universe_rules_of_section_3() -> None:
    markets = silver_markets(
        raw_market("ok"),
        raw_market("thin", volume=999.0),
        raw_market("zero", payouts='["0", "0"]'),
        raw_market("three", outcomes='["A", "B", "C"]'),
        raw_market("sport", tags=("Sports",)),
        raw_market("open", closed=None),
    )
    p1 = set(universe(markets, Category.P1)["market_id"])
    assert p1 == {"ok", "open"}  # sin closedTime se queda: se valora al corte
    assert set(universe(markets, Category.P2)["market_id"]) == {"sport"}
    assert "ok" not in set(universe(markets, Category.P1, min_volume=10_000)["market_id"])


# --- Entrada, pago y point-in-time ------------------------------------------------------------


def test_entry_is_the_first_snapshot_in_the_band_and_pays_the_published_payout() -> None:
    markets = silver_markets(raw_market("m"))
    prices = silver_prices(markets, {"m": [0.6, 0.75, 0.82, 0.90, 0.97]})
    [bet] = build_bets(markets, prices, B80, SHORT)
    assert bet.entry_time == D0 + timedelta(days=2)  # 0,82: el primero en [0,80; 0,95)
    assert bet.favorite == 0
    assert bet.price == pytest.approx(0.82)
    paid = 0.83
    assert bet.cost_per_share == pytest.approx(paid + 0.04 * paid * (1 - paid))
    assert bet.payout == 1.0
    assert bet.resolved
    assert bet.realized_at == D0 + timedelta(days=10)
    assert bet.pnl == pytest.approx(1 / (paid + 0.04 * paid * (1 - paid)) - 1)


def test_the_favorite_can_be_the_second_outcome() -> None:
    markets = silver_markets(raw_market("m", payouts='["0", "1"]'))
    prices = silver_prices(markets, {"m": [0.15]})  # el segundo vale 0,85
    [bet] = build_bets(markets, prices, B80, SHORT)
    assert bet.favorite == 1
    assert bet.price == pytest.approx(0.85)
    assert bet.payout == 1.0


def test_partial_resolutions_pay_what_was_published() -> None:
    markets = silver_markets(raw_market("m", payouts='["0.5", "0.5"]'))
    [bet] = build_bets(markets, silver_prices(markets, {"m": [0.85]}), B80, SHORT)
    assert bet.payout == 0.5


def test_no_entry_once_the_market_is_closed() -> None:
    markets = silver_markets(raw_market("m", closed=D0 + timedelta(days=1, hours=1)))
    prices = silver_prices(markets, {"m": [0.6, 0.7, 0.85]})  # 0,85 llega después del cierre
    assert build_bets(markets, prices, B80, SHORT) == []


def test_a_first_entry_outside_the_period_does_not_belong_to_it() -> None:
    markets = silver_markets(raw_market("m"))
    prices = silver_prices(markets, {"m": [0.85]})
    later = Period("despues", D0 + timedelta(days=1), D0 + timedelta(days=30), SHORT.cutoff)
    assert build_bets(markets, prices, B80, later) == []


def test_placeholders_never_trigger_an_entry() -> None:
    markets = silver_markets(raw_market("m"))
    prices = silver_prices(markets, {"m": [0.5, 0.5, 0.5, 0.86]})
    [bet] = build_bets(markets, prices, None, SHORT)  # B1: primera instantánea válida
    assert bet.entry_time == D0  # el primer 0,5 todavía es precio (pre-registro §4)
    assert bet.price == 0.5


def test_nothing_after_the_cutoff_is_used() -> None:
    """Resolución posterior al corte: se valora al último precio anterior al corte, menos 0,01."""
    cut = Period("corte", D0, D0 + timedelta(days=3), D0 + timedelta(days=3))
    markets = silver_markets(raw_market("m", closed=D0 + timedelta(days=10)))
    prices = silver_prices(markets, {"m": [0.85, 0.88, 0.90, 0.70, 0.99, 0.99]})
    [bet] = build_bets(markets, prices, B80, cut)
    assert not bet.resolved
    assert bet.realized_at == cut.cutoff
    assert bet.payout == pytest.approx(0.70 - 0.01)  # día 3; los 0,99 posteriores no cuentan


def test_holdout_period_starts_after_evaluation() -> None:
    assert HOLDOUT.entry_start > EVALUATION.cutoff
    assert EVALUATION.entry_end <= EVALUATION.cutoff


# --- Métricas ---------------------------------------------------------------------------------


def bet(event: str, pnl: float, days: int = 10) -> Bet:
    """Una apuesta con el PnL pedido (precio 0,5, sin comisión)."""
    return Bet(
        market_id=f"{event}-{pnl}",
        event_id=event,
        entry_time=D0,
        favorite=0,
        price=0.5,
        cost_per_share=0.5,
        payout=0.5 * (1 + pnl),
        realized_at=D0 + timedelta(days=days),
        resolved=True,
    )


def test_bet_stats_cluster_by_event() -> None:
    bets = [bet("a", 0.2), bet("a", 0.2), bet("b", -0.1), bet("c", 0.1)]
    st = bet_stats(bets)
    mean = (0.2 + 0.2 - 0.1 + 0.1) / 4
    meat = (0.4 - 2 * mean) ** 2 + (-0.1 - mean) ** 2 + (0.1 - mean) ** 2
    se = math.sqrt(meat) / 4 * math.sqrt(3 / 2)
    assert st.n_bets == 4
    assert st.n_events == 3
    assert st.mean_return == pytest.approx(mean)
    assert st.t_cluster == pytest.approx(mean / se)
    assert st.event_weighted_return == pytest.approx((0.2 - 0.1 + 0.1) / 3)
    assert st.dollar_year_return == pytest.approx(0.4 / (4 * 10 / 365))


def test_bet_stats_of_nothing_is_nan() -> None:
    assert math.isnan(bet_stats([]).mean_return)


def test_daily_pnl_lands_on_the_realization_day_and_covers_the_period() -> None:
    daily = daily_pnl([bet("a", 0.2, days=2), bet("b", -0.1, days=2), bet("c", 0.1, days=5)], SHORT)
    assert daily.height == 31
    assert daily.filter(pl.col("date") == date(2024, 3, 3))["pnl"][0] == pytest.approx(0.1)
    assert daily["pnl"].sum() == pytest.approx(0.2)
    assert daily_pnl([], SHORT)["pnl"].sum() == 0


def test_correlation_needs_enough_common_days() -> None:
    days = pl.date_range(date(2024, 1, 1), date(2024, 4, 30), "1d", eager=True)
    rng = np.random.default_rng(0)
    x = rng.normal(size=len(days))
    pnl = pl.DataFrame({"date": days, "pnl": x})
    other = pl.DataFrame({"date": days, "ret": 2 * x + 1})
    assert correlation(pnl, other) == pytest.approx(1.0)
    assert correlation(pnl, other.head(30)) is None
    assert correlation(pnl, other.with_columns(pl.lit(0.0).alias("ret"))) is None


# --- Registro y evaluación --------------------------------------------------------------------


def test_each_configuration_is_registered_before_it_is_evaluated() -> None:
    markets = silver_markets(raw_market("m"))
    prices = silver_prices(markets, {"m": [0.85]})
    registry = Registry()
    result = run_and_register(markets, prices, Category.P1, B80, registry)
    [trial] = registry.logged
    assert trial.name == result.name == "P1-B80"
    assert trial.hypothesis == "P1"
    assert trial.metrics["apuestas"] == 1
    assert "sharpe_daily" in trial.metrics


def test_wrong_family_or_holdout_are_refused() -> None:
    markets = silver_markets(raw_market("m"))
    prices = silver_prices(markets, {"m": [0.85]})
    wrong = Registry()
    wrong.familia = "carry"
    with pytest.raises(ValueError, match="familia"):
        run_and_register(markets, prices, Category.P1, B80, wrong)
    with pytest.raises(ValueError, match="holdout"):
        run_and_register(markets, prices, Category.P1, B80, Registry(), period=HOLDOUT)


def test_evaluate_registers_six_trials_and_reports_five_gates() -> None:
    rows, series = [], {}
    for i in range(40):
        sport = i % 4 == 0
        rows.append(
            raw_market(
                str(i),
                closed=D0 + timedelta(days=5 + i),
                payouts='["1", "0"]' if i % 5 else '["0", "1"]',
                tags=("Sports",) if sport else ("Politics",),
                event=f"ev{i // 2}",
            )
        )
        series[str(i)] = [0.72, 0.83, 0.92, 0.96]
    markets = silver_markets(*rows)
    prices = silver_prices(markets, series)
    days = pl.date_range(EVALUATION.entry_start.date(), EVALUATION.cutoff.date(), "1d", eager=True)
    carry = pl.DataFrame({"date": days, "ret": np.random.default_rng(1).normal(size=len(days))})
    registry = Registry()

    result = evaluate(markets, prices, registry, {"carry_H2": carry})

    assert [t.name for t in registry.logged] == [
        "P1-B70", "P1-B80", "P1-B90", "P2-B70", "P2-B80", "P2-B90",
    ]  # fmt: skip
    p1 = result[Category.P1]
    assert [g.name for g in p1.gates] == ["G1", "G2", "G3", "G4", "G5"]
    assert p1.n_trials == 6
    assert p1.principal.name == "P1-B80"
    assert p1.principal.stats.n_bets == 30
    assert set(p1.sensitivity) == {
        "sin_diferencial", "diferencial_0.02", "sin_comision", "volumen_10000",
    }  # fmt: skip
    assert "carry_H2" in p1.correlations
    assert 0 <= p1.pbo <= 1
    assert result[Category.P2].principal.stats.n_bets == 10
