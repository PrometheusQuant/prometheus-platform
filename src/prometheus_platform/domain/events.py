"""Eventos de dominio: la base del journal append-only (event sourcing ligero).

Cada decisión relevante del sistema queda registrada como un evento inmutable. Así se
puede auditar qué pasó y reconstruir el estado reproduciendo el journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from prometheus_platform.domain.model import InstrumentId, Side, Signal


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime
    event_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignalGenerated(DomainEvent):
    signal: Signal


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderSubmitted(DomainEvent):
    client_order_id: str
    instrument: InstrumentId
    side: Side
    quantity: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderFilled(DomainEvent):
    client_order_id: str
    fill_price: Decimal
    fill_quantity: Decimal
    fee: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskLimitBreached(DomainEvent):
    rule: str
    detail: str
