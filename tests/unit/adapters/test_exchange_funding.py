"""Funding de Bybit y OKX (PQ-79): mismo formato que Data Vision, paginado y sin claves."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from prometheus_platform.adapters.exchange_funding import (
    BybitFundingSource,
    OkxFundingSource,
    settlement_rows,
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

MARCH = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "SOLUSDT", date(2022, 3, 1))
START = int(datetime(2022, 3, 1, tzinfo=UTC).timestamp() * 1000)
H = 3_600_000


def csv_rows(payload: bytes) -> list[str]:
    bundle = zipfile.ZipFile(io.BytesIO(payload))
    return bundle.read(bundle.namelist()[0]).decode().splitlines()


def test_intervals_are_deduced_from_the_distance_between_settlements() -> None:
    rows = settlement_rows([(0, "0.1"), (8 * H, "0.2"), (12 * H, "0.3"), (12 * H + 7 * H, "0.4")])
    assert [r[1] for r in rows] == ["8", "8", "4", "8"]  # 7 h no es válido: 8 por defecto
    assert settlement_rows([(5, "0.1")]) == [["5", "8", "0.1"]]


def bybit(pages: list[list[dict[str, Any]]], seen: list[dict[str, str]]) -> BybitFundingSource:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        body = {"retCode": 0, "result": {"list": pages[len(seen) - 1]}}
        return httpx.Response(200, json=body)

    return BybitFundingSource(httpx.Client(transport=httpx.MockTransport(handler)))


def test_bybit_pages_backwards_and_writes_data_vision_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prometheus_platform.adapters import exchange_funding  # noqa: PLC0415

    monkeypatch.setattr(exchange_funding, "_BYBIT_PAGE", 2)
    newest = [
        {"fundingRateTimestamp": str(START + h * H), "fundingRate": "0.0001"} for h in (16, 8)
    ]
    oldest = [{"fundingRateTimestamp": str(START), "fundingRate": "-0.0002"}]
    seen: list[dict[str, str]] = []
    source = bybit([newest, oldest], seen)
    archive = source.fetch(MARCH, source.expected_checksum(MARCH))
    lines = csv_rows(archive.payload)
    assert lines[0] == "calc_time,funding_interval_hours,last_funding_rate"
    assert lines[1:] == [
        f"{START},8,-0.0002",
        f"{START + 8 * H},8,0.0001",
        f"{START + 16 * H},8,0.0001",
    ]
    assert int(seen[1]["endTime"]) == START + 8 * H - 1  # la segunda página pide las anteriores
    assert seen[0]["category"] == "linear"


def test_an_empty_month_is_not_published_and_errors_are_data_source_errors() -> None:
    with pytest.raises(ArchiveNotFoundError):
        bybit([[]], []).expected_checksum(MARCH)

    def broken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "params error"})

    source = BybitFundingSource(httpx.Client(transport=httpx.MockTransport(broken)))
    with pytest.raises(DataSourceError, match="ValueError"):
        source.expected_checksum(MARCH)


def test_only_monthly_funding_and_checksums_must_match() -> None:
    source = bybit([[{"fundingRateTimestamp": str(START), "fundingRate": "0.0001"}]] * 3, [])
    with pytest.raises(DataSourceError, match="mensual"):
        source.expected_checksum(
            ArchiveRef(
                Market.USDM,
                DatasetKind.FUNDING_RATE,
                "SOLUSDT",
                date(2022, 3, 5),
                None,
                Granularity.DAILY,
            )
        )
    with pytest.raises(ChecksumMismatchError):
        source.fetch(MARCH, "0" * 64)


def test_okx_pages_with_after_and_uses_the_realized_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from prometheus_platform.adapters import exchange_funding  # noqa: PLC0415

    monkeypatch.setattr(exchange_funding, "_OKX_PAGE", 2)
    seen: list[dict[str, str]] = []
    pages = [
        [
            {"fundingTime": str(START + h * H), "realizedRate": "0.0003", "fundingRate": "9"}
            for h in (16, 8)
        ],
        [{"fundingTime": str(START), "realizedRate": "0.0001", "fundingRate": "9"}],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"code": "0", "data": pages[len(seen) - 1]})

    source = OkxFundingSource(httpx.Client(transport=httpx.MockTransport(handler)))
    lines = csv_rows(source.fetch(MARCH, source.expected_checksum(MARCH)).payload)
    assert lines[1:] == [
        f"{START},8,0.0001",
        f"{START + 8 * H},8,0.0003",
        f"{START + 16 * H},8,0.0003",
    ]
    assert seen[0]["instId"] == "SOL-USDT-SWAP"
    assert int(seen[1]["after"]) == START + 8 * H
