import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from prometheus_platform.adapters.binance_rest import (
    FUNDING_COLUMNS,
    BinanceRestSource,
    RetryPolicy,
    day_refs,
)
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.parquet_bronze import KLINE_COLUMNS, ParquetBronzeStore
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Granularity,
    Market,
)

H = 3_600_000
DAY = date(2026, 11, 5)
DAY_MS = int(datetime(2026, 11, 5, tzinfo=UTC).timestamp() * 1000)
NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)  # el día 5 está cerrado; el 6, en curso


class FakeExchange:
    """API pública simulada: velas horarias y funding cada 8 h, paginadas como la real."""

    def __init__(
        self, now: datetime = NOW, *, interval_info: list[dict[str, object]] | None = None
    ):
        self.now_ms = int(now.timestamp() * 1000)
        self.calls: list[httpx.Request] = []
        self.interval_info = interval_info or []
        self.failures: list[httpx.Response] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.failures:
            return self.failures.pop(0)
        q = request.url.params
        if request.url.path.endswith("/klines"):
            start, end, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
            first = -(-start // H) * H
            bars = [
                [t, "100.0", "101.0", "99.0", "100.5", "10", t + H - 1, "1000", 7, "5", "500", "0"]
                for t in range(first, min(end, self.now_ms) + 1, H)
            ][:limit]
            return httpx.Response(200, json=bars, headers={"X-MBX-USED-WEIGHT-1M": "10"})
        if request.url.path.endswith("/fundingRate"):
            start, end, limit = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
            first = -(-start // (8 * H)) * 8 * H
            items = [
                {
                    "symbol": q["symbol"],
                    "fundingTime": t,
                    "fundingRate": "0.00010000",
                    "markPrice": "1",
                }
                for t in range(first, min(end, self.now_ms) + 1, 8 * H)
            ][:limit]
            return httpx.Response(200, json=items)
        if request.url.path.endswith("/fundingInfo"):
            return httpx.Response(200, json=self.interval_info)
        return httpx.Response(404)


def source(exchange: FakeExchange, sleeps: list[float] | None = None) -> BinanceRestSource:
    log = sleeps if sleeps is not None else []
    return BinanceRestSource(
        httpx.Client(transport=httpx.MockTransport(exchange.handler)),
        now=lambda: NOW,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
        sleep=log.append,
    )


def klines_ref(market: Market = Market.USDM, day: date = DAY) -> ArchiveRef:
    return ArchiveRef(market, DatasetKind.KLINES, "SOLUSDT", day, "1h", Granularity.DAILY)


def funding_ref(day: date = DAY) -> ArchiveRef:
    return ArchiveRef(
        Market.USDM, DatasetKind.FUNDING_RATE, "SOLUSDT", day, None, Granularity.DAILY
    )


def rows_of(store: ParquetBronzeStore, ref: ArchiveRef) -> list[dict[str, object]]:
    return pq.read_table(store.path_for(ref)).to_pylist()


@pytest.fixture
def store(tmp_path: Path) -> ParquetBronzeStore:
    return ParquetBronzeStore(tmp_path, source="binance_api", clock=FixedClock(NOW))


def test_day_refs_cover_each_utc_day() -> None:
    refs = day_refs(klines_ref(day=date(2026, 10, 30)), date(2026, 11, 2))
    assert [r.period for r in refs] == [date(2026, 10, d) for d in (30, 31)] + [
        date(2026, 11, d) for d in (1, 2)
    ]
    assert {r.granularity for r in refs} == {Granularity.DAILY}
    with pytest.raises(ValueError, match="anterior"):
        day_refs(klines_ref(), date(2026, 11, 1))


@pytest.mark.parametrize(
    ("market", "path", "limit"),
    [(Market.USDM, "/fapi/v1/klines", 1500), (Market.SPOT, "/api/v3/klines", 1000)],
)
def test_klines_use_the_right_endpoint_and_produce_the_data_vision_schema(
    store: ParquetBronzeStore, market: Market, path: str, limit: int
) -> None:
    exchange = FakeExchange()
    src, ref = source(exchange), klines_ref(market)
    rows = store.write(src.fetch(ref, src.expected_checksum(ref)))
    assert rows == 24
    assert exchange.calls[0].url.path == path
    assert exchange.calls[0].url.params["limit"] == str(limit)
    table = pq.read_table(store.path_for(ref))
    lineage = ["_source_file", "_source_sha256", "_source_row", "_ingested_at"]
    assert table.schema.names == [*KLINE_COLUMNS, *lineage]  # igual que Data Vision
    assert all(str(table.schema.field(c).type) == "string" for c in KLINE_COLUMNS)
    assert rows_of(store, ref)[0]["open_time"] == str(DAY_MS)
    assert rows_of(store, ref)[0]["_source_file"] == "SOLUSDT-1h-2026-11-05.zip"


def test_pagination_follows_the_last_open_time() -> None:
    exchange = FakeExchange()
    src = BinanceRestSource(
        httpx.Client(transport=httpx.MockTransport(exchange.handler)), now=lambda: NOW
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "prometheus_platform.adapters.binance_rest._PAGE_LIMIT",
            {Market.USDM: 10, Market.SPOT: 10},
        )
        archive = src.fetch(klines_ref(), src.expected_checksum(klines_ref()))
    starts = [int(c.url.params["startTime"]) for c in exchange.calls]
    assert starts == [DAY_MS, DAY_MS + 9 * H + 1, DAY_MS + 19 * H + 1]
    assert archive.payload  # 24 velas en 3 páginas (10 + 10 + 4)


def test_open_candles_are_left_out_until_they_close(store: ParquetBronzeStore) -> None:
    exchange = FakeExchange()
    src, today = source(exchange), klines_ref(day=date(2026, 11, 6))
    assert store.write(src.fetch(today, src.expected_checksum(today))) == 12  # 00:00 a 11:00


def test_funding_uses_the_published_interval_and_defaults_to_8h(store: ParquetBronzeStore) -> None:
    exchange = FakeExchange(interval_info=[{"symbol": "SOLUSDT", "fundingIntervalHours": 4}])
    src = source(exchange)
    store.write(src.fetch(funding_ref(), src.expected_checksum(funding_ref())))
    table = pq.read_table(store.path_for(funding_ref()))
    assert table.schema.names[:3] == list(FUNDING_COLUMNS)
    rows = table.to_pylist()
    assert [r["calc_time"] for r in rows] == [str(DAY_MS + h * H) for h in (0, 8, 16)]
    assert {r["funding_interval_hours"] for r in rows} == {"4"}

    other = ArchiveRef(
        Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", DAY, None, Granularity.DAILY
    )
    archive = src.fetch(other, src.expected_checksum(other))
    text = zipfile.ZipFile(io.BytesIO(archive.payload)).read("BTCUSDT-fundingRate-2026-11-05.csv")
    assert b",8,0.00010000" in text
    info_calls = [c for c in exchange.calls if c.url.path.endswith("/fundingInfo")]
    assert len(info_calls) == 1  # se consulta una vez por proceso


def test_same_data_same_checksum_and_a_single_download() -> None:
    exchange = FakeExchange()
    first, second = source(exchange), source(FakeExchange())
    sha = first.expected_checksum(klines_ref())
    assert sha == second.expected_checksum(klines_ref())  # ZIP determinista
    calls = len(exchange.calls)
    first.fetch(klines_ref(), sha)
    assert len(exchange.calls) == calls  # fetch reutiliza la descarga del checksum
    with pytest.raises(ChecksumMismatchError):
        first.fetch(klines_ref(), "0" * 64)


def test_a_day_without_data_is_missing_not_an_error() -> None:
    src = source(FakeExchange())
    future = klines_ref(day=date(2026, 11, 8))
    with pytest.raises(ArchiveNotFoundError):
        src.expected_checksum(future)


def test_rate_limits_are_respected() -> None:
    exchange = FakeExchange()
    exchange.failures = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(503)]
    sleeps: list[float] = []
    src = source(exchange, sleeps)
    src.expected_checksum(klines_ref())
    assert sleeps == [7.0, 2.0]  # Retry-After manda; después, backoff exponencial

    banned = FakeExchange()
    banned.failures = [httpx.Response(418)] * 3
    with pytest.raises(DataSourceError, match="HTTP 418 tras 3 intentos"):
        source(banned).expected_checksum(klines_ref())

    invalid = FakeExchange()
    invalid.failures = [httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})]
    with pytest.raises(DataSourceError, match="HTTP 400"):
        source(invalid).expected_checksum(klines_ref())
    assert len(invalid.calls) == 1  # un error del cliente no se reintenta


