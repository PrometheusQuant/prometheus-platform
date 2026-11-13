"""Lectura del paper trading para el dashboard y el resumen diario (PQ-55).

Funciones puras sobre los eventos del diario (``replay``) y el heartbeat. No escriben nada: el
dashboard monta ``data/`` en solo lectura. El dashboard y el resumen diario de Telegram salen de
las mismas funciones, así que nunca dan cifras distintas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from prometheus_platform.domain.events import (
    DomainEvent,
    FundingSettled,
    KillSwitchReset,
    KillSwitchTripped,
    OrderFilled,
    OrderSubmitted,
    PortfolioValued,
    RiskLimitBreached,
    RunnerStarted,
)
from prometheus_platform.domain.model import InstrumentId, Side

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class Fill:
    at: datetime
    client_order_id: str
    instrument: InstrumentId
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    slippage: Decimal

    @property
    def cost(self) -> Decimal:
        return self.fee + self.slippage

    @property
    def label(self) -> str:
        """``entrada``, ``salida``, ``rebalanceo``, ``reparacion`` o ``kill``."""
        head = self.client_order_id.split("-")
        return "kill" if head[0] == "kill" else head[1] if len(head) > 1 else ""


@dataclass
class PaperView:
    """Todo lo que el diario dice del paper trading, ya agregado."""

    broker: str | None = None
    started_at: datetime | None = None
    positions: dict[InstrumentId, Decimal] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    settlements: list[FundingSettled] = field(default_factory=list)
    valuations: list[PortfolioValued] = field(default_factory=list)
    breaches: list[RiskLimitBreached] = field(default_factory=list)
    kill_events: list[KillSwitchTripped | KillSwitchReset] = field(default_factory=list)

    @property
    def funding(self) -> Decimal:
        return sum((s.amount for s in self.settlements), ZERO)

    @property
    def fees(self) -> Decimal:
        """Comisiones cobradas."""
        return sum((f.fee for f in self.fills), ZERO)

    @property
    def slippage(self) -> Decimal:
        return sum((f.slippage for f in self.fills), ZERO)

    @property
    def costs(self) -> Decimal:
        """Coste total de ejecución: comisiones más slippage."""
        return self.fees + self.slippage

    @property
    def initial_equity(self) -> Decimal | None:
        return self.valuations[0].equity if self.valuations else None

    @property
    def equity(self) -> Decimal | None:
        return self.valuations[-1].equity if self.valuations else None

    @property
    def peak_equity(self) -> Decimal | None:
        return max((v.equity for v in self.valuations), default=None)

    @property
    def drawdown(self) -> Decimal:
        """Caída desde el máximo de la curva (0 si no hay valoraciones)."""
        peak, last = self.peak_equity, self.equity
        if peak is None or last is None or peak <= 0:
            return ZERO
        return max(ZERO, 1 - last / peak)


def build_view(events: Iterable[DomainEvent]) -> PaperView:
    view = PaperView()
    submitted: dict[str, OrderSubmitted] = {}
    for event in events:
        if isinstance(event, RunnerStarted):
            view.broker = event.broker
            view.started_at = view.started_at or event.occurred_at
        elif isinstance(event, OrderSubmitted):
            submitted[event.client_order_id] = event
        elif isinstance(event, OrderFilled):
            order = submitted.get(event.client_order_id)
            if order is None:  # un fill sin su orden: no se puede atribuir, no se inventa
                continue
            fill = Fill(
                event.occurred_at,
                event.client_order_id,
                order.instrument,
                order.side,
                event.fill_quantity,
                event.fill_price,
                event.fee,
                event.slippage,
            )
            view.fills.append(fill)
            signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
            quantity = view.positions.get(fill.instrument, ZERO) + signed
            if quantity:
                view.positions[fill.instrument] = quantity
            else:
                view.positions.pop(fill.instrument, None)
        elif isinstance(event, FundingSettled):
            view.settlements.append(event)
        elif isinstance(event, PortfolioValued):
            view.valuations.append(event)
        elif isinstance(event, RiskLimitBreached):
            view.breaches.append(event)
        elif isinstance(event, KillSwitchTripped | KillSwitchReset):
            view.kill_events.append(event)
    return view


@dataclass(frozen=True, slots=True)
class DailySummary:
    day: date
    orders: int
    funding: Decimal
    fees: Decimal
    slippage: Decimal
    equity_start: Decimal | None
    equity_end: Decimal | None
    breaches: int

    def details(self) -> dict[str, str]:
        change = (
            f"{self.equity_end / self.equity_start - 1:+.3%}"
            if self.equity_start and self.equity_end
            else "n/d"
        )
        return {
            "día (UTC)": self.day.isoformat(),
            "órdenes ejecutadas": str(self.orders),
            "funding neto": f"{self.funding:.4f} USD",
            "comisiones": f"{self.fees:.4f} USD",
            "slippage": f"{self.slippage:.4f} USD",
            "equity al cierre": f"{self.equity_end:.2f} USD" if self.equity_end else "n/d",
            "variación del día": change,
            "violaciones de riesgo": str(self.breaches),
        }


def daily_summary(view: PaperView, day: date) -> DailySummary:
    values = [v.equity for v in view.valuations if v.occurred_at.date() == day]
    return DailySummary(
        day=day,
        orders=sum(1 for f in view.fills if f.at.date() == day),
        funding=sum((s.amount for s in view.settlements if s.funding_time.date() == day), ZERO),
        fees=sum((f.fee for f in view.fills if f.at.date() == day), ZERO),
        slippage=sum((f.slippage for f in view.fills if f.at.date() == day), ZERO),
        equity_start=values[0] if values else None,
        equity_end=values[-1] if values else None,
        breaches=sum(1 for b in view.breaches if b.occurred_at.date() == day),
    )


def read_heartbeat(path: Path) -> dict[str, Any] | None:
    """El último heartbeat, o ``None`` si no existe o no se puede leer."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["at"] = datetime.fromisoformat(str(data["at"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return data if isinstance(data, dict) else None
