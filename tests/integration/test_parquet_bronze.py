import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.parquet_bronze import (
    KLINE_COLUMNS,
    REJECTIONS_FILE,
    BronzeFormatError,
    ParquetBronzeStore,
)
from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Market, RawArchive
from prometheus_platform.domain.ports import BronzeStore

ZipFactory = Callable[[str, str], tuple[bytes, str]]
NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)
SPOT_1H = ArchiveRef(Market.SPOT, DatasetKind.KLINES, "BTCUSDT", date(2025, 1, 1), "1h")
UM_1H = ArchiveRef(Market.USDM, DatasetKind.KLINES, "BTCUSDT", date(2022, 1, 1), "1h")
FUNDING = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", date(2024, 1, 1))

# Filas reales de Data Vision (recortadas): spot en microsegundos, sin cabecera.
SPOT_CSV = (
    "1735689600000000,93576.00000000,94509.42000000,93489.03000000,94401.14000000,"
    "755.99010000,1735693199999999,71068810.55946380,93525,421.08319000,39596777.77992590,0\n"
    "1735693200000000,94401.13000000,94554.48000000,94207.99000000,94275.82000000,"
    "457.85216000,1735696799999999,43225419.72893000,72045,213.47215000,20155424.77283930,0\n"
)
UM_CSV = (
    ",".join(KLINE_COLUMNS) + "\n"
    "1640995200000,46210.57,46729.00,46205.00,46656.11,7062.618,1640998799999,"
    "328913452.24296,90544,3803.389,177133556.05219,0\n"
)
FUNDING_CSV = "calc_time,funding_interval_hours,last_funding_rate\n1704067200000,8,0.00037409\n"


@pytest.fixture
def store(tmp_path: Path) -> ParquetBronzeStore:
    return ParquetBronzeStore(
        tmp_path / "bronze", source="binance_data_vision", clock=FixedClock(NOW)
    )


def archive(ref: ArchiveRef, csv: str, make_zip: ZipFactory) -> RawArchive:
    payload, sha = make_zip("file.csv", csv)
    return RawArchive(ref, payload, sha)


def test_partition_layout(store: ParquetBronzeStore, tmp_path: Path) -> None:
    assert store.path_for(UM_1H) == (
        tmp_path / "bronze/source=binance_data_vision/dataset=klines/market=um/symbol=BTCUSDT"
        "/interval=1h/year=2022/month=01/BTCUSDT-1h-2022-01.parquet"
    )
    assert "interval=none" in str(store.path_for(FUNDING))


def test_headerless_csv_keeps_raw_values_as_text(
    store: ParquetBronzeStore, make_zip: ZipFactory
) -> None:
    raw = archive(SPOT_1H, SPOT_CSV, make_zip)
    assert store.write(raw) == 2

    table = pq.read_table(store.path_for(SPOT_1H))
    lineage = ["_source_file", "_source_sha256", "_source_row", "_ingested_at"]
    assert table.column_names == [*KLINE_COLUMNS, *lineage]
    # Sin transformar: los µs de spot 2025 se conservan tal cual (se normalizan en silver).
    assert table.column("open_time").to_pylist() == ["1735689600000000", "1735693200000000"]
    assert table.column("close").to_pylist() == ["94401.14000000", "94275.82000000"]
    assert table.column("_source_file").to_pylist() == ["BTCUSDT-1h-2025-01.zip"] * 2
    assert table.column("_source_sha256").to_pylist() == [raw.sha256] * 2
    assert table.column("_source_row").to_pylist() == [1, 2]
    assert table.column("_ingested_at").to_pylist() == [NOW, NOW]


def test_csv_with_header_uses_its_column_names(
    store: ParquetBronzeStore, make_zip: ZipFactory
) -> None:
    assert store.write(archive(UM_1H, UM_CSV, make_zip)) == 1
    assert store.write(archive(FUNDING, FUNDING_CSV, make_zip)) == 1
    funding = pq.read_table(store.path_for(FUNDING))
    assert funding.column("last_funding_rate").to_pylist() == ["0.00037409"]
    assert funding.column("funding_interval_hours").to_pylist() == ["8"]


def test_contains_compares_the_source_checksum(
    store: ParquetBronzeStore, make_zip: ZipFactory
) -> None:
    raw = archive(SPOT_1H, SPOT_CSV, make_zip)
    assert not store.contains(SPOT_1H, raw.sha256)
    store.write(raw)
    assert store.contains(SPOT_1H, raw.sha256)
    assert not store.contains(SPOT_1H, "0" * 64)  # el proveedor republicó el archivo


def test_rewrite_replaces_atomically(store: ParquetBronzeStore, make_zip: ZipFactory) -> None:
    store.write(archive(SPOT_1H, SPOT_CSV, make_zip))
    store.write(archive(SPOT_1H, SPOT_CSV.splitlines(keepends=True)[0], make_zip))
    path = store.path_for(SPOT_1H)
    assert pq.read_table(path).num_rows == 1
    assert [p.name for p in path.parent.iterdir()] == [path.name]  # sin .tmp residuales


@pytest.mark.parametrize(
    ("ref", "csv", "message"),
    [
        (SPOT_1H, "", "vacío"),
        (SPOT_1H, "1,2,3\n", "columnas"),
        (FUNDING, "1704067200000,8,0.0001\n", "sin cabecera"),
    ],
)
def test_malformed_csv_is_refused(
    store: ParquetBronzeStore, make_zip: ZipFactory, ref: ArchiveRef, csv: str, message: str
) -> None:
    with pytest.raises(BronzeFormatError, match=message):
        store.write(archive(ref, csv, make_zip))
    assert not store.path_for(ref).exists()


def test_zip_without_exactly_one_csv_is_refused(store: ParquetBronzeStore) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("readme.txt", "hola")
    payload = buffer.getvalue()
    raw = RawArchive(SPOT_1H, payload, hashlib.sha256(payload).hexdigest())
    with pytest.raises(BronzeFormatError, match="un CSV"):
        store.write(raw)


def test_rejections_are_appended_as_json_lines(store: ParquetBronzeStore, tmp_path: Path) -> None:
    store.record_rejection(SPOT_1H, "checksum esperado a, obtenido b")
    store.record_rejection(FUNDING, "HTTP 503")
    lines = (tmp_path / "bronze" / REJECTIONS_FILE).read_text().splitlines()
    first = json.loads(lines[0])
    assert first == {
        "at": NOW.isoformat(),
        "source": "binance_data_vision",
        "archive": str(SPOT_1H),
        "reason": "checksum esperado a, obtenido b",
    }
    assert len(lines) == 2


def test_satisfies_the_port(store: ParquetBronzeStore) -> None:
    port: BronzeStore = store
    assert not port.contains(FUNDING, "a" * 64)
