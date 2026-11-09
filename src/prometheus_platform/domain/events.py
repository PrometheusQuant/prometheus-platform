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


@dataclass(frozen=True, slots=True, kw_only=True)
class KillSwitchTripped(DomainEvent):
    """Se detuvo la operación. ``source``: ``automatico``, ``cli`` o ``archivo``."""

    reason: str
    source: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KillSwitchReset(DomainEvent):
    """Se rearmó la operación, siempre a mano y con autor."""

    by: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RunnerStarted(DomainEvent):
    """Arranque del runner: con qué bróker opera (``simulado`` o ``binance-demo``) y qué opera."""

    broker: str
    strategy_id: str
    symbols: str  # separados por coma: el diario solo guarda tipos simples
    params: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundingSettled(DomainEvent):
    """Una liquidación de funding procesada, con su decisión y el estado deseado que deja.

    Se registra una vez por ``(symbol, funding_time)``: evita procesarla dos veces y, tras un
    reinicio, dice al runner hacia qué estado reconciliar.
    """

    symbol: str
    funding_time: datetime
    rate: Decimal
    interval_hours: int
    amount: Decimal  # cobrado (+) o pagado (-) por la posición perp abierta; 0 si no había
    action: str  # decisión de la regla en esta liquidación: entrada, salida o mantener
    s_k: str  # señal anualizada usada, en texto; vacía si aún no hay k liquidaciones
    target_open: bool  # estado deseado tras la decisión: el runner reconcilia hacia él
    was_open: bool  # estado deseado antes de la decisión: rige hasta t + 1 h (enmienda 1.1)
    rebalance: bool  # la decisión pide rebalancear (enmienda 2), una sola vez


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioValued(DomainEvent):
    """Valoración de la cartera: la curva de capital del paper trading."""

    equity: Decimal
    cash: Decimal
    gross_notional: Decimal
