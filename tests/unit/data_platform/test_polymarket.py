"""Lakehouse de Polymarket (PQ-92): bronze con linaje y silver point-in-time."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from prometheus_platform.data_platform.polymarket import (
    MIN_MARKETS,
    bronze_path,
    build_markets,
    build_prices,
    build_silver,
    ingest_markets,
    ingest_prices,
    ingest_trades,
    is_sports,
    month_window,
    prices_asof,
    read_bronze,
    resolution_asof,
)
from prometheus_platform.data_platform.silver import SilverValidationError
from prometheus_platform.domain.prediction_markets import PredictionMarketError, RawPage

NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
DAY = 86_400
T0 = int(datetime(2024, 3, 1, tzinfo=UTC).timestamp())


class FixedClock:
    def now(self) -> datetime:
        return NOW


def market(  # noqa: PLR0913 - un mercado de Gamma con lo justo para cada caso
    mid: str,
    *,
    end: str = "2024-03-10T12:00:00Z",
    closed: str | None = "2024-03-11 08:00:00+00",
    prices: str = '["1", "0"]',
    tags: tuple[str, ...] = ("Politics",),
    fee_type: str | None = None,
    tokens: tuple[str, ...] = ("111", "222"),
) -> dict[str, Any]:
    return {
        "id": mid,
        "conditionId": f"0x{mid}",
        "question": f"¿Pasa {mid}?",
        "slug": f"pasa-{mid}",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": prices,
        "clobTokenIds": json.dumps(list(tokens)),
        "endDate": end,
        "closedTime": closed,
        "createdAt": "2024-02-01T00:00:00Z",
        "volumeNum": 1500.0,
        "negRisk": False,
        "feeType": fee_type,
        "umaResolutionStatus": "resolved",
        "tags": [{"label": t} for t in tags],
        "events": [{"id": 77}],
    }


class FakeSource:
    def __init__(
        self,
        markets: list[dict[str, Any]] | None = None,
        history: dict[str, list[dict[str, Any]]] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self.markets = markets or []
        self.history = history or {}
        self.fail = fail or set()
        self.calls: list[tuple[str, str]] = []

    def closed_markets(self, start: datetime, end: datetime, min_volume: float) -> list[RawPage]:
        self.calls.append(("markets", f"{start:%Y-%m}"))
        if "markets" in self.fail:
            raise PredictionMarketError("caído")
        rows = [m for m in self.markets if start <= datetime.fromisoformat(m["endDate"]) <= end]
        return [RawPage(f"https://gamma/markets?m={start:%Y-%m}", rows)]

    def price_history(
        self,
        token_id: str,
        fidelity_minutes: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RawPage]:
        self.calls.append(("prices", token_id))
        if token_id in self.fail:
            raise PredictionMarketError("caído")
        return [
            RawPage(
                f"https://clob/prices-history?market={token_id}", self.history.get(token_id, [])
            )
        ]

    def trades(self, condition_id: str, max_pages: int) -> list[RawPage]:
        self.calls.append(("trades", condition_id))
        return [
            RawPage(f"https://data/v2/trades?condition={condition_id}", [{"price": 0.9, "size": 5}])
        ]


def bronze_markets(
    *rows: dict[str, Any], fetched: str = "2026-11-24T00:00:00+00:00"
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id": [r["id"] for r in rows],
            "condition_id": [r["conditionId"] for r in rows],
            "raw": [json.dumps(r) for r in rows],
            "request": ["https://gamma/markets"] * len(rows),
            "fetched_at": [fetched] * len(rows),
        }
    )


def bronze_prices(points: list[tuple[str, str, int, float]]) -> pl.DataFrame:
    """``(token, condition, t en segundos, p)``."""
    return pl.DataFrame(
        {
            "token_id": [p[0] for p in points],
            "condition_id": [p[1] for p in points],
            "outcome_index": ["0"] * len(points),
            "t": [str(p[2]) for p in points],
            "p": [str(p[3]) for p in points],
            "request": ["https://clob"] * len(points),
            "fetched_at": ["x"] * len(points),
        }
    )


# --- Bronze -----------------------------------------------------------------------------------


def test_month_window_covers_the_month_without_touching_the_next() -> None:
    start, end = month_window(date(2024, 12, 1))
    assert start == datetime(2024, 12, 1, tzinfo=UTC)
    assert end == datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert month_window(date(2024, 2, 1))[1].day == 29


def test_markets_bronze_keeps_raw_json_request_and_fetch_time(tmp_path: Path) -> None:
    src = FakeSource([market("1"), market("2", end="2024-04-02T00:00:00Z")])
    report = ingest_markets(
        src, tmp_path, [date(2024, 3, 1), date(2024, 4, 1)], min_volume=1000, clock=FixedClock()
    )

    assert report.ok
    assert report.written == ["markets/2024-03", "markets/2024-04"]
    march = pl.read_parquet(bronze_path(tmp_path, "markets", date(2024, 3, 1)))
    assert march["id"].to_list() == ["1"]
    assert json.loads(march["raw"][0])["conditionId"] == "0x1"
    assert march["request"][0] == "https://gamma/markets?m=2024-03"
    assert march["fetched_at"][0] == NOW.isoformat()
    assert all(dtype == pl.String for dtype in march.dtypes)  # bronze: todo texto


def test_markets_bronze_is_idempotent_except_for_recent_months(tmp_path: Path) -> None:
    src = FakeSource([market("1")])
    months = [date(2024, 3, 1), date(2024, 4, 1)]
    ingest_markets(src, tmp_path, months, min_volume=0, clock=FixedClock())
    src.calls.clear()

    again = ingest_markets(
        src, tmp_path, months, min_volume=0, clock=FixedClock(), refresh_since=date(2024, 4, 1)
    )

    assert again.skipped == ["markets/2024-03"]
    assert again.written == ["markets/2024-04"]
    assert src.calls == [("markets", "2024-04")]


def test_a_failed_month_is_reported_and_not_written(tmp_path: Path) -> None:
    report = ingest_markets(
        FakeSource(fail={"markets"}), tmp_path, [date(2024, 3, 1)], min_volume=0, clock=FixedClock()
    )
    assert not report.ok
    assert report.failed == ["markets/2024-03"]
    assert not bronze_path(tmp_path, "markets", date(2024, 3, 1)).exists()


def test_prices_bronze_has_every_outcome_and_is_skipped_when_present(tmp_path: Path) -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    src = FakeSource(history={"111": [{"t": T0, "p": 0.7}], "222": [{"t": T0, "p": 0.3}]})

    report = ingest_prices(src, tmp_path, markets, clock=FixedClock())

    assert report.written == ["prices/1440/2024-03"]
    raw = read_bronze(tmp_path, "prices", 1440)
    assert sorted(zip(raw["token_id"], raw["outcome_index"], strict=True)) == [
        ("111", "0"),
        ("222", "1"),
    ]
    assert raw["request"][0].startswith("https://clob/prices-history")
    again = ingest_prices(src, tmp_path, markets, clock=FixedClock())
    assert again.skipped == ["prices/1440/2024-03"]


def test_a_month_with_a_failed_token_is_retried_later(tmp_path: Path) -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    report = ingest_prices(FakeSource(fail={"222"}), tmp_path, markets, clock=FixedClock())
    assert report.failed == ["prices/1440/2024-03"]
    assert not bronze_path(tmp_path, "prices", date(2024, 3, 1), 1440).exists()


def test_trades_bronze_keeps_each_trade_with_its_market(tmp_path: Path) -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    report = ingest_trades(FakeSource(), tmp_path, markets, clock=FixedClock(), max_pages=2)
    raw = read_bronze(tmp_path, "trades")
    assert report.written == ["trades/2024-03"]
    assert raw["condition_id"].to_list() == ["0x1"]
    assert json.loads(raw["raw"][0]) == {"price": 0.9, "size": 5}


def test_read_bronze_without_files_is_empty(tmp_path: Path) -> None:
    assert read_bronze(tmp_path, "markets").is_empty()


# --- Silver: mercados -------------------------------------------------------------------------


def test_markets_silver_types_dates_payouts_and_resolution_time() -> None:
    frame, report = build_markets(bronze_markets(market("1")))
    row = frame.row(0, named=True)
    assert row["end_date"] == datetime(2024, 3, 10, 12, tzinfo=UTC)
    assert row["closed_time"] == datetime(2024, 3, 11, 8, tzinfo=UTC)
    assert row["resolution_known_at"] == row["closed_time"]
    assert row["payouts"] == [1.0, 0.0]
    assert row["token_ids"] == ["111", "222"]
    assert row["event_id"] == "77"
    assert row["excluded_reason"] is None
    assert "pagos en [0, 1]" in report.checks


def test_partial_and_undefined_resolutions() -> None:
    """Se cobra el pago publicado tal cual; ["0","0"] y la falta de closedTime se marcan."""
    frame, report = build_markets(
        bronze_markets(
            market("half", prices='["0.5", "0.5"]'),
            market("amm", prices='["0.9999973981", "0.0000026019"]'),
            market("zero", prices='["0", "0"]'),
            market("open", closed=None),
        )
    )
    by_id = {r["market_id"]: r for r in frame.iter_rows(named=True)}
    assert by_id["half"]["payouts"] == [0.5, 0.5]
    assert by_id["half"]["excluded_reason"] is None
    assert by_id["amm"]["payouts"][0] == pytest.approx(0.9999973981)
    assert by_id["zero"]["excluded_reason"] == "pago sin definir (todos 0)"
    assert by_id["open"]["excluded_reason"] == "sin closedTime"
    assert by_id["open"]["resolution_known_at"] is None
    assert "utilizables (con pago y closedTime): 2" in report.checks


def test_the_latest_download_of_a_market_wins() -> None:
    old = bronze_markets(market("1", prices='["0", "0"]'), fetched="2026-01-01T00:00:00+00:00")
    new = bronze_markets(market("1"), fetched="2026-11-01T00:00:00+00:00")
    frame, report = build_markets(pl.concat([new, old]))
    assert frame.height == 1
    assert frame["payouts"][0].to_list() == [1.0, 0.0]
    assert report.duplicates_removed == 1


def test_payouts_outside_zero_one_fail() -> None:
    with pytest.raises(SilverValidationError, match=r"pagos en \[0, 1\]"):
        build_markets(bronze_markets(market("1", prices='["1.5", "0"]')))


def test_empty_bronze_fails() -> None:
    with pytest.raises(SilverValidationError, match="vacío"):
        build_markets(pl.DataFrame())


def test_quality_report_says_whether_there_are_enough_markets() -> None:
    _, few = build_markets(bronze_markets(market("1")))
    assert f"al menos {MIN_MARKETS} mercados: NO" in few.checks
    many = bronze_markets(*(market(str(i)) for i in range(MIN_MARKETS)))
    _, enough = build_markets(many)
    assert f"al menos {MIN_MARKETS} mercados: sí" in enough.checks


@pytest.mark.parametrize(
    ("tags", "fee_type", "expected"),
    [
        (["All", "Sports", "NBA"], None, True),
        (["sports"], None, True),
        (["Politics"], "sports_fees", True),
        (["Politics"], "politics_fees", False),
        ([], None, False),
    ],
)
def test_sports_rule_of_the_preregistration(
    tags: list[str], fee_type: str | None, expected: bool
) -> None:
    assert is_sports(tags, fee_type) is expected


def test_resolution_is_hidden_before_it_is_known() -> None:
    markets, _ = build_markets(bronze_markets(market("1"), market("open", closed=None)))
    before = resolution_asof(markets, datetime(2024, 3, 11, 7, 59, tzinfo=UTC))
    after = resolution_asof(markets, datetime(2024, 3, 11, 8, tzinfo=UTC))
    assert before["payouts"].to_list() == [None, None]
    assert after.filter(pl.col("market_id") == "1")["payouts"][0].to_list() == [1.0, 0.0]
    assert after.filter(pl.col("market_id") == "open")["resolved_asof"][0] is False


# --- Silver: precios --------------------------------------------------------------------------


def test_prices_have_knowledge_time_equal_to_the_point() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    prices, report = build_prices(bronze_prices([("111", "0x1", T0, 0.42)]), markets)
    row = prices.row(0, named=True)
    assert row["event_time"] == row["knowledge_time"] == datetime(2024, 3, 1, tzinfo=UTC)
    assert row["price"] == 0.42
    assert row["source_request"] == "https://clob"
    assert "precios en [0, 1]" in report.checks


def test_a_half_that_has_not_moved_for_24_hours_is_a_placeholder() -> None:
    """Regla del pre-registro §4: el primer 0,5 todavía cuenta; a las 24 h ya es relleno."""
    markets, _ = build_markets(bronze_markets(market("1")))
    series = [0.7, 0.5, 0.5, 0.5, 0.6, 0.5]
    points = [("111", "0x1", T0 + i * DAY, p) for i, p in enumerate(series)]
    prices, report = build_prices(bronze_prices(points), markets)
    assert prices["is_placeholder"].to_list() == [False, False, True, True, False, False]
    assert prices["price"].to_list() == [0.7, 0.5, None, None, 0.6, 0.5]
    assert prices["raw_price"].to_list() == series
    assert "precios de relleno (0,5 sin moverse ≥ 24 h): 2" in report.checks


def test_points_after_close_are_flagged() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    close = int(datetime(2024, 3, 11, 8, tzinfo=UTC).timestamp())
    prices, _ = build_prices(
        bronze_prices([("111", "0x1", close - 60, 0.99), ("111", "0x1", close + 60, 1.0)]), markets
    )
    assert prices["after_close"].to_list() == [False, True]


def test_identical_duplicates_are_dropped_and_conflicts_fail() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    same = bronze_prices([("111", "0x1", T0, 0.4), ("111", "0x1", T0, 0.4)])
    prices, report = build_prices(same, markets)
    assert prices.height == 1
    assert report.duplicates_removed == 1
    with pytest.raises(SilverValidationError, match="conflicto"):
        build_prices(bronze_prices([("111", "0x1", T0, 0.4), ("111", "0x1", T0, 0.6)]), markets)


def test_prices_outside_zero_one_fail() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    with pytest.raises(SilverValidationError, match="precios"):
        build_prices(bronze_prices([("111", "0x1", T0, 1.2)]), markets)


def test_prices_asof_never_looks_ahead_and_skips_placeholders() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    points = [("111", "0x1", T0 + i * DAY, p) for i, p in enumerate([0.6, 0.5, 0.5, 0.9])]
    prices, _ = build_prices(bronze_prices(points), markets)

    at_day2 = prices_asof(prices, datetime.fromtimestamp(T0 + 2 * DAY, UTC))
    assert at_day2["price"].to_list() == [0.5]  # el 0,5 del día 1; el del día 2 es relleno
    before = prices_asof(prices, datetime.fromtimestamp(T0, UTC) - timedelta(seconds=1))
    assert before.is_empty()


def test_build_silver_writes_tables_and_quality_reports(tmp_path: Path) -> None:
    src = FakeSource(
        [market("1")], history={"111": [{"t": T0, "p": 0.8}], "222": [{"t": T0, "p": 0.2}]}
    )
    ingest_markets(src, tmp_path / "bronze", [date(2024, 3, 1)], min_volume=0, clock=FixedClock())
    markets, _ = build_markets(read_bronze(tmp_path / "bronze", "markets"))
    ingest_prices(src, tmp_path / "bronze", markets, clock=FixedClock())

    reports = build_silver(tmp_path)

    assert [r.table for r in reports] == ["polymarket/markets", "polymarket/prices_1440"]
    silver = tmp_path / "silver" / "polymarket"
    assert pl.read_parquet(silver / "markets.parquet").height == 1
    assert pl.read_parquet(silver / "prices_1440.parquet").height == 2
    assert (tmp_path / "silver" / "_quality" / "polymarket-markets.json").exists()


def test_parallel_download_gives_the_same_bronze_as_sequential(tmp_path: Path) -> None:
    markets, _ = build_markets(
        bronze_markets(*(market(str(i), tokens=(f"{i}1", f"{i}2")) for i in range(6)))
    )
    history = {f"{i}{o}": [{"t": T0 + i, "p": 0.1 * o}] for i in range(6) for o in (1, 2)}
    ingest_prices(FakeSource(history=history), tmp_path / "a", markets, clock=FixedClock())
    ingest_prices(
        FakeSource(history=history), tmp_path / "b", markets, clock=FixedClock(), workers=4
    )
    assert read_bronze(tmp_path / "a", "prices", 1440).equals(
        read_bronze(tmp_path / "b", "prices", 1440)
    )


def test_parallel_failures_still_block_the_month(tmp_path: Path) -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    report = ingest_trades(
        FakeSource(fail=set()), tmp_path, markets, clock=FixedClock(), max_pages=1, workers=3
    )
    assert report.ok
    failing = FakeSource(fail={"111"})
    report = ingest_prices(failing, tmp_path, markets, clock=FixedClock(), workers=3)
    assert report.failed == ["prices/1440/2024-03"]


def test_report_counts_tokens_without_history() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    _, report = build_prices(bronze_prices([("111", "0x1", T0, 0.4)]), markets)
    assert "tokens del catálogo sin historial: 1" in report.checks


def test_report_counts_points_far_from_midnight() -> None:
    markets, _ = build_markets(bronze_markets(market("1")))
    points = [("111", "0x1", T0 + 3, 0.4), ("111", "0x1", T0 + DAY + 3600, 0.5)]
    _, report = build_prices(bronze_prices(points), markets)
    assert "puntos a más de 1 min de las 00:00 UTC: 1" in report.checks


def test_markets_from_files_streams_in_batches_and_matches_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KE-017: tipar por archivos y tandas da lo mismo que cargarlo todo, sin el crudo entero."""
    from prometheus_platform.data_platform import polymarket as pm  # noqa: PLC0415

    monkeypatch.setattr(pm, "BATCH_ROWS", 1)  # una fila por tanda: fuerza varias tandas
    src = FakeSource(
        [market("1"), market("2"), market("3", end="2024-04-02T00:00:00Z", prices='["0", "0"]')]
    )
    ingest_markets(
        src, tmp_path, [date(2024, 3, 1), date(2024, 4, 1)], min_volume=0, clock=FixedClock()
    )
    streamed, streamed_report = pm.build_markets_from_files(pm.bronze_files(tmp_path, "markets"))
    in_memory, memory_report = build_markets(read_bronze(tmp_path, "markets"))
    assert streamed.equals(in_memory)
    assert streamed_report.checks == memory_report.checks


def test_markets_from_no_files_is_an_error() -> None:
    from prometheus_platform.data_platform import polymarket as pm  # noqa: PLC0415

    with pytest.raises(SilverValidationError, match="vacío"):
        pm.build_markets_from_files([])
