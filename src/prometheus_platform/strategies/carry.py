"""Estrategia del carry de funding para el paper trading (PQ-54).

Decide con ``domain/carry_rules.decide``, la misma función que usa el backtest. Solo traduce las
liquidaciones recientes en una acción y en el objetivo de cada pata. No conoce la ejecución ni el
riesgo: eso lo hacen el runner, ``portfolio_risk`` y el bróker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from prometheus_platform.domain.carry_rules import (
    CarryAction,
    CarryParams,
    annualize,
    decide,
    signal,
)
from prometheus_platform.domain.market import MarketSnapshot
from prometheus_platform.domain.model import FundingRate, InstrumentId, Signal, Venue

PERP_SUFFIX = "-PERP"
MAX_INTERVAL_HOURS = 8
# Configuración de H2 elegida en la evaluación (docs/estrategias/01-carry/evaluacion.md).
H2_PARAMS = CarryParams(k=9, theta=0.20)


def spot_instrument(symbol: str, venue: Venue = Venue.BINANCE) -> InstrumentId:
    return InstrumentId(symbol, venue)


def perp_instrument(symbol: str, venue: Venue = Venue.BINANCE) -> InstrumentId:
    return InstrumentId(f"{symbol}{PERP_SUFFIX}", venue)


def symbol_of(instrument: InstrumentId) -> str:
    return instrument.symbol.removesuffix(PERP_SUFFIX)


def is_perp(instrument: InstrumentId) -> bool:
    return instrument.symbol.endswith(PERP_SUFFIX)


@dataclass(frozen=True, slots=True)
class CarryDecision:
    symbol: str
    funding_time: datetime
    action: CarryAction
    s_k: float | None
    last_rate: float


class CarryStrategy:
    """Carry delta-neutral: spot largo y perpetuo corto. H2 usa ``H2_PARAMS``.

    Cumple el puerto ``Strategy`` (``on_snapshot``) y además expone ``evaluate`` y ``walk``, que
    usa el runner del carry para ponerse al día liquidación por liquidación.
    """

    def __init__(self, symbols: Sequence[str], params: CarryParams, strategy_id: str) -> None:
        if not symbols:
            raise ValueError("La estrategia necesita al menos un símbolo")
        self.symbols = tuple(symbols)
        self.params = params
        self.strategy_id = strategy_id
        self._open: dict[str, bool] = {}
        self._last: dict[str, datetime] = {}

    # --- puerto Strategy -------------------------------------------------------------------

    @property
    def instruments(self) -> tuple[InstrumentId, ...]:
        return tuple(i for s in self.symbols for i in (spot_instrument(s), perp_instrument(s)))

    @property
    def lookback(self) -> timedelta:
        """k liquidaciones con el intervalo más largo (8 h); con intervalos cortos entran más."""
        return timedelta(hours=MAX_INTERVAL_HOURS * self.params.k)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        """Peso objetivo por pata: ±1/(2n) dentro y 0 fuera (1x, enmienda 2).

        La histéresis avanza con cada liquidación nueva de la instantánea, en orden. Sin ninguna
        liquidación todavía, el símbolo queda fuera.
        """
        weight = Decimal(1) / (2 * len(self.symbols))
        signals = []
        for symbol in self.symbols:
            history = snapshot.funding.get(perp_instrument(symbol), ())
            if history:
                decisions = self.walk(
                    history, since=self._last.get(symbol), is_open=self._open.get(symbol, False)
                )
                for d in decisions:
                    if d.action is CarryAction.ENTRAR:
                        self._open[symbol] = True
                    elif d.action is CarryAction.SALIR:
                        self._open[symbol] = False
                    self._last[symbol] = d.funding_time
            w = weight if self._open.get(symbol, False) else Decimal(0)
            for instrument, target in ((spot_instrument(symbol), w), (perp_instrument(symbol), -w)):
                signals.append(
                    Signal(
                        strategy_id=self.strategy_id,
                        instrument=instrument,
                        generated_at=snapshot.as_of,
                        target_weight=target,
                    )
                )
        return signals

    # --- uso directo del runner ------------------------------------------------------------

    def evaluate(self, history: Sequence[FundingRate], *, is_open: bool) -> CarryDecision:
        """Decisión en la última liquidación de ``history`` (ordenada de antigua a reciente)."""
        if not history:
            raise ValueError("Sin liquidaciones no hay decisión")
        last = history[-1]
        annualized = [annualize(float(r.rate), r.interval_hours) for r in history]
        s_k = signal(annualized, self.params.k)
        action = decide(is_open=is_open, s_k=s_k, last_rate=float(last.rate), params=self.params)
        return CarryDecision(
            symbol_of(last.instrument), last.funding_time, action, s_k, float(last.rate)
        )

    def walk(
        self, history: Sequence[FundingRate], *, since: datetime | None, is_open: bool
    ) -> list[CarryDecision]:
        """Decisiones en cada liquidación posterior a ``since`` (todas si es ``None``).

        El estado (abierto o cerrado) avanza con cada decisión, como en el backtest. Sirve para
        ponerse al día tras una caída y, con ``since=None``, para el arranque en frío: el estado
        de la histéresis se reconstruye con el historial en lugar de suponer «cerrado».
        """
        ordered = sorted(history, key=lambda r: r.funding_time)
        decisions = []
        for i, rate in enumerate(ordered):
            if since is not None and rate.funding_time <= since:
                continue
            decision = self.evaluate(ordered[: i + 1], is_open=is_open)
            if decision.action is CarryAction.ENTRAR:
                is_open = True
            elif decision.action is CarryAction.SALIR:
                is_open = False
            decisions.append(decision)
        return decisions
