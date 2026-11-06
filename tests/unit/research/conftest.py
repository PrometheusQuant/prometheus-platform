from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from prometheus_platform.research.panel import SIGNAL_WINDOWS

T0 = datetime(2023, 1, 1, tzinfo=UTC)
HourlyFactory = Callable[..., tuple[pl.DataFrame, pl.DataFrame]]


def make_market(
    hours: int,
    *,
    price: Callable[[int], float] = lambda _: 100.0,
    rate: Callable[[int], float] = lambda _: 0.0001,
    missing_spot: frozenset[int] = frozenset(),
    start: datetime = T0,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Precios horarios (spot = perp) y liquidaciones cada 8 h con las medias S_k."""
    times = [start + timedelta(hours=i) for i in range(hours)]
    spot = [None if i in missing_spot else price(i) for i in range(hours)]
    hourly = pl.DataFrame(
        {
            "open_time": times,
            "spot_open": spot,
            "spot_close": [None if i in missing_spot else price(i + 1) for i in range(hours)],
            "perp_open": [price(i) for i in range(hours)],
            "perp_close": [price(i + 1) for i in range(hours)],
        },
        schema_overrides={"open_time": pl.Datetime("ms", "UTC")},
    )
    settle_hours = list(range(8, hours + 1, 8))
    settlements = pl.DataFrame(
        {
            "funding_time": [start + timedelta(hours=h) for h in settle_hours],
            "funding_rate": [rate(h) for h in settle_hours],
        },
        schema_overrides={"funding_time": pl.Datetime("ms", "UTC")},
    ).with_columns((pl.col("funding_rate") * 8760 / 8).alias("annualized"))
    settlements = settlements.with_columns(
        [pl.col("annualized").rolling_mean(window_size=k).alias(f"s_{k}") for k in SIGNAL_WINDOWS]
    )
    return hourly, settlements


@pytest.fixture
def market() -> HourlyFactory:
    return make_market
