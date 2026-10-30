"""Capa silver: datos tipados, validados y *point-in-time* a partir de bronze.

Aplica los hallazgos de la auditoría de Data Vision (PQ-19), cada uno con su test:

1. Spot pasó de milisegundos a microsegundos en 2025-01: se normaliza por número de dígitos.
2. Los CSV de futuros tenían o no cabecera: bronze ya resolvió los nombres; aquí se tipan.
3. El intervalo de funding varía: se anualiza con el ``funding_interval_hours`` de cada fila.
4. Hay filas duplicadas: se eliminan las idénticas y se falla si dos filas con la misma clave
   difieren.
5. Hay huecos: se informan y **no se imputan**. Los outliers reales tampoco se eliminan: se marcan.

Cada fila lleva ``event_time`` (cuándo ocurrió) y ``knowledge_time`` (cuándo se pudo conocer).
Los joins de research se hacen *as-of* sobre ``knowledge_time`` (``asof_join``).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandera.polars as pa
import polars as pl
from pandera.engines.polars_engine import DateTime

from prometheus_platform.domain.datasets import DatasetKind, Market

HOUR_MS = 3_600_000
VALID_FUNDING_INTERVALS = (1, 2, 4, 8)
MAX_ABS_FUNDING_RATE = 0.05  # 5 % por liquidación: muy por encima de cualquier tope observado
OUTLIER_SIGMAS = 10.0
OUTLIER_WINDOW = timedelta(days=30)
_INTERVAL = re.compile(r"^(?P<n>[1-9][0-9]*)(?P<unit>[mhdw])$")
_UNIT_MS = {"m": 60_000, "h": HOUR_MS, "d": 24 * HOUR_MS, "w": 7 * 24 * HOUR_MS}
PRICE_COLUMNS = ("open", "high", "low", "close")
VOLUME_COLUMNS = ("volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume")


class SilverValidationError(ValueError):
    """Los datos violan un check de silver: la construcción no debe continuar."""

    def __init__(self, table: str, check: str, detail: str) -> None:
        super().__init__(f"{table}: falló el check '{check}': {detail}")
        self.table = table
        self.check = check


@dataclass
class QualityReport:
    """Informe de calidad de una tabla silver (FR-007, FR-011)."""

    table: str
    rows: int = 0
    duplicates_removed: int = 0
    gaps: int = 0
    missing_periods: int = 0
    largest_gap_hours: float = 0.0
    gap_list: list[dict[str, str]] = field(default_factory=list)
    outliers: int = 0
    first: str | None = None
    last: str | None = None
    checks: list[str] = field(default_factory=list)
    describe: dict[str, dict[str, float | None]] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def interval_ms(interval: str) -> int:
    match = _INTERVAL.match(interval)
    if not match:
        raise ValueError(f"Intervalo no soportado: {interval!r}")
    return int(match["n"]) * _UNIT_MS[match["unit"]]


def to_epoch_ms(column: str) -> pl.Expr:
    """Hallazgo 1: un epoch de 16 dígitos está en µs y se lleva a ms."""
    raw = pl.col(column).cast(pl.Int64)
    return pl.when(raw >= 10**15).then(raw // 1000).otherwise(raw)


def _utc(ms: pl.Expr) -> pl.Expr:
    return pl.from_epoch(ms, time_unit="ms").dt.cast_time_unit("ms").dt.replace_time_zone("UTC")


# --- Esquemas declarativos (FR-009) ------------------------------------------------------


class KlineSchema(pa.DataFrameModel):
    open_time: DateTime = pa.Field(
        unique=True, dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"}
    )
    close_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    open: float = pa.Field(gt=0)
    high: float = pa.Field(gt=0)
    low: float = pa.Field(gt=0)
    close: float = pa.Field(gt=0)
    volume: float = pa.Field(ge=0)
    quote_volume: float = pa.Field(ge=0)
    trades: int = pa.Field(ge=0)
    taker_buy_volume: float = pa.Field(ge=0)
    taker_buy_quote_volume: float = pa.Field(ge=0)
    event_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    knowledge_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    is_outlier: bool
    source_file: str

    class Config:
        strict = False
        coerce = False


class FundingSchema(pa.DataFrameModel):
    funding_time: DateTime = pa.Field(
        unique=True, dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"}
    )
    calc_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    funding_interval_hours: int = pa.Field(isin=list(VALID_FUNDING_INTERVALS))
    funding_rate: float = pa.Field(ge=-MAX_ABS_FUNDING_RATE, le=MAX_ABS_FUNDING_RATE)
    funding_rate_annualized: float
    event_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    knowledge_time: DateTime = pa.Field(dtype_kwargs={"time_unit": "ms", "time_zone": "UTC"})
    source_file: str

    class Config:
        strict = False
        coerce = False


def _validate_schema(table: str, schema: type[pa.DataFrameModel], frame: pl.DataFrame) -> None:
    try:
        schema.validate(frame, lazy=True)
    except (pa.errors.SchemaError, pa.errors.SchemaErrors) as exc:
        raise SilverValidationError(table, f"esquema {schema.__name__}", str(exc)[:2000]) from exc


def _require(table: str, check: str, failing: pl.DataFrame, report: QualityReport) -> None:
    if failing.height:
        raise SilverValidationError(
            table, check, f"{failing.height} filas, p. ej. {failing.row(0)}"
        )
    report.checks.append(check)


# --- Duplicados, huecos y estadística -----------------------------------------------------


def _deduplicate(
    table: str,
    frame: pl.DataFrame,
    key: str,
    report: QualityReport,
    ignore: tuple[str, ...] = ("source_file",),
) -> pl.DataFrame:
    """Hallazgo 4: duplicados idénticos se eliminan; con valores distintos, se falla.

    ``ignore`` son columnas que no cuentan para decidir si dos filas son iguales (el archivo de
    origen o el ``calc_time`` con jitter).
    """
    values = [c for c in frame.columns if c not in ignore]
    unique = frame.unique(subset=values, keep="first", maintain_order=True)
    conflicting = unique.filter(pl.col(key).is_duplicated())
    if conflicting.height:
        raise SilverValidationError(
            table, "duplicados en conflicto", f"{conflicting.height} filas con la misma {key}"
        )
    report.duplicates_removed = frame.height - unique.height
    report.checks.append("sin duplicados en conflicto")
    return unique.sort(key)


def _gaps(frame: pl.DataFrame, column: str, step: pl.Expr, report: QualityReport) -> None:
    """Hallazgo 5: los huecos se informan, nunca se rellenan.

    ``step`` es el paso esperado entre una fila y la siguiente, evaluado en la fila anterior.
    """
    diffs = (
        frame.with_columns(step.alias("_step"))
        .select(
            pl.col(column).shift(1).alias("from"),
            pl.col(column).alias("to"),
            (pl.col(column) - pl.col(column).shift(1)).alias("delta"),
            pl.col("_step").shift(1).alias("step"),
        )
        .filter(pl.col("delta") > pl.col("step"))
    )
    report.gaps = diffs.height
    if diffs.height:
        missing = diffs.select(
            (
                pl.col("delta").dt.total_milliseconds() // pl.col("step").dt.total_milliseconds()
                - 1
            ).sum()
        ).item()
        report.missing_periods = int(missing)
        report.largest_gap_hours = float(diffs["delta"].dt.total_milliseconds().max()) / HOUR_MS  # type: ignore[arg-type]
        report.gap_list = [
            {"from": str(r["from"]), "to": str(r["to"])}
            for r in diffs.head(50).iter_rows(named=True)
        ]


def describe(frame: pl.DataFrame, columns: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    """Estadística descriptiva por variable (capítulo 4.2)."""
    stats: dict[str, dict[str, float | None]] = {}
    for name in columns:
        s = frame[name].cast(pl.Float64)
        stats[name] = {
            "n": float(s.len() - s.null_count()),
            "mean": _num(s.mean()),
            "std": _num(s.std()),
            "min": _num(s.min()),
            "p25": _num(s.quantile(0.25)),
            "median": _num(s.median()),
            "p75": _num(s.quantile(0.75)),
            "max": _num(s.max()),
        }
    return stats


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


# --- Construcción -----------------------------------------------------------------------


def build_klines(
    bronze: pl.DataFrame, market: Market, symbol: str, interval: str
) -> tuple[pl.DataFrame, QualityReport]:
    """Velas bronze (texto) → silver tipado y validado."""
    table = f"klines/{market}/{interval}/{symbol}"
    if bronze.is_empty():
        raise SilverValidationError(table, "hay datos", "bronze no tiene filas para este símbolo")
    step = interval_ms(interval)
    report = QualityReport(table=table)

    typed = bronze.select(
        to_epoch_ms("open_time").alias("open_ms"),
        to_epoch_ms("close_time").alias("close_ms"),
        *[pl.col(c).cast(pl.Float64) for c in PRICE_COLUMNS],
        *[pl.col(c).cast(pl.Float64) for c in VOLUME_COLUMNS],
        pl.col("count").cast(pl.Int64).alias("trades"),
        pl.col("_source_file").alias("source_file"),
    )
    typed = _deduplicate(table, typed, "open_ms", report)
    _require(
        table,
        "timestamps alineados al intervalo",
        typed.filter(pl.col("open_ms") % step != 0),
        report,
    )

    frame = typed.with_columns(
        _utc(pl.col("open_ms")).alias("open_time"),
        _utc(pl.col("close_ms")).alias("close_time"),
    ).with_columns(
        pl.col("open_time").alias("event_time"),
        # La vela se conoce cuando cierra: apertura + intervalo (FR-003).
        (pl.col("open_time") + pl.duration(milliseconds=step))
        .dt.cast_time_unit("ms")
        .alias("knowledge_time"),
    )

    # Outliers (FR-008): se marcan con la volatilidad *previa*, sin mirar el futuro.
    window = max(int(OUTLIER_WINDOW.total_seconds() * 1000 // step), 2)
    log_return = (pl.col("close") / pl.col("close").shift(1)).log()
    frame = frame.with_columns(
        (
            log_return.abs()
            > OUTLIER_SIGMAS
            * log_return.rolling_std(window_size=window, min_samples=window // 4).shift(1)
        )
        .fill_null(False)
        .alias("is_outlier")
    ).drop("open_ms", "close_ms")

    _require(
        table,
        "OHLC coherente",
        frame.filter(
            (pl.col("high") < pl.max_horizontal("open", "close"))
            | (pl.col("low") > pl.min_horizontal("open", "close"))
        ),
        report,
    )
    _require(
        table,
        "knowledge_time posterior a event_time",
        frame.filter(pl.col("knowledge_time") <= pl.col("event_time")),
        report,
    )
    _validate_schema(table, KlineSchema, frame)
    report.checks.append("esquema KlineSchema")

    _gaps(frame, "open_time", pl.lit(timedelta(milliseconds=step)), report)
    report.rows = frame.height
    report.outliers = int(frame["is_outlier"].sum())
    report.first, report.last = str(frame["open_time"].min()), str(frame["open_time"].max())
    report.describe = describe(frame, (*PRICE_COLUMNS, "volume", "trades"))
    return frame, report


def build_funding(bronze: pl.DataFrame, symbol: str) -> tuple[pl.DataFrame, QualityReport]:
    """Funding bronze (texto) → silver tipado, con la hora de liquidación y la tasa anualizada."""
    table = f"funding/{symbol}"
    if bronze.is_empty():
        raise SilverValidationError(table, "hay datos", "bronze no tiene filas para este símbolo")
    report = QualityReport(table=table)

    typed = bronze.select(
        to_epoch_ms("calc_time").alias("calc_ms"),
        pl.col("funding_interval_hours").cast(pl.Int64),
        pl.col("last_funding_rate").cast(pl.Float64).alias("funding_rate"),
        pl.col("_source_file").alias("source_file"),
    ).with_columns(
        # calc_time trae jitter de milisegundos (16:00:00.002): se redondea a la hora.
        (((pl.col("calc_ms") + HOUR_MS // 2) // HOUR_MS) * HOUR_MS).alias("funding_ms")
    )
    typed = _deduplicate(table, typed, "funding_ms", report, ignore=("source_file", "calc_ms"))

    frame = (
        typed.with_columns(
            _utc(pl.col("funding_ms")).alias("funding_time"),
            _utc(pl.col("calc_ms")).alias("calc_time"),
            # Hallazgo 3: anualizar con el intervalo real de cada liquidación.
            (pl.col("funding_rate") * 8760 / pl.col("funding_interval_hours")).alias(
                "funding_rate_annualized"
            ),
        )
        .with_columns(
            pl.col("funding_time").alias("event_time"),
            pl.col("funding_time").alias("knowledge_time"),
        )
        .drop("funding_ms", "calc_ms")
    )

    _validate_schema(table, FundingSchema, frame)
    report.checks.append("esquema FundingSchema")
    _gaps(
        frame,
        "funding_time",
        pl.duration(hours=pl.col("funding_interval_hours")),
        report,
    )
    report.rows = frame.height
    report.first, report.last = str(frame["funding_time"].min()), str(frame["funding_time"].max())
    report.describe = describe(
        frame, ("funding_rate", "funding_rate_annualized", "funding_interval_hours")
    )
    return frame, report


def asof_join(
    left: pl.DataFrame, right: pl.DataFrame, *, on: str, suffix: str = "_right"
) -> pl.DataFrame:
    """Une a cada fila de ``left`` (en el instante ``on``) la última fila de ``right`` ya conocida.

    Usa ``knowledge_time`` de ``right``: una fila que se conoce después de ``on`` nunca entra
    (FR-010). Ambos lados se ordenan por tiempo.
    """
    return left.sort(on).join_asof(
        right.sort("knowledge_time"),
        left_on=on,
        right_on="knowledge_time",
        strategy="backward",
        suffix=suffix,
    )


# --- E/S --------------------------------------------------------------------------------


def bronze_files(
    bronze_root: Path, dataset: DatasetKind, market: Market, symbol: str, interval: str | None
) -> list[Path]:
    base = (
        bronze_root
        / "source=binance_data_vision"
        / f"dataset={dataset}"
        / f"market={market}"
        / f"symbol={symbol}"
        / f"interval={interval or 'none'}"
    )
    return sorted(base.rglob("*.parquet"))


def read_bronze(files: list[Path]) -> pl.DataFrame:
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")


def silver_path(
    silver_root: Path,
    dataset: DatasetKind,
    symbol: str,
    market: Market | None = None,
    interval: str | None = None,
) -> Path:
    if dataset is DatasetKind.KLINES:
        return (
            silver_root
            / "klines"
            / f"market={market}"
            / f"interval={interval}"
            / f"{symbol}.parquet"
        )
    return silver_root / "funding" / f"{symbol}.parquet"


def write_silver(frame: pl.DataFrame, report: QualityReport, path: Path, quality_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    frame.write_parquet(tmp, compression="zstd")
    tmp.replace(path)
    quality_dir.mkdir(parents=True, exist_ok=True)
    (quality_dir / f"{report.table.replace('/', '-')}.json").write_text(report.to_json())
