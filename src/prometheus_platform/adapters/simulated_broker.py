"""Bróker simulado del paper trading (PQ-54): opera sin claves sobre precios en vivo.

Contabilidad igual a la del backtest (``research/backtest.py``):
- **spot:** el efectivo paga o recibe el nocional;
- **perpetuo:** la ganancia o pérdida se lleva al efectivo en cada marca (mark-to-market) y el
  funding se cobra o paga sobre el nocional valorado al mark price;
- **costes:** comisión y slippage del ``CostModel`` del símbolo, por lado y por pata.

La diferencia es el precio de ejecución: aquí es el precio actual (con slippage), no el open de la
vela siguiente. El estado se guarda en un archivo JSON con escritura atómica, así sobrevive a un
reinicio.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from prometheus_platform.domain.events import OrderFilled
from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.domain.ports import Clock, LiveMarket
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.strategies.carry import is_perp, symbol_of

ZERO = Decimal(0)


@dataclass
class _State:
    cash: Decimal
    positions: dict[InstrumentId, Decimal] = field(default_factory=dict)
    marks: dict[InstrumentId, Decimal] = field(default_factory=dict)
    # Última liquidación aplicada por instrumento: hace idempotente ``settle_funding``.
    settled: dict[InstrumentId, datetime] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "cash": str(self.cash),
                "positions": {_key(i): str(q) for i, q in self.positions.items()},
                "marks": {_key(i): str(p) for i, p in self.marks.items()},
                "settled": {_key(i): t.isoformat() for i, t in self.settled.items()},
            }
        )

    @staticmethod
    def from_json(raw: str) -> _State:
        data = json.loads(raw)

        def key(text: str) -> InstrumentId:
            symbol, venue = text.split("|")
            return InstrumentId(symbol, Venue(venue))

        return _State(
            cash=Decimal(data["cash"]),
            positions={key(k): Decimal(v) for k, v in data["positions"].items()},
            marks={key(k): Decimal(v) for k, v in data["marks"].items()},
            settled={key(k): datetime.fromisoformat(v) for k, v in data["settled"].items()},
        )


def _key(instrument: InstrumentId) -> str:
    return f"{instrument.symbol}|{instrument.venue}"


class SimulatedBroker:
    name = "simulado"

    def __init__(
        self,
        market: LiveMarket,
        costs_for: Callable[[str], CostModel],
        clock: Clock,
        state_path: Path,
        initial_cash: Decimal,
    ) -> None:
        self._market = market
        self._costs_for = costs_for
        self._clock = clock
        self._path = state_path
        self._fills: list[OrderFilled] = []
        if state_path.exists():
            self._state = _State.from_json(state_path.read_text(encoding="utf-8"))
        else:
            self._state = _State(cash=initial_cash)
            self._save()

    # --- puerto Broker ---------------------------------------------------------------------

    def submit(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> None:
        if quantity <= 0:
            raise ValueError(f"Cantidad no positiva: {quantity}")
        spot_price, mark = self._market.prices(symbol_of(instrument))
        reference = mark if is_perp(instrument) else spot_price
        costs = self._costs_for(symbol_of(instrument))
        slip = Decimal(str(costs.slippage))
        fee_rate = Decimal(str(costs.perp_fee if is_perp(instrument) else costs.spot_fee))
        price = reference * (1 + slip) if side is Side.BUY else reference * (1 - slip)
        signed = quantity if side is Side.BUY else -quantity
        if is_perp(instrument):
            self._mark(instrument, price)  # realiza el P&L hasta el precio de ejecución
        else:
            self._state.cash -= signed * price
            self._state.marks[instrument] = price
        fee = quantity * price * fee_rate
        self._state.cash -= fee
        new_qty = self._state.positions.get(instrument, ZERO) + signed
        if new_qty == 0:
            self._state.positions.pop(instrument, None)
        else:
            self._state.positions[instrument] = new_qty
        self._fills.append(
            OrderFilled(
                occurred_at=self._clock.now(),
                client_order_id=client_order_id,
                fill_price=price,
                fill_quantity=quantity,
                fee=fee,
            )
        )
        self._save()

    def cancel_all(self) -> None:
        """Las órdenes de mercado simuladas se ejecutan al instante: no hay nada abierto."""

    def positions(self) -> dict[InstrumentId, Decimal]:
        return dict(self._state.positions)

    def cash(self) -> Decimal:
        return self._state.cash

    def drain_fills(self) -> list[OrderFilled]:
        fills, self._fills = self._fills, []
        return fills

    def settle_funding(
        self, instrument: InstrumentId, funding_time: datetime, rate: Decimal, mark: Decimal
    ) -> Decimal:
        last = self._state.settled.get(instrument)
        if last is not None and funding_time <= last:
            return ZERO  # ya aplicada (reinicio entre el cobro y el diario)
        qty = self._state.positions.get(instrument, ZERO)
        amount = ZERO
        if qty:
            self._mark(instrument, mark)
            amount = -qty * mark * rate  # el corto (qty < 0) cobra cuando la tasa es positiva
            self._state.cash += amount
        self._state.settled[instrument] = funding_time
        self._save()
        return amount

    def equity(self, marks: Mapping[InstrumentId, Decimal]) -> Decimal:
        """Efectivo más el valor del spot; el perpetuo ya está en el efectivo tras marcarlo."""
        for instrument, price in marks.items():
            if is_perp(instrument):
                self._mark(instrument, price)
            else:
                self._state.marks[instrument] = price
        self._save()
        spot_value = sum(
            (
                q * self._state.marks.get(i, ZERO)
                for i, q in self._state.positions.items()
                if not is_perp(i)
            ),
            ZERO,
        )
        return self._state.cash + spot_value

    # --- internos --------------------------------------------------------------------------

    def _mark(self, instrument: InstrumentId, price: Decimal) -> None:
        qty = self._state.positions.get(instrument, ZERO)
        previous = self._state.marks.get(instrument)
        if qty and previous is not None:
            self._state.cash += qty * (price - previous)
        self._state.marks[instrument] = price

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f"{self._path.name}.tmp")
        tmp.write_text(self._state.to_json(), encoding="utf-8")
        os.replace(tmp, self._path)
