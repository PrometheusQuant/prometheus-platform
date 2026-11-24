"""Bróker de exchange (PQ-52): el libro del simulado con los fills reales del exchange."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_platform.adapters.exchange_broker import ExchangeBroker
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.domain.model import ExchangeFill, FundingRate, InstrumentId, Side
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 24, 12, tzinfo=UTC)
SPOT, PERP = spot_instrument("SOLUSDT"), perp_instrument("SOLUSDT")


class Prices:
    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        return Decimal(100), Decimal(100)

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        return []


class FakeGateway:
    """``ExecutionPort`` en memoria: ejecuta a ``price`` con la comisión indicada."""

    name = "binance-demo"

    def __init__(self) -> None:
        self.price_ = Decimal("100.5")
        self.fee = Decimal("0.05")
        self.net_cut = Decimal(0)
        self.remote: dict[InstrumentId, Decimal] = {}
        self.cancelled = 0

    def balance(self, asset: str, *, perp: bool) -> Decimal:
        return Decimal(5000)

    def price(self, instrument: InstrumentId) -> Decimal:
        return self.price_

    def market_order(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> ExchangeFill:
        return ExchangeFill(client_order_id, "1", quantity - self.net_cut, self.price_, self.fee)

    def cancel_all(self) -> None:
        self.cancelled += 1

    def positions(self, instruments: Sequence[InstrumentId]) -> dict[InstrumentId, Decimal]:
        return {i: q for i, q in self.remote.items() if i in instruments}

    def funding_income(
        self, instrument: InstrumentId, since: datetime
    ) -> list[tuple[datetime, Decimal]]:
        return [(T0, Decimal("0.1"))]


def make(tmp_path: Path, gateway: FakeGateway) -> ExchangeBroker:
    return ExchangeBroker(
        gateway,
        market=Prices(),
        clock=FixedClock(T0),
        state_path=tmp_path / "b.json",
        initial_cash=Decimal(1000),
    )


def test_spot_buy_books_the_real_fill(tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.net_cut = Decimal("0.001")  # comisión cobrada en SOL
    broker = make(tmp_path, gateway)
    broker.submit("c1", SPOT, Side.BUY, Decimal(1))
    assert broker.positions() == {SPOT: Decimal("0.999")}
    assert broker.cash() == 1000 - Decimal("0.999") * Decimal("100.5") - Decimal("0.05")
    (fill,) = broker.drain_fills()
    assert fill.fill_price == Decimal("100.5")
    assert fill.fee == Decimal("0.05")
    assert fill.slippage == Decimal("0.999") * Decimal("0.5")  # frente a la valoración (100)
    assert broker.name == "binance-demo"


def test_perp_sell_moves_cash_only_by_slippage_and_fee(tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.price_ = Decimal("99.8")
    broker = make(tmp_path, gateway)
    broker.submit("c2", PERP, Side.SELL, Decimal(2))
    assert broker.positions() == {PERP: Decimal(-2)}
    # Vender a 99,8 con referencia 100: 0,4 USDT de slippage más la comisión.
    assert broker.cash() == 1000 - Decimal("0.4") - Decimal("0.05")


def test_state_survives_a_restart(tmp_path: Path) -> None:
    broker = make(tmp_path, FakeGateway())
    broker.submit("c3", PERP, Side.SELL, Decimal(1))
    again = make(tmp_path, FakeGateway())
    assert again.positions() == broker.positions()
    assert again.cash() == broker.cash()


def test_reconcile_reports_only_real_gaps(tmp_path: Path) -> None:
    gateway = FakeGateway()
    broker = make(tmp_path, gateway)
    broker.submit("c4", SPOT, Side.BUY, Decimal(1))
    broker.submit("c5", PERP, Side.SELL, Decimal(1))
    gateway.remote = {SPOT: Decimal(3), PERP: Decimal(-1)}  # spot con saldo de prueba ajeno
    assert broker.reconcile([SPOT, PERP]) == {}
    gateway.remote = {SPOT: Decimal("0.5"), PERP: Decimal("-0.9")}
    assert broker.reconcile([SPOT, PERP]) == {
        SPOT: (Decimal(1), Decimal("0.5")),
        PERP: (Decimal(-1), Decimal("-0.9")),
    }


def test_cancel_all_and_funding_go_to_the_exchange(tmp_path: Path) -> None:
    gateway = FakeGateway()
    broker = make(tmp_path, gateway)
    broker.cancel_all()
    assert gateway.cancelled == 1
    assert broker.exchange_funding(PERP, T0) == [(T0, Decimal("0.1"))]
