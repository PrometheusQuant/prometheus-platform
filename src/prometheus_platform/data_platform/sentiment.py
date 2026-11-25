"""Fear & Greed Index en el lakehouse (PQ-128): bronze con cada descarga, silver point-in-time.

- **Bronze:** una copia por descarga, con el JSON crudo, la URL y la hora
  (``bronze/source=alternative_me/dataset=fear_greed/fetched=<instante>.parquet``). Nunca se
  sobrescribe: así, de aquí en adelante, la serie es point-in-time por construcción y se puede
  comprobar si alguna vez se revisa un valor (riesgo declarado en el pre-registro de sentimiento).
- **Silver:** un valor por día (``date``, ``value``, ``classification``), con la **primera** vez que
  lo vimos (``first_fetched_at``) y su ``knowledge_time``: las 00:00 UTC del día más 1 h de margen,
  según la hora de publicación medida en PQ-103. Si dos descargas difieren en un día, se avisa en
  el informe de calidad y se conserva la primera.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE = "alternative_me"
DATASET = "fear_greed"
PUBLICATION_MARGIN = timedelta(hours=1)
SILVER_FILE = Path("sentiment") / "fear_greed.parquet"
_TS: pl.DataType = pl.Datetime("ms", "UTC")


class SentimentValidationError(ValueError):
    """El silver no pasa sus comprobaciones: no se escribe."""


def bronze_dir(bronze_root: Path) -> Path:
    return bronze_root / f"source={SOURCE}" / f"dataset={DATASET}"


def write_bronze(bronze_root: Path, raw: str, request: str, fetched_at: datetime) -> Path:
    """Guarda una descarga tal cual. Escritura atómica; una descarga = un archivo."""
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at tiene que tener zona horaria")
    stamp = fetched_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = bronze_dir(bronze_root) / f"fetched={stamp}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "raw": pa.array([raw], type=pa.string()),
            "request": pa.array([request], type=pa.string()),
            "fetched_at": pa.array([fetched_at.astimezone(UTC).isoformat()], type=pa.string()),
        }
    )
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    return path


@dataclass
class SentimentQuality:
    days: int = 0
    first: str = ""
    last: str = ""
    gaps: list[tuple[str, int]] = field(default_factory=list)  # (día anterior al hueco, días)
    revised: list[tuple[str, int, int]] = field(default_factory=list)  # (día, primero, después)
    downloads: int = 0


def _parse(raw: str, fetched_at: str) -> pl.DataFrame:
    rows = json.loads(raw)["data"]
    return pl.DataFrame(
        {
            "date": [datetime.fromtimestamp(int(r["timestamp"]), UTC).date() for r in rows],
            "value": [int(r["value"]) for r in rows],
            "classification": [str(r["value_classification"]) for r in rows],
            "fetched_at": [datetime.fromisoformat(fetched_at)] * len(rows),
        },
        schema={
            "date": pl.Date,
            "value": pl.Int64,
            "classification": pl.String,
            "fetched_at": _TS,
        },
    )


def build_silver(bronze_root: Path, silver_root: Path) -> SentimentQuality:
    """Reconstruye el silver desde todas las descargas guardadas."""
    files = sorted(bronze_dir(bronze_root).glob("fetched=*.parquet"))
    if not files:
        raise SentimentValidationError("No hay descargas del Fear & Greed en bronze")
    parts = []
    for file in files:
        table = pq.read_table(file).to_pylist()[0]
        parts.append(_parse(table["raw"], table["fetched_at"]))
    every = pl.concat(parts).sort("date", "fetched_at")
    first = every.group_by("date", maintain_order=True).first()
    quality = SentimentQuality(downloads=len(files))
    changed = every.join(first.select("date", pl.col("value").alias("v0")), on="date").filter(
        pl.col("value") != pl.col("v0")
    )
    quality.revised = [
        (str(d), int(a), int(b)) for d, b, a in changed.select("date", "value", "v0").iter_rows()
    ]
    silver = first.select(
        "date",
        "value",
        "classification",
        pl.col("fetched_at").alias("first_fetched_at"),
        (pl.col("date").cast(_TS) + pl.duration(hours=1)).alias("knowledge_time"),
    ).sort("date")
    if silver.filter((pl.col("value") < 0) | (pl.col("value") > 100)).height:
        raise SentimentValidationError("Valores fuera de 0-100")
    days = silver["date"]
    steps = days.diff().dt.total_days().fill_null(1)
    quality.days = silver.height
    quality.first, quality.last = str(days.min()), str(days.max())
    quality.gaps = [
        (str(d), int(s) - 1) for d, s in zip(days.shift(1), steps, strict=True) if s > 1
    ]
    path = silver_root / SILVER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    silver.write_parquet(tmp)
    os.replace(tmp, path)
    return quality


def read_silver(silver_root: Path) -> pl.DataFrame:
    return pl.read_parquet(silver_root / SILVER_FILE)
