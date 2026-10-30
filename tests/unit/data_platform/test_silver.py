from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from prometheus_platform.data_platform.silver import (
    SilverValidationError,
    asof_join,
    build_funding,
    build_klines,
    interval_ms,
    to_epoch_ms,
)
from prometheus_platform.domain.datasets import Market

H = 3_600_000
T0 = 1_733_011_200_000  # 2024-12-01 00:00 UTC en ms


def kline_bronze(open_times: list[int], *, unit: int = 1, closes: list[float] | None = None,
                 highs: list[float] | None = None) -> pl.DataFrame:  # fmt: skip
    """Bronze de velas como lo deja PQ-20: todo texto, con linaje."""
    n = len(open_times)
    closes = closes or [100.0 + i for i in range(n)]
    highs = highs or [c + 5 for c in closes]
    return pl.DataFrame(
        {
            "open_time": [str(t * unit) for t in open_times],
            "open": [str(c - 1) for c in closes],
            "high": [str(h) for h in highs],
            "low": [str(c - 3) for c in closes],
            "close": [str(c) for c in closes],
            "volume": ["10"] * n,
            "close_time": [str((t + H - 1) * unit) for t in open_times],
            "quote_volume": ["1000"] * n,
            "count": ["42"] * n,
            "taker_buy_volume": ["5"] * n,
            "taker_buy_quote_volume": ["500"] * n,
            "ignore": ["0"] * n,
            "_source_file": ["f.zip"] * n,
        }
    )


