"""Estrategia del carry de funding para el paper trading (PQ-54).

Decide con ``domain/carry_rules.decide``, la misma función que usa el backtest. Solo traduce las
liquidaciones recientes en una acción y en el objetivo de cada pata. No conoce la ejecución ni el
riesgo: eso lo hacen el runner, ``portfolio_risk`` y el bróker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from prometheus_platform.domain.carry_rules import (
    CarryAction,
    CarryParams,
    annualize,
    decide,
    signal,
)
from prometheus_platform.domain.model import FundingRate, InstrumentId, Venue

PERP_SUFFIX = "-PERP"
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
    """Carry delta-neutral: spot largo y perpetuo corto. H2 usa ``H2_PARAMS``."""

    def __init__(self, symbols: Sequence[str], params: CarryParams, strategy_id: str) -> None:
        if not symbols:
            raise ValueError("La estrategia necesita al menos un símbolo")
        self.symbols = tuple(symbols)
        self.params = params
        self.strategy_id = strategy_id

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
