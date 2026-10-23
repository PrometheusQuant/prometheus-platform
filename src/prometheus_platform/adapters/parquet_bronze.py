"""Capa bronze en Parquet: cada archivo del proveedor se guarda tal cual llegó.

Cumple el puerto ``BronzeStore``. "Tal cual" quiere decir que todas las columnas se guardan como
texto, con el valor exacto del CSV: la normalización de unidades y tipos es trabajo de silver.
A cada fila se le añaden columnas de linaje para saber de qué archivo y checksum viene.

Distribución en disco (particiones estilo Hive, legibles con DuckDB y Polars)::

    <root>/source=<s>/dataset=<d>/market=<m>/symbol=<S>/interval=<i>/year=<YYYY>/month=<MM>/<archivo>.parquet

El checksum del origen se guarda también en los metadatos del Parquet, lo que permite saber si
un archivo ya está ingerido sin leer sus filas.
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Granularity, RawArchive
from prometheus_platform.domain.ports import Clock

SHA256_METADATA_KEY = b"prometheus.source_sha256"
REJECTIONS_FILE = "_rejections.jsonl"

# Columnas de los CSV sin cabecera (las velas anteriores a 2022-01 en futuros y todas las de spot).
KLINE_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)
_DEFAULT_COLUMNS = {DatasetKind.KLINES: KLINE_COLUMNS}


class BronzeFormatError(ValueError):
    """El contenido del archivo no tiene la forma esperada."""


def _archive_stem(ref: ArchiveRef) -> str:
    period = (
        ref.period.strftime("%Y-%m")
        if ref.granularity is Granularity.MONTHLY
        else ref.period.isoformat()
    )
    return f"{ref.symbol}-{ref.interval or ref.dataset.value}-{period}"


def _read_csv(archive: RawArchive) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(archive.payload)) as bundle:
        members = [name for name in bundle.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise BronzeFormatError(f"{archive.ref}: se esperaba un CSV y hay {len(members)}")
        text = bundle.read(members[0]).decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if not rows:
        raise BronzeFormatError(f"{archive.ref}: CSV vacío")
    # La cabecera se detecta por contenido: su primera celda no es un timestamp numérico.
    if not rows[0][0].strip().isdigit():
        header, body = [c.strip() for c in rows[0]], rows[1:]
    elif archive.ref.dataset in _DEFAULT_COLUMNS:
        header, body = list(_DEFAULT_COLUMNS[archive.ref.dataset]), rows
    else:
        raise BronzeFormatError(f"{archive.ref}: CSV sin cabecera y sin columnas conocidas")
    width = len(header)
    for number, row in enumerate(body, start=1):
        if len(row) != width:
            raise BronzeFormatError(
                f"{archive.ref}: la fila {number} tiene {len(row)} columnas, se esperaban {width}"
            )
    return header, body


class ParquetBronzeStore:
    """Guarda archivos crudos como Parquet particionado. Cumple el puerto ``BronzeStore``."""

    def __init__(self, root: Path, *, source: str, clock: Clock) -> None:
        self._root = root
        self._source = source
        self._clock = clock

    def path_for(self, ref: ArchiveRef) -> Path:
        return (
            self._root
            / f"source={self._source}"
            / f"dataset={ref.dataset}"
            / f"market={ref.market}"
            / f"symbol={ref.symbol}"
            / f"interval={ref.interval or 'none'}"
            / f"year={ref.period.year:04d}"
            / f"month={ref.period.month:02d}"
            / f"{_archive_stem(ref)}.parquet"
        )

    def contains(self, ref: ArchiveRef, sha256: str) -> bool:
        path = self.path_for(ref)
        if not path.exists():
            return False
        metadata = pq.read_schema(path).metadata or {}
        return metadata.get(SHA256_METADATA_KEY) == sha256.encode()

    def write(self, archive: RawArchive) -> int:
        header, body = _read_csv(archive)
        columns: dict[str, pa.Array[Any]] = {
            name: pa.array([row[i] for row in body], type=pa.string())
            for i, name in enumerate(header)
        }
        count = len(body)
        columns["_source_file"] = pa.array([f"{_archive_stem(archive.ref)}.zip"] * count)
        columns["_source_sha256"] = pa.array([archive.sha256] * count)
        columns["_source_row"] = pa.array(range(1, count + 1), type=pa.int32())
        columns["_ingested_at"] = pa.array(
            [self._clock.now()] * count, type=pa.timestamp("us", tz="UTC")
        )
        table = pa.table(columns).replace_schema_metadata(
            {SHA256_METADATA_KEY: archive.sha256.encode()}
        )

        path = self.path_for(archive.ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atómica: un lector nunca ve un Parquet a medio escribir.
        tmp = path.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, path)
        return count

    def record_rejection(self, ref: ArchiveRef, reason: str) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": self._clock.now().isoformat(),
            "source": self._source,
            "archive": str(ref),
            "reason": reason,
        }
        with (self._root / REJECTIONS_FILE).open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
