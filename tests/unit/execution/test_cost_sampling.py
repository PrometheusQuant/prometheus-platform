"""Muestreo de costes en un exchange de pruebas (PQ-95), con un gateway falso: sin red."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.domain.events import OrderFilled, OrderSubmitted
from prometheus_platform.domain.model import ExchangeFill, InstrumentId, Side
from prometheus_platform.domain.ports import ExecutionPort
from prometheus_platform.execution.cost_sampling import sample_costs
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.research.cost_calibration import order_costs, summarize

T0 = datetime(2026, 11, 25, 12, tzinfo=UTC)


class TickingClock:
    def __init__(self) -> None:
        self.t = T0

    def now(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


class FakeGateway:
    """Libro 99,95 / 100,05; las compras se llenan al ask más 1 céntimo y las ventas al bid."""

    name = "fake"

    def __init__(self, base_fee_cut: Decimal = Decimal(0)) -> None:
        self.cut = base_fee_cut
        self.sent: list[tuple[str, InstrumentId, Side, Decimal]] = []

    def quote(self, instrument: InstrumentId) -> tuple[Decimal, Decimal]:
        return Decimal("99.95"), Decimal("100.05")

    def market_order(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> ExchangeFill:
        self.sent.append((client_order_id, instrument, side, quantity))
        price = Decimal("100.06") if side is Side.BUY else Decimal("99.95")
        spot_buy = side is Side.BUY and not instrument.symbol.endswith("-PERP")
        net = quantity - self.cut if spot_buy else quantity  # la comisión spot sale del activo
        return ExchangeFill(client_order_id, "1", net, price, quantity * price * Decimal("0.001"))


def port(gateway: FakeGateway) -> ExecutionPort:
    """El muestreo solo usa ``quote`` y ``market_order`` del puerto."""
    return cast("ExecutionPort", gateway)


def test_each_symbol_and_leg_gets_a_round_trip_in_its_own_journal(tmp_path: Path) -> None:
    gateway = FakeGateway(base_fee_cut=Decimal("0.001"))
    journal = JsonlEventJournal(tmp_path / "muestreo.jsonl")
    sent = sample_costs(
        port(gateway), journal, TickingClock(), symbols=["BTCUSDT"], notional=Decimal(100), rounds=2
    )
    assert sent == 8  # 2 rondas, 2 patas, ida y vuelta
    sides = [(i.symbol, s) for _, i, s, _ in gateway.sent[:4]]
    assert sides == [
        ("BTCUSDT", Side.BUY),
        ("BTCUSDT", Side.SELL),
        ("BTCUSDT-PERP", Side.SELL),
        ("BTCUSDT-PERP", Side.BUY),
    ]
    # La venta spot devuelve lo comprado neto de la comisión: la ida y vuelta queda plana.
    assert gateway.sent[1][3] == gateway.sent[0][3] - Decimal("0.001")
    assert gateway.sent[3][3] == gateway.sent[2][3]  # en perp, la misma cantidad
    assert gateway.sent[0][3] == Decimal(100) / Decimal(100)  # nocional / medio del libro
    events = list(journal.replay())
    assert sum(isinstance(e, OrderSubmitted) for e in events) == 8
    assert sum(isinstance(e, OrderFilled) for e in events) == 8
    assert len({e.client_order_id for e in events if isinstance(e, OrderSubmitted)}) == 8


def test_the_reference_is_the_mid_of_the_book_before_each_order(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "muestreo.jsonl")
    sample_costs(
        port(FakeGateway()),
        journal,
        TickingClock(),
        symbols=["ETHUSDT"],
        notional=Decimal(50),
        rounds=1,
    )
    orders = order_costs(journal.replay(), lambda _symbol: CostModel())
    assert all(o.reference == Decimal(100) for o in orders)
    buys = [o.slippage_bp for o in orders if o.side is Side.BUY]
    sells = [o.slippage_bp for o in orders if o.side is Side.SELL]
    assert buys == pytest.approx([6.0, 6.0])  # 100,06 frente a 100: medio spread y 1 céntimo
    assert sells == pytest.approx([5.0, 5.0])  # 99,95 frente a 100: medio spread
    spot, perp = summarize(orders)
    assert spot.slippage_worse  # 5,5 pb > 2 pb del CostModel por defecto
    assert perp.slippage_bp_median == pytest.approx(5.5)


@pytest.mark.parametrize(
    ("notional", "rounds", "message"),
    [(Decimal(5), 1, "nocional"), (Decimal(5000), 1, "nocional"), (Decimal(100), 0, "rondas")],
)
def test_limits_keep_the_sample_small(
    tmp_path: Path, notional: Decimal, rounds: int, message: str
) -> None:
    gateway = FakeGateway()
    with pytest.raises(ValueError, match=message):
        sample_costs(
            port(gateway),
            JsonlEventJournal(tmp_path / "x.jsonl"),
            TickingClock(),
            symbols=["BTCUSDT"],
            notional=notional,
            rounds=rounds,
        )
    assert gateway.sent == []
