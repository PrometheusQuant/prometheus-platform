"""Runner del paper trading del carry H2 (PQ-54): raíz de composición del ciclo en vivo.

Cada ciclo (``tick``), en este orden:

1. ``KillSwitch.observe()``: si está activado, cancela y, más abajo, cierra todo sin abrir nada;
2. precios de mercado y valoración de la cartera;
3. ``RiskManager.monitor`` y ``enforce`` (las violaciones graves activan el kill-switch);
4. por símbolo, las liquidaciones nuevas: cobro o pago del funding, decisión con la **misma regla
   que el backtest** (``domain/carry_rules``) y órdenes, cada una aprobada por ``pre_trade``;
5. ``PortfolioValued`` en el diario y el heartbeat en disco.

**Reinicio.** Las posiciones y el efectivo viven en el bróker (el simulado los guarda en disco).
Las liquidaciones procesadas y la equity de inicio del día salen del diario (``replay``). El
bróker aplica cada liquidación una sola vez (idempotente por ``funding_time``).

**Arranque en frío.** Sin liquidaciones previas en el diario, el estado de la histéresis se
reconstruye recorriendo el historial reciente (``CarryStrategy.walk``) y se actúa sobre la última
liquidación. Así el paper trading arranca en el mismo estado en que estaría el backtest.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from prometheus_platform.domain.carry_rules import CarryAction, CarryParams, needs_rebalance
from prometheus_platform.domain.events import (
    DomainEvent,
    FundingSettled,
    OrderSubmitted,
    PortfolioValued,
    RiskLimitBreached,
    RunnerStarted,
    SignalGenerated,
)
from prometheus_platform.domain.model import InstrumentId, Side, Signal
from prometheus_platform.domain.ports import Broker, Clock, EventJournal, LiveMarket
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch, enforce
from prometheus_platform.portfolio_risk.risk import (
    Breach,
    Leg,
    PortfolioSnapshot,
    Position,
    ProposedOrder,
    RiskManager,
    flatten_orders,
    hedge_imbalances,
)
from prometheus_platform.strategies.carry import (
    CarryDecision,
    CarryStrategy,
    is_perp,
    perp_instrument,
    spot_instrument,
    symbol_of,
)

ZERO = Decimal(0)
log = get_logger(component="paper_runner")


class MarketUnavailableError(RuntimeError):
    """Falta un precio o una liquidación: en este ciclo no se decide con datos incompletos."""


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    symbols: tuple[str, ...]
    params: CarryParams
    strategy_id: str = "carry-h2"
    # Liquidaciones que se piden en cada ciclo: k para la señal y el resto para la histéresis.
    history_limit: int = 90
    # Margen bajo 1x al dimensionar: comisiones y redondeos no deben empujar el apalancamiento
    # por encima del límite de riesgo (que es 1x en paper). Única diferencia de tamaño con el
    # backtest; la paridad se exige en las decisiones.
    sizing_buffer: Decimal = Decimal("0.02")
    valuation_every: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("El runner necesita al menos un símbolo")
        if self.history_limit < self.params.k:
            raise ValueError("history_limit debe ser >= k")
        if not ZERO <= self.sizing_buffer < 1:
            raise ValueError("sizing_buffer debe estar en [0, 1)")


@dataclass(frozen=True, slots=True)
class TickReport:
    ok: bool
    equity: Decimal | None = None
    kill_switch: bool = False
    settlements: int = 0
    orders: int = 0
    detail: str = ""


@dataclass
class _Recovered:
    processed: dict[str, datetime]
    day: date | None
    day_start_equity: Decimal | None


def _recover(events: Iterable[DomainEvent]) -> _Recovered:
    processed: dict[str, datetime] = {}
    day: date | None = None
    start: Decimal | None = None
    for event in events:
        if isinstance(event, FundingSettled):
            last = processed.get(event.symbol)
            if last is None or event.funding_time > last:
                processed[event.symbol] = event.funding_time
        elif isinstance(event, PortfolioValued) and event.occurred_at.date() != day:
            day, start = event.occurred_at.date(), event.equity
    return _Recovered(processed, day, start)


def _final_state(decisions: Iterable[CarryDecision], *, start: bool) -> bool:
    """Abierto o cerrado tras aplicar las decisiones en orden."""
    state = start
    for d in decisions:
        if d.action is CarryAction.ENTRAR:
            state = True
        elif d.action is CarryAction.SALIR:
            state = False
    return state


def _assume_filled(book: PortfolioSnapshot, order: ProposedOrder) -> PortfolioSnapshot:
    """La cartera como si ``order`` ya se hubiera ejecutado a su precio."""
    held = book.position(order.instrument)
    quantity = (held.quantity if held else ZERO) + order.signed_quantity
    others = [p for p in book.positions if p.instrument != order.instrument]
    if quantity:
        mark = max(order.price, held.mark_price) if held else order.price
        others.append(Position(order.instrument, order.symbol, order.leg, quantity, mark))
    return replace(book, positions=others)


class PaperRunner:
    def __init__(  # noqa: PLR0913 - raíz de composición: cada dependencia es un puerto
        self,
        *,
        config: RunnerConfig,
        market: LiveMarket,
        broker: Broker,
        journal: EventJournal,
        kill_switch: KillSwitch,
        risk: RiskManager,
        clock: Clock,
        heartbeat_path: Path,
    ) -> None:
        self.config = config
        self._market = market
        self._broker = broker
        self._journal = journal
        self._kill = kill_switch
        self._risk = risk
        self._clock = clock
        self._heartbeat = heartbeat_path
        self._strategy = CarryStrategy(config.symbols, config.params, config.strategy_id)
        recovered = _recover(journal.replay())
        self._processed = recovered.processed
        self._day = recovered.day
        self._day_start = recovered.day_start_equity
        self._last_valued: datetime | None = None
        self._imbalanced_since: dict[str, datetime] = {}
        self._warnings: set[str] = set()  # violaciones leves vigentes: se registran al aparecer

    # --- ciclo -----------------------------------------------------------------------------

    def start(self) -> None:
        p = self.config.params
        self._journal.append(
            RunnerStarted(
                occurred_at=self._clock.now(),
                broker=self._broker.name,
                strategy_id=self.config.strategy_id,
                symbols=",".join(self.config.symbols),
                params=f"k={p.k} theta={p.theta} always_on={p.always_on}",
            )
        )
        log.info("paper_runner_started", broker=self._broker.name, symbols=self.config.symbols)

    def tick(self) -> TickReport:
        now = self._clock.now()
        killed = self._kill.observe()
        try:
            marks = self._marks()
        except MarketUnavailableError as exc:
            log.error("paper_market_unavailable", detail=str(exc))
            self._write_heartbeat(now, ok=False, detail=str(exc), killed=killed)
            return TickReport(ok=False, kill_switch=killed, detail=str(exc))

        self._roll_day(now, self._broker.equity(marks))
        book = self._book(marks, now)
        if not killed:
            enforce(
                self._to_record(self._risk.monitor(book)), self._kill, self._journal, self._clock
            )
            killed = self._kill.active

        orders = 0
        if killed:
            orders += self._execute(flatten_orders(book), f"kill-{now:%Y%m%dT%H%M%S}", marks, now)
        settlements = 0
        for symbol in self.config.symbols:
            try:
                n_settled, n_orders = self._process_symbol(symbol, marks, now, trade=not killed)
            except Exception as exc:  # un símbolo con problemas no detiene a los demás
                log.error(
                    "paper_symbol_skipped",
                    symbol=symbol,
                    error=type(exc).__name__,
                    detail=str(exc)[:200],
                )
                continue
            settlements += n_settled
            orders += n_orders

        equity = self._broker.equity(marks)
        if orders or settlements or self._valuation_due(now):
            self._journal.append(
                PortfolioValued(
                    occurred_at=now,
                    equity=equity,
                    cash=self._broker.cash(),
                    gross_notional=self._book(marks, now).gross_notional,
                )
            )
            self._last_valued = now
        self._write_heartbeat(now, ok=True, detail="", killed=killed)
        return TickReport(True, equity, killed, settlements, orders)

    def run(
        self,
        *,
        interval_seconds: float,
        max_ticks: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Bucle del proceso. Un error inesperado se registra y el ciclo siguiente reintenta."""
        self.start()
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            try:
                self.tick()
            except Exception as exc:  # el proceso no muere: el heartbeat refleja el fallo
                log.error("paper_tick_failed", error=type(exc).__name__, detail=str(exc)[:200])
                self._write_heartbeat(
                    self._clock.now(), ok=False, detail=type(exc).__name__, killed=self._kill.active
                )
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                sleep(interval_seconds)
        return ticks

    # --- por símbolo -----------------------------------------------------------------------

    def _process_symbol(
        self, symbol: str, marks: dict[InstrumentId, Decimal], now: datetime, *, trade: bool
    ) -> tuple[int, int]:
        """Liquidaciones nuevas del símbolo: cobro del funding, decisión y órdenes."""
        history = self._market.recent_funding(symbol, self.config.history_limit)
        if not history:
            raise MarketUnavailableError(f"{symbol}: sin liquidaciones recientes")
        since = self._processed.get(symbol)
        perp = perp_instrument(symbol)
        is_open = self._broker.positions().get(perp, ZERO) != 0
        if since is None:  # arranque en frío: la histéresis se reconstruye con el historial
            walked = self._strategy.walk(history, since=None, is_open=False)
            want_open = _final_state(walked, start=False)
            decisions = walked[-1:]  # solo la última cuenta como procesada
        else:
            decisions = self._strategy.walk(history, since=since, is_open=is_open)
            want_open = _final_state(decisions, start=is_open)
        if not decisions:
            return 0, 0

        rates = {r.funding_time: r for r in history}
        for decision in decisions:
            rate = rates[decision.funding_time]
            amount = self._broker.settle_funding(perp, rate.funding_time, rate.rate, marks[perp])
            self._journal.append(
                FundingSettled(
                    occurred_at=now,
                    symbol=symbol,
                    funding_time=rate.funding_time,
                    rate=rate.rate,
                    interval_hours=rate.interval_hours,
                    amount=amount,
                    action=decision.action.value,
                    s_k="" if decision.s_k is None else repr(decision.s_k),
                )
            )
            self._processed[symbol] = rate.funding_time
            log.info(
                "paper_funding_settled",
                symbol=symbol,
                funding_time=rate.funding_time.isoformat(),
                action=decision.action.value,
                amount=str(amount),
            )
        if not trade:
            return len(decisions), 0
        return len(decisions), self._act(symbol, decisions[-1], want_open, marks, now)

    def _act(
        self,
        symbol: str,
        last: CarryDecision,
        want_open: bool,
        marks: dict[InstrumentId, Decimal],
        now: datetime,
    ) -> int:
        spot, perp = spot_instrument(symbol), perp_instrument(symbol)
        leg = self._leg_target(marks) if want_open else ZERO
        held = self._broker.positions()
        is_open = held.get(perp, ZERO) != 0
        if want_open and is_open:
            spot_value = held.get(spot, ZERO) * marks[spot]
            perp_value = -held.get(perp, ZERO) * marks[perp]
            rebalance = last.action is CarryAction.MANTENER and last.s_k is not None
            if not (
                rebalance and needs_rebalance(float(spot_value), float(perp_value), float(leg))
            ):
                return 0
            label = "rebalanceo"
        elif want_open == is_open:
            return 0
        else:
            label = "entrada" if want_open else "salida"

        targets = {spot: leg / marks[spot], perp: -leg / marks[perp]}
        orders = []
        for instrument, target in targets.items():
            delta = target - held.get(instrument, ZERO)
            if delta:
                orders.append(
                    ProposedOrder(
                        strategy_id=self.config.strategy_id,
                        instrument=instrument,
                        symbol=symbol,
                        leg=Leg.PERP if is_perp(instrument) else Leg.SPOT,
                        side=Side.BUY if delta > 0 else Side.SELL,
                        quantity=abs(delta),
                        price=marks[instrument],
                    )
                )
        if not orders:
            return 0
        equity = self._broker.equity(marks)
        for instrument, target in targets.items():
            weight = target * marks[instrument] / equity if equity > 0 else ZERO
            self._journal.append(
                SignalGenerated(
                    occurred_at=now,
                    signal=Signal(
                        strategy_id=self.config.strategy_id,
                        instrument=instrument,
                        generated_at=now,
                        target_weight=max(Decimal(-1), min(Decimal(1), weight)),
                    ),
                )
            )
        log.info("paper_decision", symbol=symbol, label=label, s_k=last.s_k)
        return self._execute(orders, f"{last.funding_time:%Y%m%dT%H%M}-{label}", marks, now)

    def _leg_target(self, marks: dict[InstrumentId, Decimal]) -> Decimal:
        """Nocional por pata: equity / n símbolos / 2 (1x, enmienda 2), menos el margen."""
        equity = self._broker.equity(marks)
        share = equity / len(self.config.symbols) / 2
        return share * (1 - self.config.sizing_buffer)

    # --- órdenes ---------------------------------------------------------------------------

    def _execute(
        self,
        orders: Sequence[ProposedOrder],
        tag: str,
        marks: dict[InstrumentId, Decimal],
        now: datetime,
    ) -> int:
        """Aprueba **todas** las patas antes de enviar ninguna: una pata sola es un desbalance."""
        if not orders:
            return 0
        book = self._book(marks, now)
        for order in orders:
            decision = self._risk.pre_trade(order, book, kill_switch_active=self._kill.active)
            if not decision.approved:
                detail = f"{order.instrument.symbol} {order.side.value}: {decision.detail}"
                log.warning("paper_order_rejected", rule=decision.rule, detail=detail)
                self._journal.append(
                    RiskLimitBreached(occurred_at=now, rule=decision.rule, detail=detail)
                )
                return 0
            # La pata aprobada cuenta como ejecutada para aprobar la siguiente: ``pre_trade`` usa
            # las órdenes pendientes para saber si una orden reduce, no para sumar exposición.
            book = _assume_filled(book, order)
        sent = 0
        for order in orders:
            client_order_id = f"{tag}-{order.instrument.symbol}"
            self._journal.append(
                OrderSubmitted(
                    occurred_at=now,
                    client_order_id=client_order_id,
                    instrument=order.instrument,
                    side=order.side,
                    quantity=order.quantity,
                )
            )
            self._broker.submit(client_order_id, order.instrument, order.side, order.quantity)
            for fill in self._broker.drain_fills():
                self._journal.append(fill)
            sent += 1
        return sent

    # --- estado ----------------------------------------------------------------------------

    def _marks(self) -> dict[InstrumentId, Decimal]:
        marks: dict[InstrumentId, Decimal] = {}
        for symbol in self.config.symbols:
            try:
                spot_price, mark = self._market.prices(symbol)
            except Exception as exc:
                raise MarketUnavailableError(f"{symbol}: {type(exc).__name__}") from exc
            for instrument, price in (
                (spot_instrument(symbol), spot_price),
                (perp_instrument(symbol), mark),
            ):
                if not price.is_finite() or price <= 0:
                    raise MarketUnavailableError(f"{instrument.symbol}: precio inválido {price}")
                marks[instrument] = price
        return marks

    def _book(self, marks: dict[InstrumentId, Decimal], now: datetime) -> PortfolioSnapshot:
        equity = self._broker.equity(marks)
        positions = []
        for instrument, quantity in self._broker.positions().items():
            mark = marks.get(instrument)
            if mark is None:  # posición fuera del universo configurado: no se puede valorar
                raise MarketUnavailableError(f"{instrument.symbol}: posición sin precio")
            positions.append(
                Position(
                    instrument=instrument,
                    symbol=symbol_of(instrument),
                    leg=Leg.PERP if is_perp(instrument) else Leg.SPOT,
                    quantity=quantity,
                    mark_price=mark,
                )
            )
        return PortfolioSnapshot(
            equity=equity,
            start_of_day_equity=self._day_start or equity,
            positions=positions,
            imbalance_age_seconds=self._imbalance_ages(positions, now),
        )

    def _imbalance_ages(self, positions: Sequence[Position], now: datetime) -> dict[str, float]:
        """Desde cuándo dura cada desbalance de la cobertura (lo exige ``monitor``)."""
        limit = self._risk.limits.max_hedge_imbalance
        ages = {}
        current = hedge_imbalances(positions)
        for symbol in list(self._imbalanced_since):
            if current.get(symbol, ZERO) <= limit:
                del self._imbalanced_since[symbol]
        for symbol, imbalance in current.items():
            if imbalance > limit:
                since = self._imbalanced_since.setdefault(symbol, now)
                ages[symbol] = (now - since).total_seconds()
        return ages

    def _roll_day(self, now: datetime, equity: Decimal) -> None:
        """Equity de referencia de la pérdida diaria: la primera valoración del día UTC."""
        if self._day != now.date() or self._day_start is None:
            self._day, self._day_start = now.date(), equity

    def _to_record(self, breaches: Sequence[Breach]) -> list[Breach]:
        """Las graves siempre; las leves, solo al aparecer (no una línea por ciclo)."""
        current = {b.rule for b in breaches if not b.trips_kill_switch}
        selected = [b for b in breaches if b.trips_kill_switch or b.rule not in self._warnings]
        self._warnings = current
        return selected

    def _valuation_due(self, now: datetime) -> bool:
        return self._last_valued is None or now - self._last_valued >= self.config.valuation_every

    def _write_heartbeat(self, now: datetime, *, ok: bool, detail: str, killed: bool) -> None:
        payload = {
            "at": now.isoformat(),
            "ok": ok,
            "detail": detail,
            "broker": self._broker.name,
            "kill_switch": killed,
        }
        try:
            self._heartbeat.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._heartbeat.with_name(f"{self._heartbeat.name}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._heartbeat)
        except OSError as exc:  # sin heartbeat el monitor externo avisa: no se detiene el ciclo
            log.error("paper_heartbeat_failed", error=type(exc).__name__)
