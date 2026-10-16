"""Adaptadores en memoria: implementaciones de referencia de los puertos para tests y backtests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from prometheus_platform.domain.events import DomainEvent


class InMemoryEventJournal:
    """Journal append-only en memoria. Cumple el puerto ``EventJournal``."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def append(self, event: DomainEvent) -> None:
        if self._events and event.occurred_at < self._events[-1].occurred_at:
            raise ValueError("El journal es append-only y cronológico: evento fuera de orden")
        self._events.append(event)

    def replay(self) -> Iterator[DomainEvent]:
        return iter(tuple(self._events))

    def __len__(self) -> int:
        return len(self._events)


class FixedClock:
    """Reloj controlable para backtests y tests. Cumple el puerto ``Clock``."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance_to(self, instant: datetime) -> None:
        if instant < self._now:
            raise ValueError("El reloj simulado no puede retroceder")
        self._now = instant
