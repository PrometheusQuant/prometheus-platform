"""Bróker del paper que ejecuta de verdad en un exchange de pruebas (PQ-52).

Lleva el mismo libro que el simulado (``LedgerBroker``): efectivo, posiciones, marcas y funding,
con el mismo formato de estado. La diferencia está en cada fill:

- **precio y cantidad:** los de la ejecución real, con la cantidad neta de comisiones;
- **comisión:** la que cobró el exchange;
- **slippage:** la diferencia entre el precio real y la valoración del ciclo.

El libro es una **subcuenta** de ``initial_cash`` dentro de la cuenta demo, que tiene más saldo de
prueba. Por eso ``reconcile`` compara solo los instrumentos operados, y no el saldo total.

El funding se calcula con la tasa publicada, igual que en el simulado. ``funding_income`` del
puerto permite contrastarlo con lo que registró el exchange.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from prometheus_platform.adapters.simulated_broker import LedgerBroker
from prometheus_platform.domain.model import InstrumentId, Side
from prometheus_platform.domain.ports import Clock, ExecutionPort, LiveMarket

ZERO = Decimal(0)


class ExchangeBroker(LedgerBroker):
    def __init__(
        self,
        gateway: ExecutionPort,
        *,
        market: LiveMarket,
        clock: Clock,
        state_path: Path,
        initial_cash: Decimal,
    ) -> None:
        super().__init__(market, clock, state_path, initial_cash)
        self._gateway = gateway
        self.name = gateway.name

    def submit(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> None:
        reference = self._reference(instrument)
        fill = self._gateway.market_order(client_order_id, instrument, side, quantity)
        self._apply_fill(
            client_order_id,
            instrument,
            side,
            quantity=fill.quantity,
            price=fill.price,
            reference=reference,
            fee=fill.fee,
        )

    def cancel_all(self) -> None:
        self._gateway.cancel_all()

    def reconcile(
        self, instruments: Sequence[InstrumentId]
    ) -> dict[InstrumentId, tuple[Decimal, Decimal]]:
        """Diferencias ``(libro, exchange)`` en los instrumentos dados; vacío si cuadran.

        En spot el exchange puede tener **más** que el libro (saldo de prueba ajeno a esta
        subcuenta): solo es diferencia si tiene menos, o si el signo no coincide.
        """
        held = self.positions()
        remote = self._gateway.positions(instruments)
        gaps: dict[InstrumentId, tuple[Decimal, Decimal]] = {}
        for instrument in instruments:
            mine, theirs = held.get(instrument, ZERO), remote.get(instrument, ZERO)
            if instrument.symbol.endswith("-PERP"):
                if mine != theirs:
                    gaps[instrument] = (mine, theirs)
            elif theirs < mine:
                gaps[instrument] = (mine, theirs)
        return gaps

    def exchange_funding(
        self, instrument: InstrumentId, since: datetime
    ) -> list[tuple[datetime, Decimal]]:
        return self._gateway.funding_income(instrument, since)