def funding_bronze(rows: list[tuple[int, int, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "calc_time": [str(t) for t, _, _ in rows],
            "funding_interval_hours": [str(i) for _, i, _ in rows],
            "last_funding_rate": [r for _, _, r in rows],
            "_source_file": ["f.zip"] * len(rows),
        }
    )


def test_interval_parsing() -> None:
    assert interval_ms("1h") == H
    assert interval_ms("1d") == 24 * H
    with pytest.raises(ValueError, match="no soportado"):
        interval_ms("1M")


def test_microseconds_and_milliseconds_end_up_on_the_same_scale() -> None:
    # Hallazgo 1: spot en µs desde 2025-01.
    frame = pl.DataFrame({"t": ["1735689600000000", "1733011200000"]})
    assert frame.select(to_epoch_ms("t"))["t"].to_list() == [1735689600000, 1733011200000]


def test_klines_are_typed_utc_and_known_at_close() -> None:
    ms = kline_bronze([T0, T0 + H])
    us = kline_bronze([T0 + 2 * H], unit=1000)  # mismo símbolo, ya en µs
    frame, report = build_klines(pl.concat([ms, us]), Market.SPOT, "BTCUSDT", "1h")

    assert frame["open_time"].dtype == pl.Datetime("ms", "UTC")
    assert frame["open_time"].to_list() == [datetime(2024, 12, 1, h, tzinfo=UTC) for h in range(3)]
    assert (frame["knowledge_time"] - frame["event_time"]).to_list() == [timedelta(hours=1)] * 3
    assert frame["trades"].dtype == pl.Int64
    assert report.rows == 3
    assert report.gaps == 0
    assert "esquema KlineSchema" in report.checks
    assert report.describe["close"]["n"] == 3


def test_gaps_are_reported_and_not_filled() -> None:
    frame, report = build_klines(kline_bronze([T0, T0 + H, T0 + 4 * H]), Market.USDM, "X1", "1h")
    assert frame.height == 3  # no se imputa nada
    assert report.gaps == 1
    assert report.missing_periods == 2
    assert report.largest_gap_hours == 3.0
    assert report.gap_list[0]["from"].startswith("2024-12-01 01:00")


def test_identical_duplicates_are_dropped_and_counted() -> None:
    bronze = kline_bronze([T0, T0 + H])
    frame, report = build_klines(pl.concat([bronze, bronze]), Market.USDM, "BTCUSDT", "1h")
    assert frame.height == 2
    assert report.duplicates_removed == 2


def test_conflicting_duplicates_fail() -> None:
    a = kline_bronze([T0], closes=[100.0])
    b = kline_bronze([T0], closes=[200.0])
    with pytest.raises(SilverValidationError, match="duplicados en conflicto"):
        build_klines(pl.concat([a, b]), Market.USDM, "BTCUSDT", "1h")


@pytest.mark.parametrize(
    ("bronze", "check"),
    [
        (kline_bronze([T0], highs=[50.0]), "OHLC coherente"),
        (kline_bronze([T0 + 1]), "alineados"),
        (kline_bronze([T0], closes=[0.5]), "esquema"),  # low = close - 3 < 0
    ],
)
def test_impossible_candles_fail_with_the_check_name(bronze: pl.DataFrame, check: str) -> None:
    with pytest.raises(SilverValidationError, match=check):
        build_klines(bronze, Market.SPOT, "BTCUSDT", "1h")


def test_empty_bronze_is_a_clear_error() -> None:
    with pytest.raises(SilverValidationError, match="no tiene filas"):
        build_klines(pl.DataFrame(), Market.SPOT, "BTCUSDT", "1h")
    with pytest.raises(SilverValidationError, match="no tiene filas"):
        build_funding(pl.DataFrame(), "BTCUSDT")


def test_outliers_are_flagged_not_removed() -> None:
    n = 400
    closes = [100.0 * (1.001 if i % 2 else 0.999) for i in range(n)]
    closes[-1] = 160.0  # salto de +60 % en una hora
    highs = [c + 5 for c in closes]
    bronze = kline_bronze([T0 + i * H for i in range(n)], closes=closes, highs=highs)
    frame, report = build_klines(bronze, Market.USDM, "BTCUSDT", "1h")
    assert frame.height == n
    assert report.outliers == 1
    assert frame["is_outlier"][-1]


def test_funding_is_annualized_with_its_own_interval_and_rounded_to_the_hour() -> None:
    rows = [
        (T0 + 2, 8, "0.00010000"),  # jitter de 2 ms (hallazgo 3)
        (T0 + 8 * H, 2, "0.00010000"),  # intervalo de 2 h como SOL en nov-2022
        (T0 + 10 * H, 2, "-0.00020000"),
    ]
    frame, report = build_funding(funding_bronze(rows), "SOLUSDT")
    assert frame["funding_time"][0] == datetime(2024, 12, 1, tzinfo=UTC)
    assert frame["calc_time"][0] == datetime(2024, 12, 1, 0, 0, 0, 2000, tzinfo=UTC)
    assert frame["funding_rate_annualized"].to_list() == pytest.approx([0.1095, 0.438, -0.876])
    assert (frame["knowledge_time"] == frame["funding_time"]).all()
    assert report.gaps == 0


def test_funding_gap_uses_the_previous_interval() -> None:
    rows = [(T0, 8, "0.0001"), (T0 + 8 * H, 8, "0.0001"), (T0 + 24 * H, 8, "0.0001")]
    _, report = build_funding(funding_bronze(rows), "BTCUSDT")
    assert report.gaps == 1
    assert report.missing_periods == 1


@pytest.mark.parametrize(("interval", "rate"), [(3, "0.0001"), (8, "0.2")])
def test_invalid_funding_fails_schema(interval: int, rate: str) -> None:
    with pytest.raises(SilverValidationError, match="FundingSchema"):
        build_funding(funding_bronze([(T0, interval, rate)]), "BTCUSDT")


def test_asof_join_never_uses_data_known_later() -> None:
    funding, _ = build_funding(
        funding_bronze([(T0, 8, "0.0001"), (T0 + 8 * H, 8, "0.0003")]), "BTCUSDT"
    )
    t = [datetime(2024, 12, 1, h, tzinfo=UTC) for h in (0, 7, 8, 9)]
    left = pl.DataFrame({"t": t}).with_columns(pl.col("t").dt.cast_time_unit("ms"))
    joined = asof_join(left, funding.select("knowledge_time", "funding_rate"), on="t")
    # A las 07:00 la liquidación de las 08:00 todavía no existe.
    assert joined["funding_rate"].to_list() == pytest.approx([0.0001, 0.0001, 0.0003, 0.0003])
