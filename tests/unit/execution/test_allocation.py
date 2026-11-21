"""Reglas puras del ejecutor genérico de señales (PQ-116)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.contract.example_strategies import BTC, SmaTrend

from prometheus_platform.domain.model import Signal
from prometheus_platform.execution.allocation import (
    StrategyAllocation,
    decision_time,
    effective_weight,
    outside_band,
    target_quantity,
    validate_allocations,
)

T0 = datetime(2026, 11, 1, tzinfo=UTC)
D = Decimal
HOUR = timedelta(hours=1)


def signal(hours: int, weight: str) -> Signal:
    return Signal("sma-ejemplo", BTC, T0 + timedelta(hours=hours), D(weight))


def test_decision_time_is_the_last_published_hourly_close() -> None:
    delay = timedelta(minutes=2)
    assert decision_time(T0 + timedelta(minutes=1), delay) == T0 - HOUR
    assert decision_time(T0 + timedelta(minutes=2), delay) == T0
    assert decision_time(T0 + timedelta(minutes=59), delay) == T0


def test_effective_weight_honours_the_latency_and_the_latest_signal_wins() -> None:
    history = [signal(0, "1"), signal(1, "0.5"), signal(2, "0")]
    # La pendiente es la última: cada señal nueva sustituye a la que aún no regía.
    assert effective_weight(history, T0 + timedelta(minutes=30), HOUR) == (None, history[2])
    assert effective_weight(history, T0 + 2 * HOUR, HOUR) == (history[1], history[2])
    assert effective_weight(history, T0 + 3 * HOUR, HOUR) == (history[2], None)
    assert effective_weight([], T0, HOUR) == (None, None)


def test_target_quantity_is_signed_and_capped() -> None:
    assert target_quantity(D(1), D(500), D(100), D(10_000)) == D(5)
    assert target_quantity(D(-1), D(500), D(100), D(10_000)) == D(-5)
    assert target_quantity(D("0.5"), D(500), D(100), D(100)) == D(1)  # tope de nocional
    assert target_quantity(D(0), D(500), D(100), D(100)) == 0
    assert target_quantity(D(1), D(0), D(100), D(100)) == 0
    with pytest.raises(ValueError, match="Precio"):
        target_quantity(D(1), D(500), D(0), D(100))


def test_band_is_a_fraction_of_the_allocated_capital() -> None:
    assert not outside_band(D(5), D(5), D(100), D(500), D("0.1"))
    assert not outside_band(D("4.5"), D(5), D(100), D(500), D("0.1"))  # 10 % exacto: no
    assert outside_band(D("4.4"), D(5), D(100), D(500), D("0.1"))
    assert outside_band(D(1), D(0), D(100), D(0), D("0.1"))  # sin capital, todo sobra


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"capital_share": D(0)}, "capital_share"),
        ({"capital_share": D("1.1")}, "capital_share"),
        ({"capital_share": D("NaN")}, "capital_share"),
        ({"capital_share": D("0.5"), "rebalance_band": D(1)}, "rebalance_band"),
        ({"capital_share": D("0.5"), "execution_delay": -HOUR}, "execution_delay"),
    ],
)
def test_allocation_rejects_bad_parameters(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        StrategyAllocation(SmaTrend(), **kwargs)  # type: ignore[arg-type]


def test_allocation_rejects_strategies_without_instruments_or_lookback() -> None:
    class Empty(SmaTrend):
        @property
        def instruments(self) -> tuple[()]:
            return ()

    with pytest.raises(ValueError, match="instrumentos"):
        StrategyAllocation(Empty(), D("0.5"))
    with pytest.raises(ValueError, match="lookback"):
        StrategyAllocation(SmaTrend(hours=0), D("0.5"))


def test_validate_allocations_sums_the_shares() -> None:
    eth = SmaTrend(BTC.__class__("ETHUSDT", BTC.venue), strategy_id="eth")
    allocations = [StrategyAllocation(SmaTrend(), D("0.3")), StrategyAllocation(eth, D("0.2"))]
    assert validate_allocations(allocations) == D("0.5")
    with pytest.raises(ValueError, match="suman"):
        validate_allocations(
            [
                *allocations,
                StrategyAllocation(
                    SmaTrend(strategy_id="x", instrument=BTC.__class__("XRPUSDT", BTC.venue)),
                    D("0.6"),
                ),
            ]
        )
