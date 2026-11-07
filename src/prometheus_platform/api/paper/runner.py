"""Runner del paper trading del carry H2 (PQ-54): raíz de composición del ciclo en vivo.

**Por niveles, no por flancos.** Cada liquidación procesada deja en el diario un ``FundingSettled``
con el **estado deseado** del símbolo (abierto o cerrado) y si toca rebalancear. Cada ciclo
**reconcilia** las posiciones con ese estado. Así, un fallo entre dos patas, una excepción o una
caída del proceso entre la decisión y las órdenes se corrigen solos en el ciclo siguiente: el
estado deseado sigue en el diario y la reconciliación vuelve a intentarlo.

Cada ciclo (``tick``), en este orden:

1. ``KillSwitch.observe()``: si está activado, se cierra todo y no se abre nada;
2. precios de mercado y valoración de la cartera;
3. ``RiskManager.monitor`` y ``enforce`` (las violaciones graves activan el kill-switch);
4. por símbolo:
   - las liquidaciones nuevas: cobro o pago del funding y decisión con **la misma regla que el
     backtest** (``domain/carry_rules``);
   - la reconciliación con el estado deseado. Respeta la latencia de 1 h de la enmienda 1.1: la
     orden de una decisión en *t* no se envía antes de *t + 1 h*;
5. ``PortfolioValued`` en el diario y el heartbeat en disco.

**Reinicio.** Las posiciones y el efectivo viven en el bróker (el simulado los guarda en disco).
Las liquidaciones procesadas, el estado deseado, los rebalanceos hechos y la equity de inicio del
día salen del diario (``replay``).

**Arranque en frío.** Sin liquidaciones previas en el diario, el estado de la histéresis se
reconstruye recorriendo el historial reciente (``CarryStrategy.walk``).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
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
from prometheus_platform.domain.model import FundingRate, InstrumentId, Side, Signal
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
# Enmienda 1.1 del pre-registro: las órdenes se ejecutan en la vela que abre en t + 1 h.
EXECUTION_DELAY = timedelta(hours=1)
log = get_logger(component="paper_runner")
Marks = dict[InstrumentId, Decimal]


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
    # por encima del límite de riesgo (1x en paper). La paridad con el backtest se exige en las
    # decisiones, no en el tamaño (ver el runbook).
    sizing_buffer: Decimal = Decimal("0.02")
    valuation_every: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("El runner necesita al menos un símbolo")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError(f"Símbolos repetidos: {self.symbols}")
        if self.history_limit < self.params.k:
            raise ValueError("history_limit debe ser >= k")
        if not ZERO <= self.sizing_buffer < 1:
            raise ValueError("sizing_buffer debe estar en [0, 1)")

    def describe(self) -> str:
        p = self.params
        return (
            f"k={p.k} theta={p.theta} always_on={p.always_on} history_limit={self.history_limit} "
            f"sizing_buffer={self.sizing_buffer} execution_delay={EXECUTION_DELAY}"
        )


@dataclass(frozen=True, slots=True)
class TickReport:
    ok: bool
    equity: Decimal | None = None
    kill_switch: bool = False
    settlements: int = 0
    orders: int = 0
    detail: str = ""


@dataclass
class _Target:
    """Estado deseado de un símbolo según la última liquidación procesada."""

    funding_time: datetime
    open: bool
    previous_open: bool  # lo que valía antes de esta decisión: rige hasta t + 1 h

    def desired(self, now: datetime) -> bool:
        """Abierto o cerrado vigente en ``now``, con la latencia de la enmienda 1.1."""
        return self.previous_open if now < self.funding_time + EXECUTION_DELAY else self.open

    @property
    def tag(self) -> str:
        return f"{self.funding_time:%Y%m%dT%H%M}"


@dataclass
class _Recovered:
    processed: dict[str, datetime] = field(default_factory=dict)
    targets: dict[str, _Target] = field(default_factory=dict)
    # Rebalanceo pedido y aún no enviado, por símbolo: la hora de la decisión que lo pidió.
    # Va aparte del estado deseado porque, con funding de 1 h, la liquidación siguiente llega
    # antes de que pase la latencia y no debe borrarlo.
    rebalance_due: dict[str, datetime] = field(default_factory=dict)
    day: date | None = None
    day_start_equity: Decimal | None = None


def _recover(events: Iterable[DomainEvent]) -> _Recovered:
    state = _Recovered()
    for event in events:
        if isinstance(event, FundingSettled):
            last = state.processed.get(event.symbol)
            if last is None or event.funding_time > last:
                state.processed[event.symbol] = event.funding_time
                state.targets[event.symbol] = _Target(
                    event.funding_time, event.target_open, event.was_open
                )
                if event.rebalance:
                    state.rebalance_due.setdefault(event.symbol, event.funding_time)
                elif not event.target_open:
                    state.rebalance_due.pop(event.symbol, None)
        elif isinstance(event, OrderSubmitted):
            symbol = symbol_of(event.instrument)
            due = state.rebalance_due.get(symbol)
            if due is not None and event.client_order_id.startswith(
                f"{due:%Y%m%dT%H%M}-rebalanceo-"
            ):
                del state.rebalance_due[symbol]
        elif isinstance(event, PortfolioValued) and event.occurred_at.date() != state.day:
            state.day, state.day_start_equity = event.occurred_at.date(), event.equity
    return state


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
        foreign = sorted({symbol_of(i) for i in broker.positions()} - set(config.symbols))
        if foreign:  # no se podrían valorar ni cerrar, ni siquiera con el kill-switch
            raise ValueError(
                f"El bróker tiene posiciones en {', '.join(foreign)}, fuera de --symbols: "
                "inclúyelos o ciérralos antes"
            )
        recovered = _recover(journal.replay())
        self._processed = recovered.processed
        self._targets = recovered.targets
        self._rebalance_due = recovered.rebalance_due
        self._day = recovered.day
        self._day_start = recovered.day_start_equity
        self._last_valued: datetime | None = None
        self._imbalanced_since: dict[str, datetime] = {}
        self._warnings: set[str] = set()  # violaciones leves vigentes: se registran al aparecer
        self._rejected: dict[str, str] = {}  # último rechazo por símbolo: se registra al cambiar

    # --- ciclo -----------------------------------------------------------------------------

    def start(self) -> None:
        self._journal.append(
            RunnerStarted(
                occurred_at=self._clock.now(),
                broker=self._broker.name,
                strategy_id=self.config.strategy_id,
                symbols=",".join(self.config.symbols),
                params=self.config.describe(),
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

        problems: list[str] = []
        orders = 0
        if killed:
            orders += self._execute(flatten_orders(book), f"kill-{now:%Y%m%dT%H%M%S}", marks, now)
        settlements = 0
        for symbol in self.config.symbols:
            # Por separado: sin liquidaciones nuevas (API de funding caída) se sigue
            # reconciliando con el estado deseado que ya está en el diario, p. ej. una salida.
            settlements += self._guarded(
                symbol, "liquidar", problems, self._settle, symbol, marks, now, problems
            )
            if not killed:
                orders += self._guarded(
                    symbol, "reconciliar", problems, self._reconcile, symbol, marks, now
                )

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
        detail = "; ".join(problems)
        self._write_heartbeat(now, ok=not problems, detail=detail, killed=killed)
        return TickReport(not problems, equity, killed, settlements, orders, detail)

    def run(
        self,
        *,
        interval_seconds: float,
        max_ticks: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bool:
        """Bucle del proceso. Devuelve si el último ciclo fue sano (para ``--once``)."""
        if interval_seconds <= 0:
            raise ValueError(f"El intervalo debe ser positivo: {interval_seconds}")
        self.start()
        ticks, healthy = 0, False
        while max_ticks is None or ticks < max_ticks:
            try:
                healthy = self.tick().ok
            except Exception as exc:  # el proceso no muere: el heartbeat refleja el fallo
                healthy = False
                log.error("paper_tick_failed", error=type(exc).__name__, detail=str(exc)[:200])
                self._write_heartbeat(
                    self._clock.now(), ok=False, detail=type(exc).__name__, killed=self._kill.active
                )
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                sleep(interval_seconds)
        return healthy

    def _guarded(
        self,
        symbol: str,
        step: str,
        problems: list[str],
        fn: Callable[..., int],
        *args: object,
    ) -> int:
        """Un símbolo con problemas no detiene a los demás; el fallo queda en el heartbeat."""
        try:
            return fn(*args)
        except Exception as exc:
            problems.append(f"{symbol} ({step}): {type(exc).__name__}")
            log.error(
                "paper_symbol_failed",
                symbol=symbol,
                step=step,
                error=type(exc).__name__,
                detail=str(exc)[:200],
            )
            return 0

    # --- liquidaciones y decisiones --------------------------------------------------------

    def _settle(self, symbol: str, marks: Marks, now: datetime, problems: list[str]) -> int:
        """Liquidaciones nuevas del símbolo: cobro del funding y estado deseado en el diario."""
        history = self._market.recent_funding(symbol, self.config.history_limit)
        if not history:
            raise MarketUnavailableError(f"{symbol}: sin liquidaciones recientes")
        since = self._processed.get(symbol)
        target = self._targets.get(symbol)
        if since is None:  # arranque en frío: la histéresis se reconstruye con el historial
            walked = self._strategy.walk(history, since=None, is_open=False)
            start = _final_state(walked[:-1], start=False)
            decisions = walked[-1:]  # solo la última cuenta como procesada
        else:
            if history[0].funding_time > since:
                # Entre «since» y la ventana pudo haber liquidaciones que ya no se ven.
                problems.append(f"{symbol}: hueco de liquidaciones desde {since.isoformat()}")
                log.error("paper_funding_gap", symbol=symbol, since=since.isoformat())
            start = target.open if target else False
            decisions = self._strategy.walk(history, since=since, is_open=start)
        rates = {r.funding_time: r for r in history}
        state = start
        for decision in decisions:
            previous, state = state, _final_state([decision], start=state)
            self._record(
                symbol,
                rates[decision.funding_time],
                decision,
                previous=previous,
                state=state,
                marks=marks,
                now=now,
            )
        return len(decisions)

    def _record(  # noqa: PLR0913 - una liquidación con su decisión y el estado que deja
        self,
        symbol: str,
        rate: FundingRate,
        decision: CarryDecision,
        *,
        previous: bool,
        state: bool,
        marks: Marks,
        now: datetime,
    ) -> None:
        perp = perp_instrument(symbol)
        amount = self._broker.settle_funding(perp, rate.funding_time, rate.rate, marks[perp])
        held = self._broker.positions()
        hedged = held.get(spot_instrument(symbol), ZERO) > 0 > held.get(perp, ZERO)
        rebalance = (  # enmienda 2: solo con la posición abierta (como el backtest)
            state
            and previous
            and hedged
            and decision.action is CarryAction.MANTENER
            and decision.s_k is not None
            and self._drifted(symbol, marks)
        )
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
                target_open=state,
                was_open=previous,
                rebalance=rebalance,
            )
        )
        self._processed[symbol] = rate.funding_time
        self._targets[symbol] = _Target(rate.funding_time, state, previous)
        if rebalance:  # el pendiente más antiguo manda: uno nuevo no lo aplaza
            self._rebalance_due.setdefault(symbol, rate.funding_time)
        elif not state:
            self._rebalance_due.pop(symbol, None)
        log.info(
            "paper_funding_settled",
            symbol=symbol,
            funding_time=rate.funding_time.isoformat(),
            action=decision.action.value,
            target_open=state,
            rebalance=rebalance,
            amount=str(amount),
        )

    def _drifted(self, symbol: str, marks: Marks) -> bool:
        """Enmienda 2: alguna pata se desvía más de un 10 % de su objetivo."""
        held = self._broker.positions()
        spot, perp = spot_instrument(symbol), perp_instrument(symbol)
        spot_value = held.get(spot, ZERO) * marks[spot]
        perp_value = -held.get(perp, ZERO) * marks[perp]
        leg = self._leg_target(marks)
        return needs_rebalance(float(spot_value), float(perp_value), float(leg))

    # --- reconciliación --------------------------------------------------------------------

    def _reconcile(self, symbol: str, marks: Marks, now: datetime) -> int:
        """Lleva las posiciones del símbolo al estado deseado vigente."""
        target = self._targets.get(symbol)
        if target is None:
            return 0
        spot, perp = spot_instrument(symbol), perp_instrument(symbol)
        held = self._broker.positions()
        q_spot, q_perp = held.get(spot, ZERO), held.get(perp, ZERO)
        due = self._rebalance_due.get(symbol)
        if not target.desired(now):
            if not (q_spot or q_perp):
                return 0
            label, tag, leg = "salida", target.tag, ZERO
        elif not self._hedged(q_spot * marks[spot], q_perp * marks[perp]):
            # Sin posición, con una pata sola, con un signo cambiado o desbalanceada (p. ej. un
            # rebalanceo que se quedó a medias): las dos patas al objetivo.
            label = "entrada" if not (q_spot or q_perp) else "reparacion"
            tag, leg = target.tag, self._leg_target(marks)
        elif due is not None and now >= due + EXECUTION_DELAY:
            label, tag, leg = "rebalanceo", f"{due:%Y%m%dT%H%M}", self._leg_target(marks)
        else:
            return 0
        targets = {spot: leg / marks[spot], perp: -leg / marks[perp]}
        orders = [
            ProposedOrder(
                strategy_id=self.config.strategy_id,
                instrument=instrument,
                symbol=symbol,
                leg=Leg.PERP if is_perp(instrument) else Leg.SPOT,
                side=Side.BUY if delta > 0 else Side.SELL,
                quantity=abs(delta),
                price=marks[instrument],
            )
            for instrument, goal in targets.items()
            if (delta := goal - held.get(instrument, ZERO))
        ]
        sent = self._execute(orders, f"{tag}-{label}", marks, now, targets=targets)
        if sent and label == "rebalanceo":
            del self._rebalance_due[symbol]
        return sent

    def _hedged(self, spot_value: Decimal, perp_value: Decimal) -> bool:
        """Spot largo, perpetuo corto y desbalance por debajo de la mitad del límite de riesgo.

        La mitad deja margen: se repara antes de que ``monitor`` lo cuente como violación.
        """
        if not spot_value > 0 > perp_value:
            return False
        imbalance = abs(spot_value + perp_value) / max(spot_value, -perp_value)
        return imbalance <= self._risk.limits.max_hedge_imbalance / 2

    def _leg_target(self, marks: Marks) -> Decimal:
        """Nocional por pata: equity / n / 2 (1x siempre, enmienda 2), acotado por los límites.

        Sin la cota, al crecer la equity las entradas chocarían con el nocional máximo y se
        rechazarían siempre. El margen ``sizing_buffer`` deja sitio a comisiones y redondeos.
        """
        n = len(self.config.symbols)
        limits = self._risk.limits
        equity = self._broker.equity(marks)
        share = min(equity / n, limits.max_notional_symbol, limits.max_notional_total / n)
        return share / 2 * (1 - self.config.sizing_buffer)

    def _signal(self, targets: dict[InstrumentId, Decimal], marks: Marks, now: datetime) -> None:
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

    # --- órdenes ---------------------------------------------------------------------------

    def _execute(
        self,
        orders: Sequence[ProposedOrder],
        tag: str,
        marks: Marks,
        now: datetime,
        *,
        targets: dict[InstrumentId, Decimal] | None = None,
    ) -> int:
        """Aprueba **todas** las patas antes de enviar ninguna: una pata sola es un desbalance.

        Si una pata falla al enviarse, la otra queda sola. La reconciliación del ciclo siguiente
        la completa o la cierra, dentro de la gracia de ``monitor``.
        """
        if not orders:
            return 0
        symbol = orders[0].symbol
        book = self._book(marks, now)
        for order in orders:
            decision = self._risk.pre_trade(order, book, kill_switch_active=self._kill.active)
            if not decision.approved:
                detail = f"{order.instrument.symbol} {order.side.value}: {decision.detail}"
                if self._rejected.get(symbol) != decision.rule:  # una línea por rechazo nuevo
                    log.warning("paper_order_rejected", rule=decision.rule, detail=detail)
                    self._journal.append(
                        RiskLimitBreached(occurred_at=now, rule=decision.rule, detail=detail)
                    )
                    self._rejected[symbol] = decision.rule
                return 0
            # La pata aprobada cuenta como ejecutada para aprobar la siguiente: ``pre_trade`` usa
            # las órdenes pendientes para saber si una orden reduce, no para sumar exposición.
            book = _assume_filled(book, order)
        self._rejected.pop(symbol, None)
        if targets is not None:
            self._signal(targets, marks, now)
        log.info("paper_orders", symbol=symbol, tag=tag, orders=len(orders))
        sent = 0
        for order in orders:
            # Único aunque la misma decisión se ejecute dos veces (reintento o rearme).
            client_order_id = f"{tag}-{now:%Y%m%dT%H%M%S}-{order.instrument.symbol}"
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

    def _marks(self) -> Marks:
        marks: Marks = {}
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

    def _book(self, marks: Marks, now: datetime) -> PortfolioSnapshot:
        equity = self._broker.equity(marks)
        positions = [
            Position(
                instrument=instrument,
                symbol=symbol_of(instrument),
                leg=Leg.PERP if is_perp(instrument) else Leg.SPOT,
                quantity=quantity,
                mark_price=marks[instrument],
            )
            for instrument, quantity in self._broker.positions().items()
        ]
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
