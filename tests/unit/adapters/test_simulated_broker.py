"""Bróker simulado (PQ-54): contabilidad igual a la del backtest y estado que sobrevive."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.domain.model import FundingRate, Side
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 1, 8, tzinfo=UTC)
SPOT, PERP = spot_instrument("SOLUSDT"), perp_instrument("SOLUSDT")
COSTS = CostModel(spot_fee=0.001, perp_fee=0.0005, slippage=0.0)


class Prices:
    def __init__(self) -> None:
        self.spot = self.mark = Decimal(100)

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        return self.spot, self.mark

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        return []


def make(tmp_path: Path, market: Prices) -> SimulatedBroker:
    return SimulatedBroker(
        market, lambda _: COSTS, FixedClock(T0), tmp_path / "b.json", Decimal(1000)
    )


def test_spot_buy_pays_notional_and_fee(tmp_path: Path) -> None:
    broker = make(tmp_path, Prices())
    broker.submit("a", SPOT, Side.BUY, Decimal(2))

    assert broker.cash() == Decimal(1000) - 200 - Decimal("0.2")
    (fill,) = broker.drain_fills()
    assert fill.fill_price == 100
    assert fill.fee == Decimal("0.2")
    assert broker.drain_fills() == []


def test_slippage_worsens_the_price_on_both_sides(tmp_path: Path) -> None:
    broker = SimulatedBroker(
        Prices(),
        lambda _: CostModel(slippage=0.001),
        FixedClock(T0),
        tmp_path / "b.json",
        Decimal(1000),
    )
    broker.submit("a", SPOT, Side.BUY, Decimal(1))
    broker.submit("b", SPOT, Side.SELL, Decimal(1))
    buy, sell = broker.drain_fills()
    assert buy.fill_price == Decimal("100.1")
    assert sell.fill_price == Decimal("99.9")


def test_short_perp_is_marked_to_market_and_hedge_is_neutral(tmp_path: Path) -> None:
    market = Prices()
    broker = make(tmp_path, market)
    broker.submit("s", SPOT, Side.BUY, Decimal(2))
    broker.submit("p", PERP, Side.SELL, Decimal(2))
    start = broker.equity({SPOT: Decimal(100), PERP: Decimal(100)})

    after = broker.equity({SPOT: Decimal(150), PERP: Decimal(150)})

    assert after == start  # delta-neutral: +100 en spot, -100 en el corto
    assert broker.positions() == {SPOT: Decimal(2), PERP: Decimal(-2)}


def test_funding_is_paid_to_the_short_once_per_settlement(tmp_path: Path) -> None:
    broker = make(tmp_path, Prices())
    broker.submit("p", PERP, Side.SELL, Decimal(2))
    cash = broker.cash()

    amount = broker.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100))
    again = broker.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100))

    assert amount == Decimal("0.0200")
    assert again == 0
    assert broker.cash() == cash + amount


def test_no_position_settles_nothing_but_records_the_settlement(tmp_path: Path) -> None:
    broker = make(tmp_path, Prices())
    assert broker.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100)) == 0
    broker.submit("p", PERP, Side.SELL, Decimal(1))
    assert broker.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100)) == 0  # ya vista


def test_state_survives_a_restart(tmp_path: Path) -> None:
    market = Prices()
    broker = make(tmp_path, market)
    broker.submit("s", SPOT, Side.BUY, Decimal(2))
    broker.submit("p", PERP, Side.SELL, Decimal(2))
    broker.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100))

    again = make(tmp_path, market)

    assert again.cash() == broker.cash()
    assert again.positions() == broker.positions()
    assert again.settle_funding(PERP, T0, Decimal("0.0001"), Decimal(100)) == 0


def test_closing_removes_the_position_and_rejects_bad_quantities(tmp_path: Path) -> None:
    broker = make(tmp_path, Prices())
    broker.submit("a", SPOT, Side.BUY, Decimal(1))
    broker.submit("b", SPOT, Side.SELL, Decimal(1))
    assert broker.positions() == {}
    broker.cancel_all()  # no-op: las órdenes simuladas se ejecutan al instante
    with pytest.raises(ValueError, match="no positiva"):
        broker.submit("c", SPOT, Side.BUY, Decimal(0))