def test_high_used_weight_pauses_until_the_next_minute() -> None:
    def heavy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"X-MBX-USED-WEIGHT-1M": "2000"})

    sleeps: list[float] = []
    src = BinanceRestSource(
        httpx.Client(transport=httpx.MockTransport(heavy)),
        now=lambda: datetime(2026, 11, 6, 12, 0, 45, tzinfo=UTC),
        sleep=sleeps.append,
    )
    with pytest.raises(ArchiveNotFoundError):
        src.expected_checksum(klines_ref())
    assert sleeps == [15.0]


def test_only_daily_archives_and_valid_retry_policy() -> None:
    monthly = ArchiveRef(Market.USDM, DatasetKind.KLINES, "SOLUSDT", date(2026, 11, 1), "1h")
    with pytest.raises(DataSourceError, match="diarios"):
        source(FakeExchange()).expected_checksum(monthly)
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_transport_errors_are_retried() -> None:
    attempts = {"n": 0}
    exchange = FakeExchange()

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("sin red")
        return exchange.handler(request)

    sleeps: list[float] = []
    src = BinanceRestSource(
        httpx.Client(transport=httpx.MockTransport(flaky)), now=lambda: NOW, sleep=sleeps.append
    )
    assert src.expected_checksum(klines_ref())
    assert sleeps == [1.0]
