"""Contrato de estrategia (PQ-113, ADR-0011): cada estrategia del runner debe pasarlo.

**Para añadir una estrategia:** agrega a ``STRATEGIES`` su nombre, una fábrica (instancia nueva
cada vez) y una historia sintética que la ejercite: que entre y salga, con huecos y cambios de
intervalo si le afectan.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.contract.strategy_contract import History, check_strategy_contract

from prometheus_platform.domain.market import MarketSnapshot, snapshot_at
from prometheus_platform.domain.model import DomainError, FundingRate, InstrumentId, Signal
from prometheus_platform.domain.ports import Strategy
from prometheus_platform.strategies.carry import H2_PARAMS, CarryStrategy, perp_instrument

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def funding_history(symbols: tuple[str, ...], n: int = 240) -> History:
    """Tasas que cruzan θ, θ/2 y cero; un tramo con intervalo de 4 h (como XRP en episodios)."""
    funding = {}
    for offset, symbol in enumerate(symbols):
        rows, at = [], T0
        for i in range(n):
            interval = 4 if 100 <= i < 140 else 8
            rate = 0.00005 + 0.0003 * math.sin((i + 13 * offset) / 15)
            rows.append(
                FundingRate(
                    instrument=perp_instrument(symbol),
                    funding_time=at,
                    rate=Decimal(repr(rate * interval / 8)),
                    interval_hours=interval,
                )
            )
            at += timedelta(hours=interval)
        funding[perp_instrument(symbol)] = rows
    return History(funding=funding)


H2 = ("SOLUSDT", "BNBUSDT", "XRPUSDT")
STRATEGIES: list[tuple[str, Callable[[], Strategy], History]] = [
    ("carry-h2", lambda: CarryStrategy(H2, H2_PARAMS, "carry-h2"), funding_history(H2)),
    (
        "carry-k3",
        lambda: CarryStrategy(("SOLUSDT",), H2_PARAMS.__class__(3, 0.10), "carry-k3"),
        funding_history(("SOLUSDT",)),
    ),
]


@pytest.mark.parametrize(("name", "factory", "history"), STRATEGIES, ids=[s[0] for s in STRATEGIES])
def test_every_strategy_honours_the_contract(
    name: str, factory: Callable[[], Strategy], history: History
) -> None:
    signals = check_strategy_contract(factory, history)
    weights = {s.target_weight for batch in signals for s in batch}
    assert len(weights) > 1, f"{name}: la historia de prueba no la hace entrar ni salir"


# --- el contrato detecta a las estrategias que lo incumplen ---------------------------------

SOL = perp_instrument("SOLUSDT")


class LeakyMean:
    """Declara 8 h de historia, pero promedia todo lo que ve: en paper decide distinto."""

    strategy_id = "fuga"
    instruments = (SOL,)
    lookback = timedelta(hours=8)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        rows = snapshot.funding.get(SOL, ())
        mean = sum((r.rate for r in rows), Decimal(0)) / max(len(rows), 1)
        weight = Decimal(-1) if mean > Decimal("0.00005") else Decimal(0)
        return [Signal("fuga", SOL, snapshot.as_of, weight)]


class Flaky:
    """Usa azar sin semilla: dos instancias nuevas no coinciden."""

    strategy_id = "azar"
    instruments = (SOL,)
    lookback = timedelta(hours=8)

    def __init__(self) -> None:
        self._rng = random.Random()  # noqa: S311 - es justo el defecto que el contrato detecta

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        weight = Decimal(int(self._rng.random() > 0.5))
        return [Signal("azar", SOL, snapshot.as_of, weight)]


class WrongTime:
    strategy_id = "reloj"
    instruments = (SOL,)
    lookback = timedelta(hours=8)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        return [Signal("reloj", SOL, snapshot.as_of + timedelta(seconds=1), Decimal(0))]


@pytest.mark.parametrize(
    ("strategy", "message"),
    [(LeakyMean, "paridad"), (Flaky, "determinismo"), (WrongTime, "generated_at")],
)
def test_the_contract_catches_bad_strategies(
    strategy: Callable[[], Strategy], message: str
) -> None:
    with pytest.raises(AssertionError, match=message):
        check_strategy_contract(strategy, funding_history(("SOLUSDT",), n=60))


# --- la instantánea es point-in-time --------------------------------------------------------


def rate(at: datetime) -> FundingRate:
    return FundingRate(instrument=SOL, funding_time=at, rate=Decimal("0.0001"))


def test_snapshot_rejects_data_from_the_future() -> None:
    with pytest.raises(DomainError, match="futuro"):
        MarketSnapshot(as_of=T0, funding={SOL: [rate(T0 + timedelta(hours=8))]})


def test_snapshot_rejects_unsorted_series_and_naive_times() -> None:
    with pytest.raises(DomainError, match="antigua"):
        MarketSnapshot(
            as_of=T0 + timedelta(days=1), funding={SOL: [rate(T0 + timedelta(hours=8)), rate(T0)]}
        )
    with pytest.raises(DomainError, match="UTC"):
        MarketSnapshot(as_of=datetime(2026, 1, 1))  # noqa: DTZ001 - el error es justo ese


def test_snapshot_at_cuts_at_as_of_and_at_the_lookback() -> None:
    rows = [rate(T0 + timedelta(hours=8 * i)) for i in range(10)]
    snap = snapshot_at(T0 + timedelta(hours=40), funding={SOL: rows}, lookback=timedelta(hours=16))
    assert [r.funding_time for r in snap.funding[SOL]] == [
        T0 + timedelta(hours=h) for h in (24, 32, 40)
    ]


def test_carry_declares_both_legs_and_its_lookback() -> None:
    strategy = CarryStrategy(("SOLUSDT",), H2_PARAMS, "carry-h2")
    assert [i.symbol for i in strategy.instruments] == ["SOLUSDT", "SOLUSDT-PERP"]
    assert strategy.lookback == timedelta(hours=8 * H2_PARAMS.k)
    assert InstrumentId("SOLUSDT-PERP", SOL.venue) in strategy.instruments
