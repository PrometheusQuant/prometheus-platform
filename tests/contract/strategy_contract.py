"""Prueba de contrato reutilizable para estrategias (PQ-113, ADR-0011).

Toda estrategia nueva que vaya a conectarse al runner debe pasar ``check_strategy_contract``.
Se añade a la lista ``STRATEGIES`` de ``tests/unit/strategies/test_strategy_contract.py``.

Qué comprueba:

1. **Señales válidas:** su ``strategy_id``, ``generated_at`` igual al ``as_of`` de la instantánea,
   solo instrumentos declarados y como mucho una señal por instrumento.
2. **Determinismo:** dos instancias nuevas con las mismas instantáneas dan las mismas señales.
3. **Paridad backtest ↔ paper:** la misma estrategia se alimenta de dos formas.
   - Backtest: en cada instante ve **todo** el pasado.
   - Paper: los datos llegan cuando se conocen y solo conserva la ventana ``lookback``, como el
     runner en vivo.

   Si las señales difieren, la estrategia usa más historia de la que declara o depende de algo que
   no está en la instantánea.

El sesgo de anticipación lo impide ``MarketSnapshot``, que rechaza cualquier dato posterior a su
``as_of``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from prometheus_platform.domain.market import MarketSnapshot, snapshot_at
from prometheus_platform.domain.model import Bar, FundingRate, InstrumentId, Signal
from prometheus_platform.domain.ports import Strategy


@dataclass(frozen=True)
class History:
    """Historia completa de mercado con la que se ejercita la estrategia."""

    bars: dict[InstrumentId, list[Bar]] = field(default_factory=dict)
    funding: dict[InstrumentId, list[FundingRate]] = field(default_factory=dict)

    def knowledge_times(self) -> list[datetime]:
        times = {r.knowledge_time for rows in self.bars.values() for r in rows}
        times |= {r.knowledge_time for rates in self.funding.values() for r in rates}
        return sorted(times)


def backtest_drive(
    strategy: Strategy, history: History, times: Sequence[datetime]
) -> list[list[Signal]]:
    return [
        strategy.on_snapshot(snapshot_at(t, bars=history.bars, funding=history.funding))
        for t in times
    ]


def paper_drive(
    strategy: Strategy, history: History, times: Sequence[datetime]
) -> list[list[Signal]]:
    """Como el runner: los datos llegan al conocerse y solo se guarda la ventana ``lookback``."""
    arrivals: list[tuple[datetime, str, InstrumentId, Bar | FundingRate]] = sorted(
        [(r.knowledge_time, "bar", i, r) for i, rows in history.bars.items() for r in rows]
        + [
            (r.knowledge_time, "funding", i, r) for i, rows in history.funding.items() for r in rows
        ],
        key=lambda item: item[0],
    )
    bars: dict[InstrumentId, list[Bar]] = {i: [] for i in history.bars}
    funding: dict[InstrumentId, list[FundingRate]] = {i: [] for i in history.funding}
    out, cursor = [], 0
    for t in times:
        while cursor < len(arrivals) and arrivals[cursor][0] <= t:
            _, kind, instrument, row = arrivals[cursor]
            if kind == "bar" and isinstance(row, Bar):
                bars[instrument].append(row)
            elif isinstance(row, FundingRate):
                funding[instrument].append(row)
            cursor += 1
        start = t - strategy.lookback
        for instrument, rows in bars.items():
            bars[instrument] = [r for r in rows if r.knowledge_time >= start]
        for instrument, rates in funding.items():
            funding[instrument] = [r for r in rates if r.knowledge_time >= start]
        snapshot = MarketSnapshot(
            as_of=t,
            bars={i: list(rows) for i, rows in bars.items()},
            funding={i: list(rows) for i, rows in funding.items()},
        )
        out.append(strategy.on_snapshot(snapshot))
    return out


def _validate(strategy: Strategy, t: datetime, signals: Sequence[Signal]) -> None:
    declared = set(strategy.instruments)
    seen: set[InstrumentId] = set()
    for s in signals:
        assert s.strategy_id == strategy.strategy_id, f"{t}: strategy_id {s.strategy_id!r}"
        assert s.generated_at == t, f"{t}: generated_at {s.generated_at} distinto del as_of"
        assert s.instrument in declared, f"{t}: {s.instrument} no está en instruments"
        assert s.instrument not in seen, f"{t}: dos señales para {s.instrument}"
        seen.add(s.instrument)


def check_strategy_contract(
    factory: Callable[[], Strategy], history: History, times: Sequence[datetime] | None = None
) -> list[list[Signal]]:
    """Falla con ``AssertionError`` si la estrategia incumple el contrato; devuelve sus señales."""
    times = list(times or history.knowledge_times())
    assert times, "La historia de prueba está vacía"
    first = backtest_drive(factory(), history, times)
    for t, signals in zip(times, first, strict=True):
        _validate(factory(), t, signals)
    second = backtest_drive(factory(), history, times)
    assert first == second, "determinismo: dos instancias nuevas dieron señales distintas"
    paper = paper_drive(factory(), history, times)
    for t, backtest_signals, paper_signals in zip(times, first, paper, strict=True):
        assert backtest_signals == paper_signals, (
            f"paridad backtest ↔ paper rota en {t.isoformat()}: con la ventana lookback la "
            "estrategia decide distinto que con todo el pasado"
        )
    return first
