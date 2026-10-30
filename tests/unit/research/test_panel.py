from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from prometheus_platform.research.panel import (
    DEV_END,
    development_only,
    hourly_prices,
    settlement_features,
)

T0 = datetime(2024, 6, 25, tzinfo=UTC)


def legs(hours: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    times = [T0 + timedelta(hours=i) for i in range(hours)]
    schema: dict[str, pl.DataType] = {
        "open_time": pl.Datetime("ms", "UTC"),
        "open": pl.Float64(),
        "close": pl.Float64(),
    }
    spot = pl.DataFrame(
        {
            "open_time": times,
            "open": [100.0 + i for i in range(hours)],
            "close": [101.0 + i for i in range(hours)],
        },
        schema=schema,
    )
    perp = spot.with_columns(pl.col("close") * 1.001, pl.col("open") * 1.001)
    return spot, perp


def funding(n: int) -> pl.DataFrame:
    times = [T0 + timedelta(hours=8 * (i + 1)) for i in range(n)]
    return pl.DataFrame(
        {
            "funding_time": times,
            "knowledge_time": times,
            "funding_interval_hours": [8] * n,
            "funding_rate": [0.0001 * (i + 1) for i in range(n)],
            "funding_rate_annualized": [0.1095 * (i + 1) for i in range(n)],
        }
    ).with_columns(
        pl.col("funding_time", "knowledge_time").dt.cast_time_unit("ms").dt.replace_time_zone("UTC")
    )


def test_hourly_prices_keep_missing_hours_null() -> None:
    spot, perp = legs(5)
    hourly = hourly_prices(spot.filter(pl.col("open") != 102.0), perp)
    assert hourly.height == 5
    assert hourly["spot_close"].null_count() == 1


def test_features_only_use_bars_closed_at_or_before_the_settlement() -> None:
    spot, perp = legs(24 * 3)
    panel = settlement_features(funding(8), hourly_prices(spot, perp))
    first = panel.row(0, named=True)
    # La liquidación de las 08:00 usa la vela 07:00-08:00 (close = 101 + 7), no la de las 08:00.
    assert first["spot_close"] == 108.0
    assert first["basis"] == pytest.approx(0.001)
    assert panel["s_3"][2] == pytest.approx(0.1095 * 2)
    assert panel["annualized_lag1"][1] == pytest.approx(0.1095)
    assert panel["target_next_annualized"][0] == pytest.approx(0.1095 * 2)


def test_development_only_never_leaks_a_holdout_rate_into_the_target() -> None:
    spot, perp = legs(24 * 10)
    panel = development_only(settlement_features(funding(25), hourly_prices(spot, perp)))
    assert panel["funding_time"].max() <= DEV_END  # type: ignore[operator]
    assert panel["target_next_annualized"][-1] is None  # la siguiente cae en el holdout
