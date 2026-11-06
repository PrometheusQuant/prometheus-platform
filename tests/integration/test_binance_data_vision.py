from collections.abc import Callable, Iterator
from datetime import date

import httpx
import pytest

from prometheus_platform.adapters.binance_data_vision import (
    BinanceDataVisionSource,
    archive_path,
)
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Granularity,
    Market,
)
from prometheus_platform.domain.ports import HistoricalDataSource

ZipFactory = Callable[[str, str], tuple[bytes, str]]
BASE = "https://data.binance.vision"
UM_1H = ArchiveRef(Market.USDM, DatasetKind.KLINES, "BTCUSDT", date(2024, 1, 1), "1h")
FUNDING = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", date(2024, 1, 1))


def source_for(
    handler: httpx.MockTransport, sleeps: list[float] | None = None, attempts: int = 4
) -> BinanceDataVisionSource:
    log = sleeps if sleeps is not None else []
    return BinanceDataVisionSource(
        httpx.Client(transport=handler),
        max_attempts=attempts,
        backoff_seconds=0.5,
        sleep=log.append,
    )


@pytest.mark.parametrize(
    ("ref", "path"),
    [
        (UM_1H, "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip"),
        (FUNDING, "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip"),
        (
            ArchiveRef(Market.SPOT, DatasetKind.KLINES, "ETHUSDT", date(2025, 3, 1), "1d"),
            "data/spot/monthly/klines/ETHUSDT/1d/ETHUSDT-1d-2025-03.zip",
        ),
        (
            ArchiveRef(
                Market.SPOT,
                DatasetKind.KLINES,
                "ETHUSDT",
                date(2025, 3, 7),
                "1h",
                Granularity.DAILY,
            ),
            "data/spot/daily/klines/ETHUSDT/1h/ETHUSDT-1h-2025-03-07.zip",
        ),
    ],
)
def test_archive_paths_match_data_vision_layout(ref: ArchiveRef, path: str) -> None:
    assert archive_path(ref) == path


def test_downloads_and_verifies_checksum(make_zip: ZipFactory) -> None:
    payload, sha = make_zip("BTCUSDT-1h-2024-01.csv", "1704067200000,1,2,0.5,1.5\n")
    routes = {
        f"{BASE}/{archive_path(UM_1H)}": payload,
        f"{BASE}/{archive_path(UM_1H)}.CHECKSUM": f"{sha}  BTCUSDT-1h-2024-01.zip\n".encode(),
    }
    source = source_for(
        httpx.MockTransport(lambda r: httpx.Response(200, content=routes[str(r.url)]))
    )

    expected = source.expected_checksum(UM_1H)
    archive = source.fetch(UM_1H, expected)
    assert expected == sha
    assert archive.payload == payload
    assert archive.sha256 == sha


def test_rejects_payload_that_does_not_match_checksum(make_zip: ZipFactory) -> None:
    payload, _ = make_zip("x.csv", "1,2\n")
    source = source_for(httpx.MockTransport(lambda r: httpx.Response(200, content=payload)))
    with pytest.raises(ChecksumMismatchError) as excinfo:
        source.fetch(UM_1H, "0" * 64)
    assert excinfo.value.expected == "0" * 64


def test_unpublished_archive_raises_not_found_without_retrying() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(ArchiveNotFoundError):
        source_for(httpx.MockTransport(handler)).expected_checksum(UM_1H)
    assert len(calls) == 1


def test_retries_transient_errors_with_exponential_backoff() -> None:
    responses: Iterator[httpx.Response | httpx.TransportError] = iter(
        [
            httpx.Response(503),
            httpx.ConnectTimeout("timeout"),
            httpx.Response(429),
            httpx.Response(200, content=b"f" * 64 + b"  file.zip"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        item = next(responses)
        if isinstance(item, httpx.TransportError):
            raise item
        return item

    sleeps: list[float] = []
    digest = source_for(httpx.MockTransport(handler), sleeps).expected_checksum(UM_1H)
    assert digest == "f" * 64
    assert sleeps == [0.5, 1.0, 2.0]


def test_gives_up_after_max_attempts() -> None:
    sleeps: list[float] = []
    source = source_for(httpx.MockTransport(lambda r: httpx.Response(502)), sleeps, attempts=3)
    with pytest.raises(DataSourceError, match="HTTP 502 tras 3 intentos"):
        source.expected_checksum(UM_1H)
    assert sleeps == [0.5, 1.0]


def test_non_retryable_http_errors_fail_fast() -> None:
    sleeps: list[float] = []
    source = source_for(httpx.MockTransport(lambda r: httpx.Response(403)), sleeps)
    with pytest.raises(DataSourceError, match="HTTP 403"):
        source.fetch(UM_1H, "a" * 64)
    assert sleeps == []


@pytest.mark.parametrize("body", [b"", b"not-a-checksum file.zip"])
def test_unreadable_checksum_file_is_an_error(body: bytes) -> None:
    source = source_for(httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    with pytest.raises(DataSourceError, match="ilegible"):
        source.expected_checksum(UM_1H)


def test_rejects_invalid_attempt_count() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        BinanceDataVisionSource(httpx.Client(), max_attempts=0)


def test_satisfies_the_port() -> None:
    source: HistoricalDataSource = source_for(httpx.MockTransport(lambda r: httpx.Response(404)))
    assert source is not None
