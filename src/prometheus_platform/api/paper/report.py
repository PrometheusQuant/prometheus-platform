"""Lectura del paper trading para el dashboard y el resumen diario (PQ-55).

Funciones puras sobre los eventos del diario (``replay``) y el heartbeat. No escriben nada: el
dashboard monta ``data/`` en solo lectura. El dashboard y el resumen diario de Telegram salen de
las mismas funciones, así que nunca dan cifras distintas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
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
    SignalGenerated,
)
from prometheus_platform.domain.model import InstrumentId, Side
from prometheus_platform.strategies.carry import perp_instrument, symbol_of

UNASSIGNED = "sin asignar"

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
    # PQ-84: de qué estrategia es cada instrumento (sus señales) y el último precio de cada uno.
    owners: dict[InstrumentId, str] = field(default_factory=dict)
    marks: dict[InstrumentId, Decimal] = field(default_factory=dict)
    # Respaldo: la estrategia del último arranque para cada símbolo (el carry antes de operar).
    runner_symbols: dict[str, str] = field(default_factory=dict)

    def owner(self, instrument: InstrumentId) -> str:
        """De quién es un instrumento: sus señales mandan; si no tiene, el runner del símbolo."""
        found = self.owners.get(instrument)
        return found or self.runner_symbols.get(symbol_of(instrument), UNASSIGNED)

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


def _apply_fill(view: PaperView, event: OrderFilled, submitted: dict[str, OrderSubmitted]) -> None:
    order = submitted.get(event.client_order_id)
    if order is None:  # un fill sin su orden: no se puede atribuir, no se inventa
        return
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


def build_view(events: Iterable[DomainEvent]) -> PaperView:
    view = PaperView()
    submitted: dict[str, OrderSubmitted] = {}
    for event in events:
        if isinstance(event, RunnerStarted):
            view.broker = event.broker
            view.started_at = view.started_at or event.occurred_at
            for symbol in filter(None, event.symbols.split(",")):
                view.runner_symbols[symbol] = event.strategy_id
        elif isinstance(event, OrderSubmitted):
            submitted[event.client_order_id] = event
        elif isinstance(event, OrderFilled):
            _apply_fill(view, event, submitted)
        elif isinstance(event, FundingSettled):
            view.settlements.append(event)
        elif isinstance(event, PortfolioValued):
            view.valuations.append(event)
            view.marks.update(event.mark_prices())
        elif isinstance(event, SignalGenerated):
            view.owners[event.signal.instrument] = event.signal.strategy_id
        elif isinstance(event, RiskLimitBreached):
            view.breaches.append(event)
        elif isinstance(event, KillSwitchTripped | KillSwitchReset):
            view.kill_events.append(event)
    return view


@dataclass(frozen=True, slots=True)
class StrategyRow:
    """Una estrategia en un exchange, según el diario del paper trading (PQ-84)."""

    strategy: str
    exchange: str
    exposure: Decimal  # nocional bruto abierto, a la última marca
    pnl: Decimal  # flujos de las órdenes + funding + posición a la última marca
    funding: Decimal
    costs: Decimal  # comisiones + slippage
    approximate: bool  # alguna posición sin marca: se valoró al último fill


@dataclass
class _Acc:
    exposure: Decimal = ZERO
    pnl: Decimal = ZERO
    funding: Decimal = ZERO
    costs: Decimal = ZERO
    approximate: bool = False


def strategy_breakdown(view: PaperView) -> list[StrategyRow]:
    """Capital y PnL por estrategia y exchange. La suma de los PnL es el PnL de la cartera.

    PnL de un instrumento: menos la suma de (cantidad con signo · precio) de sus fills, menos las
    comisiones, más la cantidad abierta a la última marca. El slippage ya va dentro del precio del
    fill. El funding de un símbolo es de quien tiene su perpetuo.
    """
    rows: dict[tuple[str, str], _Acc] = {}

    def row(instrument: InstrumentId) -> _Acc:
        key = (view.owner(instrument), str(instrument.venue))
        return rows.setdefault(key, _Acc())

    last_price: dict[InstrumentId, Decimal] = {}
    for fill in view.fills:
        signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
        acc = row(fill.instrument)
        acc.pnl -= signed * fill.price + fill.fee
        acc.costs += fill.cost
        last_price[fill.instrument] = fill.price
    for settlement in view.settlements:
        acc = row(perp_instrument(settlement.symbol))
        acc.pnl += settlement.amount
        acc.funding += settlement.amount
    for instrument, quantity in view.positions.items():
        acc = row(instrument)
        mark = view.marks.get(instrument)
        if mark is None:  # diario anterior a PQ-84: se valora al último fill
            mark = last_price.get(instrument, ZERO)
            acc.approximate = True
        acc.pnl += quantity * mark
        acc.exposure += abs(quantity) * mark
    return [
        StrategyRow(strategy, exchange, a.exposure, a.pnl, a.funding, a.costs, a.approximate)
        for (strategy, exchange), a in sorted(rows.items())
    ]


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


# --- informe semanal (PQ-85) ----------------------------------------------------------------

WEEK = timedelta(days=7)


def iso_week(monday: date) -> str:
    """Etiqueta ISO de la semana, p. ej. ``2026-W47``."""
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


def parse_iso_week(text: str) -> date:
    """El lunes de una semana ``AAAA-Www``."""
    try:
        year, _, week = text.strip().upper().partition("-W")
        return date.fromisocalendar(int(year), int(week), 1)
    except ValueError as exc:
        raise ValueError(f"semana {text!r}: usa AAAA-Www, p. ej. 2026-W47") from exc


def last_complete_week(now: datetime) -> date:
    """El lunes de la última semana ISO (lunes a domingo, UTC) que ya terminó."""
    today = now.astimezone(UTC).date()
    return today - timedelta(days=today.weekday()) - WEEK


@dataclass(frozen=True, slots=True)
class StrategyWeek:
    """Lo que hizo una estrategia en un exchange durante la semana."""

    strategy: str
    exchange: str
    pnl: Decimal
    funding: Decimal
    costs: Decimal
    exposure: Decimal  # nocional bruto abierto al cierre de la semana


@dataclass(frozen=True, slots=True)
class WeeklySummary:
    week: str
    start: date  # lunes
    end: date  # domingo
    orders: int
    funding: Decimal
    fees: Decimal
    slippage: Decimal
    equity_start: Decimal | None  # cierre de la semana anterior (o primera valoración)
    equity_end: Decimal | None
    max_drawdown: Decimal  # de pico a valle dentro de la semana
    breaches: int
    kill_trips: int
    strategies: tuple[StrategyWeek, ...]
    curve: tuple[tuple[datetime, Decimal], ...]

    @property
    def change(self) -> Decimal | None:
        if not self.equity_start or self.equity_end is None:
            return None
        return self.equity_end / self.equity_start - 1

    def details(self) -> dict[str, str]:
        change = self.change
        trips = "1 vez" if self.kill_trips == 1 else f"{self.kill_trips} veces"
        details = {
            "semana": f"{self.week} ({self.start} a {self.end}, UTC)",
            "órdenes ejecutadas": str(self.orders),
            "funding neto": f"{self.funding:.4f} USD",
            "comisiones": f"{self.fees:.4f} USD",
            "slippage": f"{self.slippage:.4f} USD",
            "equity al cierre": f"{self.equity_end:.2f} USD" if self.equity_end else "n/d",
            "variación semanal": f"{change:+.3%}" if change is not None else "n/d",
            "caída máxima en la semana": f"{self.max_drawdown:.2%}",
            "violaciones de riesgo": str(self.breaches),
            "kill-switch activado": trips,
        }
        for row in self.strategies:
            details[f"PnL {row.strategy} ({row.exchange})"] = f"{row.pnl:+.2f} USD"
        return details


def _strategy_weeks(before: PaperView, after: PaperView) -> tuple[StrategyWeek, ...]:
    """PnL de la semana = acumulado al cierre menos acumulado al inicio, por estrategia."""
    start = {(r.strategy, r.exchange): r for r in strategy_breakdown(before)}
    rows = []
    for row in strategy_breakdown(after):
        prev = start.get((row.strategy, row.exchange))
        rows.append(
            StrategyWeek(
                row.strategy,
                row.exchange,
                row.pnl - (prev.pnl if prev else ZERO),
                row.funding - (prev.funding if prev else ZERO),
                row.costs - (prev.costs if prev else ZERO),
                row.exposure,
            )
        )
    return tuple(rows)


def weekly_summary(events: Iterable[DomainEvent], monday: date) -> WeeklySummary:
    """Cifras de la semana ISO que empieza en ``monday``, a partir de los eventos del diario.

    Todo sale de comparar dos vistas del diario: al inicio del lunes y al final del domingo
    (UTC). Así las cifras de la semana cuadran con las acumuladas del dashboard.
    """
    opens = datetime.combine(monday, time(), UTC)
    closes = opens + WEEK
    history = [e for e in events if e.occurred_at < closes]
    before = build_view(e for e in history if e.occurred_at < opens)
    after = build_view(history)
    inside = [v for v in after.valuations if v.occurred_at >= opens]
    equity_start = before.equity or (inside[0].equity if inside else None)
    curve: list[tuple[datetime, Decimal]] = (
        [] if before.equity is None else [(opens, before.equity)]
    )
    curve += [(v.occurred_at, v.equity) for v in inside]
    return WeeklySummary(
        week=iso_week(monday),
        start=monday,
        end=monday + timedelta(days=6),
        orders=len(after.fills) - len(before.fills),
        funding=after.funding - before.funding,
        fees=after.fees - before.fees,
        slippage=after.slippage - before.slippage,
        equity_start=equity_start,
        equity_end=after.equity,
        max_drawdown=_max_drawdown([equity for _, equity in curve]),
        breaches=len(after.breaches) - len(before.breaches),
        kill_trips=sum(
            isinstance(e, KillSwitchTripped) for e in after.kill_events[len(before.kill_events) :]
        ),
        strategies=_strategy_weeks(before, after),
        curve=tuple(curve),
    )


def _max_drawdown(values: Iterable[Decimal]) -> Decimal:
    peak, worst = None, ZERO
    for value in values:
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            worst = max(worst, 1 - value / peak)
    return worst
