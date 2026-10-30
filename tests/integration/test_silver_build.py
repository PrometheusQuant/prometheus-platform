import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.parquet_bronze import KLINE_COLUMNS, ParquetBronzeStore
from prometheus_platform.api import cli
from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Market, RawArchive

ZipFactory = Callable[[str, str], tuple[bytes, str]]
H = 3_600_000
T0 = 1_735_689_600_000  # 2025-01-01


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    yield
    structlog.reset_defaults()


def kline_csv(unit: int, header: bool) -> str:
    rows = []
    for i in range(3):
        start, end = (T0 + i * H) * unit, (T0 + (i + 1) * H - 1) * unit
        rows.append(f"{start},100,105,99,{101 + i},10,{end},1000,7,5,500,0")
    return (",".join(KLINE_COLUMNS) + "\n" if header else "") + "\n".join(rows) + "\n"


def write_bronze(tmp_path: Path, make_zip: ZipFactory) -> None:
    store = ParquetBronzeStore(
        tmp_path / "lake" / "bronze",
        source="binance_data_vision",
        clock=FixedClock(datetime(2026, 10, 30, tzinfo=UTC)),
    )
    jan = date(2025, 1, 1)
    archives = [
        (ArchiveRef(Market.SPOT, DatasetKind.KLINES, "BTCUSDT", jan, "1h"), kline_csv(1000, False)),
        (ArchiveRef(Market.USDM, DatasetKind.KLINES, "BTCUSDT", jan, "1h"), kline_csv(1, True)),
        (
            ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", jan),
            f"calc_time,funding_interval_hours,last_funding_rate\n{T0 + 1},8,0.0001\n",
        ),
    ]
    for ref, text in archives:
        payload, sha = make_zip("f.csv", text)
        store.write(RawArchive(ref, payload, sha))


def test_silver_build_aligns_spot_microseconds_with_perp_milliseconds(
    tmp_path: Path, make_zip: ZipFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    write_bronze(tmp_path, make_zip)
    assert cli.main(["silver", "build", "--symbol", "btcusdt"]) == 0
    assert "klines/spot/1h/BTCUSDT: filas=3" in capsys.readouterr().out

    silver = tmp_path / "lake" / "silver"
    spot = pl.read_parquet(silver / "klines/market=spot/interval=1h/BTCUSDT.parquet")
    perp = pl.read_parquet(silver / "klines/market=um/interval=1h/BTCUSDT.parquet")
    assert spot["open_time"].to_list() == perp["open_time"].to_list()  # SC-002
    funding = pl.read_parquet(silver / "funding/BTCUSDT.parquet")
    assert funding["funding_time"][0] == datetime(2025, 1, 1, tzinfo=UTC)

    report = json.loads((silver / "_quality/klines-spot-1h-BTCUSDT.json").read_text())
    assert report["rows"] == 3
    assert "OHLC coherente" in report["checks"]


def test_silver_build_fails_cleanly_without_bronze(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["silver", "build", "--symbol", "ETHUSDT"]) == 1
    assert "no tiene filas" in capsys.readouterr().err
