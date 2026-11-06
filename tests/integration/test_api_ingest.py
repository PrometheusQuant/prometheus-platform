"""PQ-65: ingesta incremental por la API pública y precedencia de Data Vision en silver."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl
import pyarrow.parquet as pq
import pytest

from prometheus_platform.adapters import binance_rest
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.parquet_bronze import KLINE_COLUMNS, ParquetBronzeStore
from prometheus_platform.api import cli
from prometheus_platform.data_platform.silver import build_klines, read_bronze_sources
from prometheus_platform.domain.datasets import (
    ArchiveRef,
    DatasetKind,
    Granularity,
    Market,
    RawArchive,
)

ZipFactory = Callable[[str, str], tuple[bytes, str]]
H = 3_600_000
NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
JAN_MS = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)


def kline_rows(start_ms: int, hours: int, close: float = 100.5) -> list[str]:
    return [
        f"{start_ms + i * H},100,101,99,{close},10,{start_ms + (i + 1) * H - 1},1000,7,5,500,0"
        for i in range(hours)
    ]


def write(
    store: ParquetBronzeStore, ref: ArchiveRef, rows: list[str], make_zip: ZipFactory
) -> None:
    payload, sha = make_zip("f.csv", ",".join(KLINE_COLUMNS) + "\n" + "\n".join(rows) + "\n")
    store.write(RawArchive(ref, payload, sha))


def test_data_vision_replaces_the_api_for_the_months_it_published(
    tmp_path: Path, make_zip: ZipFactory
) -> None:
    clock = FixedClock(NOW)
    audited = ParquetBronzeStore(tmp_path, source="binance_data_vision", clock=clock)
    api = ParquetBronzeStore(tmp_path, source="binance_api", clock=clock)
    jan = ArchiveRef(Market.USDM, DatasetKind.KLINES, "SOLUSDT", date(2025, 1, 1), "1h")
    write(audited, jan, kline_rows(JAN_MS, 48), make_zip)  # 1 y 2 de enero, auditados

    day = ArchiveRef(
        Market.USDM, DatasetKind.KLINES, "SOLUSDT", date(2025, 1, 1), "1h", Granularity.DAILY
    )
    api_jan = kline_rows(JAN_MS, 24)
    api_jan[5] = api_jan[5].replace(",100.5,", ",100.7,")  # la API difiere en una vela
    write(api, day, api_jan, make_zip)
    feb_ms = JAN_MS + 31 * 24 * H
    feb = ArchiveRef(
        Market.USDM, DatasetKind.KLINES, "SOLUSDT", date(2025, 2, 1), "1h", Granularity.DAILY
    )
    write(api, feb, kline_rows(feb_ms, 3), make_zip)  # febrero aún no está en Data Vision

    raw, sources = read_bronze_sources(tmp_path, DatasetKind.KLINES, Market.USDM, "SOLUSDT", "1h")
    assert sources == {
        "filas_data_vision": 48,
        "filas_api": 3,
        "filas_api_reemplazadas": 24,
        "solo_api": 0,
        "solo_data_vision": 0,  # solo se compara el tramo que cubre la API
        "valores_distintos": 1,
    }
    frame, report = build_klines(raw, Market.USDM, "SOLUSDT", "1h")  # mismos checks de silver
    assert frame.height == 51
    assert frame.filter(pl.col("open_time").dt.month() == 1)["close"].max() == 100.5
    assert report.gaps == 1  # el hueco entre el 2 de enero y febrero se informa, no se rellena


def test_funding_differences_are_compared_by_settlement_hour(
    tmp_path: Path, make_zip: ZipFactory
) -> None:
    clock = FixedClock(NOW)
    audited = ParquetBronzeStore(tmp_path, source="binance_data_vision", clock=clock)
    api = ParquetBronzeStore(tmp_path, source="binance_api", clock=clock)
    month = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "SOLUSDT", date(2025, 1, 1))
    header = "calc_time,funding_interval_hours,last_funding_rate\n"
    payload, sha = make_zip(
        "f.csv", header + f"{JAN_MS + 2},8,0.0001\n{JAN_MS + 8 * H + 3},8,0.0002\n"
    )
    audited.write(RawArchive(month, payload, sha))
    day = ArchiveRef(
        Market.USDM, DatasetKind.FUNDING_RATE, "SOLUSDT", date(2025, 1, 1), None, Granularity.DAILY
    )
    payload, sha = make_zip("f.csv", header + f"{JAN_MS},8,0.0001\n{JAN_MS + 8 * H},8,0.0003\n")
    api.write(RawArchive(day, payload, sha))
    _, sources = read_bronze_sources(
        tmp_path, DatasetKind.FUNDING_RATE, Market.USDM, "SOLUSDT", None
    )
    # El jitter de calc_time de Data Vision no cuenta como diferencia; la tasa distinta, sí.
    assert sources["valores_distintos"] == 1
    assert sources["solo_api"] == sources["solo_data_vision"] == 0


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    now_ms = int(NOW.timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.path}?{request.url.params.get('startTime', '')}")
        q = request.url.params
        if request.url.path.endswith("/fundingInfo"):
            return httpx.Response(200, json=[])
        start, end = int(q["startTime"]), int(q["endTime"])
        if request.url.path.endswith("/fundingRate"):
            items = [
                {"fundingTime": t, "fundingRate": "0.0001"}
                for t in range(start, min(end, now_ms) + 1, 8 * H)
            ]
            return httpx.Response(200, json=items)
        bars = [
            [t, "1", "2", "0.5", "1.5", "9", t + H - 1, "9", 1, "4", "4", "0"]
            for t in range(start, min(end, now_ms) + 1, H)
        ]
        return httpx.Response(200, json=bars)

    monkeypatch.setattr(
        cli, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return calls


def test_cli_api_ingest_is_incremental_and_silver_reports_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_api: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    lake = tmp_path / "lake"
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    monkeypatch.setattr(cli, "SystemClock", lambda: FixedClock(NOW))
    args = ["ingest", "--source", "api", "klines", "--market", "um", "--symbol", "SOLUSDT"]
    args += ["--interval", "1h", "--since", "2026-11-05"]

    assert cli.main(args) == 0
    assert "escritos=2" in capsys.readouterr().out  # el 5 (completo) y el 6 (en curso)
    first_run = len(fake_api)

    assert cli.main(args) == 0
    out = capsys.readouterr().out
    # El 5 ya está completo en bronze: solo se vuelve a pedir el día en curso.
    assert "escritos=0 ya_ingeridos=1" in out
    assert len(fake_api) - first_run == 1

    api_root = lake / "bronze" / "source=binance_api"
    files = sorted(api_root.rglob("*.parquet"))
    assert [f.name for f in files] == [
        "SOLUSDT-1h-2026-11-05.parquet",
        "SOLUSDT-1h-2026-11-06.parquet",
    ]
    assert pq.read_table(files[1]).num_rows == 12  # solo velas cerradas


def test_cli_skips_months_already_published_by_data_vision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_api: list[str], make_zip: ZipFactory
) -> None:
    lake = tmp_path / "lake"
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    monkeypatch.setattr(cli, "SystemClock", lambda: FixedClock(NOW))
    audited = ParquetBronzeStore(
        lake / "bronze", source="binance_data_vision", clock=FixedClock(NOW)
    )
    oct_ref = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "SOLUSDT", date(2026, 10, 1))
    payload, sha = make_zip("f.csv", "calc_time,funding_interval_hours,last_funding_rate\n1,8,0\n")
    audited.write(RawArchive(oct_ref, payload, sha))

    args = ["ingest", "--source", "api", "funding", "--symbol", "SOLUSDT", "--since", "2026-10-31"]
    assert cli.main(args) == 0
    paths = {c.split("?")[0] for c in fake_api}
    assert "/fapi/v1/fundingRate" in paths
    starts = {c.split("?")[1] for c in fake_api if "fundingRate" in c}
    oct31 = str(int(datetime(2026, 10, 31, tzinfo=UTC).timestamp() * 1000))
    assert oct31 not in starts  # octubre ya lo publicó Data Vision


def test_cli_silver_build_records_the_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_api: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    lake = tmp_path / "lake"
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    monkeypatch.setattr(cli, "SystemClock", lambda: FixedClock(NOW))
    for market in ("um", "spot"):
        cli.main(
            [
                "ingest",
                "--source",
                "api",
                "klines",
                "--market",
                market,
                "--symbol",
                "SOLUSDT",
                "--interval",
                "1h",
                "--since",
                "2026-11-06",
            ]
        )
    cli.main(
        ["ingest", "--source", "api", "funding", "--symbol", "SOLUSDT", "--since", "2026-11-06"]
    )
    capsys.readouterr()

    assert cli.main(["silver", "build", "--symbol", "SOLUSDT"]) == 0
    assert "api=12" in capsys.readouterr().out
    quality = json.loads((lake / "silver" / "_quality" / "klines-um-1h-SOLUSDT.json").read_text())
    assert quality["fuentes"]["filas_api"] == 12
    assert quality["fuentes"]["filas_data_vision"] == 0


def test_cli_data_vision_still_requires_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    assert cli.main(["ingest", "funding", "--symbol", "SOLUSDT"]) == 2
    assert "--start" in capsys.readouterr().err
    assert binance_rest.SOURCE_NAME == "binance_api"
