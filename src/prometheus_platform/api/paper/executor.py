"""Ejecutor genérico de señales del runner (PQ-116): cualquier ``Strategy`` opera en paper.

El carry tiene su propio camino en el runner (dos patas, funding, enmiendas 1.1 y 2). Este módulo
opera **cualquier otra** estrategia que cumpla el puerto ``Strategy`` (ADR-0011) sin tocar ese
núcleo. Cada ciclo hace dos cosas:

1. **Decidir**, una vez por cierre de vela horaria: construye la ``MarketSnapshot`` con la
   ventana ``lookback`` de la estrategia (velas de 1 h de sus instrumentos y funding de sus
   perpetuos), llama a ``on_snapshot`` y guarda cada ``Signal`` en el diario
   (``SignalGenerated``). Si falta la vela de algún instrumento, no decide con datos a medias: lo
   vuelve a intentar en el ciclo siguiente.
2. **Reconciliar por niveles**, como el carry: el peso vigente (con la latencia de la asignación)
   se convierte en una cantidad objetivo y se envía la diferencia, si supera la banda. Las órdenes
   pasan por ``pre_trade``, el kill-switch y el diario con el mismo ``_execute`` del runner.

**Reinicio.** Las señales y la última decisión salen del diario: el objetivo sigue vigente aunque
la API de velas no responda, y la misma vela no se decide dos veces. El estado interno de una
estrategia con memoria se reconstruye con su ventana ``lookback``, que es lo que la prueba de
contrato garantiza (paridad con la ventana recibida de forma incremental).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from prometheus_platform.domain.events import DomainEvent, SignalGenerated
from prometheus_platform.domain.market import MarketSnapshot, snapshot_at
from prometheus_platform.domain.model import InstrumentId, Side, Signal
from prometheus_platform.domain.ports import EventJournal, MarketDataFeed
from prometheus_platform.execution.allocation import (
    HOUR,
    StrategyAllocation,
    decision_time,
    effective_weight,
    outside_band,
    target_quantity,
)
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.portfolio_risk.risk import Leg, ProposedOrder, RiskLimits
from prometheus_platform.strategies.carry import is_perp, symbol_of

ZERO = Decimal(0)
# Margen tras el cierre de la vela para que la API la publique.
DATA_DELAY = timedelta(minutes=2)
# Si la vela sigue sin llegar pasado este tiempo, el heartbeat lo refleja.
MISSING_DATA_GRACE = timedelta(minutes=10)
log = get_logger(component="paper_executor")
Execute = Callable[[Sequence[ProposedOrder], str], int]


class InvalidSignalError(ValueError):
    """La estrategia devolvió una señal que incumple el contrato: no se registra ni se opera."""


@dataclass(frozen=True, slots=True)
class Account:
    """Lo que el runner sabe de la cuenta en este ciclo."""

    equity: Decimal
    held: Mapping[InstrumentId, Decimal]
    marks: Mapping[InstrumentId, Decimal]
    limits: RiskLimits
    sizing_buffer: Decimal

    def budget(self, allocation: StrategyAllocation) -> Decimal:
        """Capital asignado: su parte de la equity, sin pasar del nocional total permitido."""
        base = min(self.equity, self.limits.max_notional_total)
        return max(base, ZERO) * allocation.capital_share * (1 - self.sizing_buffer)

    @property
    def max_instrument(self) -> Decimal:
        return self.limits.max_notional_symbol * (1 - self.sizing_buffer)


class StrategyExecutor:
    def __init__(
        self,
        allocations: Sequence[StrategyAllocation],
        feed: MarketDataFeed,
        journal: EventJournal,
        events: Iterable[DomainEvent],
    ) -> None:
        self._allocations = tuple(allocations)
        self._feed = feed
        self._journal = journal
        ids = {a.strategy_id for a in self._allocations}
        self._signals: dict[tuple[str, InstrumentId], list[Signal]] = {}
        self._decided: dict[str, datetime] = {}
        for event in events:  # reinicio: señales y última decisión de cada estrategia
            if isinstance(event, SignalGenerated) and event.signal.strategy_id in ids:
                self._remember(event.signal)

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(symbol_of(i) for a in self._allocations for i in a.strategy.instruments)

    def describe(self) -> str:
        return " ".join(a.describe() for a in self._allocations)

    # --- decidir ---------------------------------------------------------------------------

    def decide(self, allocation: StrategyAllocation, now: datetime, problems: list[str]) -> int:
        """Llama a la estrategia si hay una vela horaria nueva; devuelve las señales guardadas."""
        as_of = decision_time(now, DATA_DELAY)
        last = self._decided.get(allocation.strategy_id)
        if last is not None and as_of <= last:
            return 0
        snapshot = self._snapshot(allocation, as_of)
        if snapshot is None:
            if now - as_of > MISSING_DATA_GRACE:
                problems.append(f"{allocation.strategy_id}: sin la vela de {as_of:%H:%M} UTC")
            return 0
        signals = allocation.strategy.on_snapshot(snapshot)
        _validate(allocation, as_of, signals)
        for signal in signals:
            self._journal.append(SignalGenerated(occurred_at=now, signal=signal))
            self._remember(signal)
        self._decided[allocation.strategy_id] = as_of
        log.info(
            "paper_strategy_decided",
            strategy_id=allocation.strategy_id,
            as_of=as_of.isoformat(),
            weights={str(s.instrument): str(s.target_weight) for s in signals},
        )
        return len(signals)

    def _snapshot(self, allocation: StrategyAllocation, as_of: datetime) -> MarketSnapshot | None:
        strategy = allocation.strategy
        start = as_of - strategy.lookback
        bars = {}
        funding = {}
        for instrument in strategy.instruments:
            rows = list(self._feed.bars(instrument, start - HOUR, as_of))
            if not rows or rows[-1].knowledge_time < as_of:
                return None  # la vela que cierra en as_of aún no está: no se decide a medias
            bars[instrument] = rows
            if is_perp(instrument):
                funding[instrument] = list(self._feed.funding_rates(instrument, start, as_of))
        return snapshot_at(as_of, bars=bars, funding=funding, lookback=strategy.lookback)

    def _remember(self, signal: Signal) -> None:
        self._signals.setdefault((signal.strategy_id, signal.instrument), []).append(signal)
        last = self._decided.get(signal.strategy_id)
        if last is None or signal.generated_at > last:
            self._decided[signal.strategy_id] = signal.generated_at

    # --- reconciliar -----------------------------------------------------------------------

    def reconcile(
        self, allocation: StrategyAllocation, account: Account, now: datetime, execute: Execute
    ) -> int:
        """Lleva cada instrumento de la estrategia a su peso vigente; devuelve las órdenes."""
        budget = account.budget(allocation)
        sent = 0
        for instrument in allocation.strategy.instruments:
            history = self._signals.get((allocation.strategy_id, instrument), [])
            signal, _ = effective_weight(history, now, allocation.execution_delay)
            if signal is None:
                continue  # aún no hay un peso vigente: no se toca la posición
            price = account.marks[instrument]
            quantity = account.held.get(instrument, ZERO)
            target = target_quantity(signal.target_weight, budget, price, account.max_instrument)
            if not outside_band(quantity, target, price, budget, allocation.rebalance_band):
                continue
            delta = target - quantity
            order = ProposedOrder(
                strategy_id=allocation.strategy_id,
                instrument=instrument,
                symbol=symbol_of(instrument),
                leg=Leg.PERP if is_perp(instrument) else Leg.SPOT,
                side=Side.BUY if delta > 0 else Side.SELL,
                quantity=abs(delta),
                price=price,
            )
            sent += execute([order], f"{allocation.strategy_id}-{signal.generated_at:%Y%m%dT%H%M}")
        return sent


def _validate(allocation: StrategyAllocation, as_of: datetime, signals: Sequence[Signal]) -> None:
    """Lo mismo que exige la prueba de contrato, también en vivo: una señal mala no se opera."""
    declared = set(allocation.strategy.instruments)
    seen: set[InstrumentId] = set()
    for s in signals:
        problem = (
            "otro strategy_id"
            if s.strategy_id != allocation.strategy_id
            else "generated_at distinto del as_of"
            if s.generated_at != as_of
            else f"{s.instrument} no declarado"
            if s.instrument not in declared
            else f"dos señales para {s.instrument}"
            if s.instrument in seen
            else ""
        )
        if problem:
            raise InvalidSignalError(f"{allocation.strategy_id}: {problem}")
        seen.add(s.instrument)
