from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from prometheus_platform.domain.model import (
    Bar,
    DomainError,
    FundingRate,
    InstrumentId,
    Signal,
    Venue,
)

BTC = InstrumentId("BTCUSDT", Venue.BINANCE)
T0 = datetime(2026, 1, 1, tzinfo=UTC)
prices = st.decimals(min_value=Decimal("0.01"), max_value=Decimal(10**6), places=2)


def make_bar(**overrides: object) -> Bar:
    fields: dict[str, object] = {
        "instrument": BTC,
        "open_time": T0,
        "close_time": T0 + timedelta(hours=1),
        "open": Decimal(100),
        "high": Decimal(110),
        "low": Decimal(90),
        "close": Decimal(105),
        "volume": Decimal(5),
    }
    fields.update(overrides)
    return Bar(**fields)  # type: ignore[arg-type]


def test_instrument_id_string_form() -> None:
    assert str(BTC) == "BTCUSDT.BINANCE"


def test_bar_is_known_only_at_close() -> None:
    bar = make_bar()
    assert bar.knowledge_time == bar.close_time


@given(a=prices, b=prices, c=prices, d=prices)
def test_bar_accepts_any_consistent_ohlc(a: Decimal, b: Decimal, c: Decimal, d: Decimal) -> None:
    open_, close = a, b
    high = max(a, b, c, d)
    low = min(a, b, c, d)
    bar = make_bar(open=open_, high=high, low=low, close=close)
    assert bar.low <= bar.high


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": Decimal(95)},  # high por debajo del cierre
        {"low": Decimal(101)},  # low por encima de la apertura
        {"open": Decimal(0)},
        {"volume": Decimal(-1)},
        {"close_time": T0},
        {"open_time": datetime(2026, 1, 1)},  # noqa: DTZ001 - sin zona horaria a propósito
        {"open_time": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-4)))},
    ],
)
def test_bar_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(DomainError):
        make_bar(**overrides)


def test_funding_rate_knowledge_time() -> None:
    fr = FundingRate(BTC, T0, Decimal("0.0001"))
    assert fr.knowledge_time == T0


@pytest.mark.parametrize("weight", [Decimal("1.01"), Decimal("-1.5")])
def test_signal_weight_is_bounded(weight: Decimal) -> None:
    with pytest.raises(DomainError):
        Signal("carry", BTC, T0, weight)


def test_signal_requires_strategy_id() -> None:
    with pytest.raises(DomainError):
        Signal("", BTC, T0, Decimal("0.5"))


def test_instrument_rejects_blank_symbol() -> None:
    with pytest.raises(DomainError):
        InstrumentId(" ", Venue.BINANCE)
