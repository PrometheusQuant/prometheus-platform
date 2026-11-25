"""Muestreo de costes de ejecución en un exchange de pruebas (PQ-95).

Con el funding bajo, el carry puede pasar días sin operar, y PQ-95 necesita fills reales. Este
muestreo hace idas y vueltas pequeñas por símbolo y pata:

- **spot:** compra y venta;
- **perp:** venta y recompra.

Las registra en un **diario propio**, que no es el del runner, así que el libro del runner no se
entera. La referencia de cada orden es el **medio del libro** del propio exchange justo antes de
enviarla: el slippage medido es medio spread más el impacto.

Cada ida y vuelta queda plana salvo el polvo del redondeo. En una compra spot, la comisión se cobra
en el activo comprado y se vende la cantidad neta truncada al paso.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from prometheus_platform.domain.events import OrderFilled, OrderSubmitted
from prometheus_platform.domain.model import ExchangeFill, InstrumentId, Side, Venue
from prometheus_platform.domain.ports import Clock, EventJournal, ExecutionPort

PERP_SUFFIX = "-PERP"
MAX_ROUNDS = 10
NOTIONAL_RANGE = (Decimal(10), Decimal(1000))


def sample_costs(  # noqa: PLR0913 - keyword-only: piezas y parámetros del muestreo
    gateway: ExecutionPort,
    journal: EventJournal,
    clock: Clock,
    *,
    symbols: Sequence[str],
    notional: Decimal,
    rounds: int,
) -> int:
    """``rounds`` idas y vueltas de ``notional`` USDT por símbolo y pata; cuenta las órdenes."""
    if not 1 <= rounds <= MAX_ROUNDS:
        raise ValueError(f"rondas debe estar entre 1 y {MAX_ROUNDS}: {rounds}")
    low, high = NOTIONAL_RANGE
    if not low <= notional <= high:
        raise ValueError(f"nocional debe estar entre {low} y {high} USDT: {notional}")
    sent = 0
    stamp = f"{clock.now():%m%d%H%M%S}"
    for round_ in range(rounds):
        for symbol in symbols:
            for instrument, first, second in (
                (InstrumentId(symbol, Venue.BINANCE), Side.BUY, Side.SELL),
                (InstrumentId(f"{symbol}{PERP_SUFFIX}", Venue.BINANCE), Side.SELL, Side.BUY),
            ):
                prefix = f"pq95-{stamp}-{round_}-{instrument.symbol}"
                bid, ask = gateway.quote(instrument)
                quantity = notional / ((bid + ask) / 2)
                opened = _order(gateway, journal, clock, f"{prefix}-a", instrument, first, quantity)
                _order(gateway, journal, clock, f"{prefix}-b", instrument, second, opened.quantity)
                sent += 2
    return sent


def _order(  # noqa: PLR0913, PLR0917 - una orden completa del muestreo
    gateway: ExecutionPort,
    journal: EventJournal,
    clock: Clock,
    client_order_id: str,
    instrument: InstrumentId,
    side: Side,
    quantity: Decimal,
) -> ExchangeFill:
    bid, ask = gateway.quote(instrument)
    mid = (bid + ask) / 2
    journal.append(
        OrderSubmitted(
            occurred_at=clock.now(),
            client_order_id=client_order_id,
            instrument=instrument,
            side=side,
            quantity=quantity,
        )
    )
    fill = gateway.market_order(client_order_id, instrument, side, quantity)
    signed = fill.quantity if side is Side.BUY else -fill.quantity
    journal.append(
        OrderFilled(
            occurred_at=clock.now(),
            client_order_id=client_order_id,
            fill_price=fill.price,
            fill_quantity=fill.quantity,
            fee=fill.fee,
            slippage=signed * (fill.price - mid),
        )
    )
    return fill
