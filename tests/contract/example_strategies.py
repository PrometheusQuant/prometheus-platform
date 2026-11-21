"""Estrategias de ejemplo para la prueba de contrato y el ejecutor genérico (PQ-116).

``SmaTrend`` es la estrategia más simple de una sola pata: va larga si el último cierre supera la
media de las últimas ``hours`` velas, y se sale si no. No es una hipótesis de investigación: solo
demuestra que cualquier ``Strategy`` que pase el contrato opera en el runner sin tocarlo.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from prometheus_platform.domain.market import MarketSnapshot
from prometheus_platform.domain.model import Bar, InstrumentId, Signal, Venue

BTC = InstrumentId("BTCUSDT", Venue.BINANCE)
ONE, ZERO = Decimal(1), Decimal(0)


class SmaTrend:
    def __init__(
        self, instrument: InstrumentId = BTC, hours: int = 4, strategy_id: str = "sma-ejemplo"
    ) -> None:
        self.strategy_id = strategy_id
        self._instrument = instrument
        self._hours = hours

    @property
    def instruments(self) -> tuple[InstrumentId, ...]:
        return (self._instrument,)

    @property
    def lookback(self) -> timedelta:
        return timedelta(hours=self._hours)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        closes = [b.close for b in snapshot.bars.get(self._instrument, ())][-self._hours :]
        if len(closes) < self._hours:
            return []  # sin la ventana completa no decide
        mean = sum(closes, ZERO) / len(closes)
        weight = ONE if closes[-1] > mean else ZERO
        return [Signal(self.strategy_id, self._instrument, snapshot.as_of, weight)]


def hourly_bars(instrument: InstrumentId, start: datetime, closes: Sequence[Decimal]) -> list[Bar]:
    """Una vela de 1 h por cierre, desde ``start``; cada una abre en el cierre anterior."""
    bars, previous = [], closes[0]
    for i, close in enumerate(closes):
        opened = start + timedelta(hours=i)
        bars.append(
            Bar(
                instrument=instrument,
                open_time=opened,
                close_time=opened + timedelta(hours=1),
                open=previous,
                high=max(previous, close),
                low=min(previous, close),
                close=close,
                volume=Decimal(1),
            )
        )
        previous = close
    return bars
