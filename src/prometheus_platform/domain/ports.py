"""Puertos de la arquitectura hexagonal.

Son interfaces pequeñas (ISP) que el núcleo usa sin conocer la implementación (DIP).
Los adaptadores en ``prometheus_platform.adapters`` las implementan para Binance, el
paper trading o los tests, y son intercambiables entre sí (LSP).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from prometheus_platform.domain.events import DomainEvent
from prometheus_platform.domain.model import Bar, FundingRate, InstrumentId, Side


class Clock(Protocol):
    """Fuente de tiempo. En backtest es simulada; en vivo, el reloj del sistema."""

    def now(self) -> datetime: ...


class MarketDataFeed(Protocol):
    def bars(self, instrument: InstrumentId, start: datetime, end: datetime) -> Iterable[Bar]: ...

    def funding_rates(
        self, instrument: InstrumentId, start: datetime, end: datetime
    ) -> Iterable[FundingRate]: ...


class OrderGateway(Protocol):
    def submit(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> None: ...

    def cancel_all(self) -> None:
        """Usado por el kill-switch: cancela todas las órdenes abiertas."""
        ...


class EventJournal(Protocol):
    """Registro append-only. Nunca modifica ni borra eventos."""

    def append(self, event: DomainEvent) -> None: ...

    def replay(self) -> Iterator[DomainEvent]: ...
