"""Assets, checks y schedules del lakehouse (PQ-22).

``make orquestador`` abre la interfaz en http://127.0.0.1:3000.

- **bronze**: particionado por mes y símbolo. Cada partición ingesta de Data Vision las velas spot,
  las del perpetuo y el funding de ese mes (idempotente: lo ya descargado se salta).
- **silver**: reconstruye las tablas validadas de todos los símbolos. No se particiona por fecha:
  los checks de duplicados, huecos y outliers necesitan la historia completa de cada símbolo.
- **gold**: modelo en estrella para BI (PQ-46).
- **research**: assets **externos**, solo de linaje. No se pueden materializar desde aquí:
  cada ejecución de una evaluación suma ensayos a N (Deflated Sharpe, pre-registro §10). Se
  corren a mano con ``pq research …`` y su commit. Ningún schedule los toca.

Los checks de silver y gold son **bloqueantes**: si fallan, gold no se reconstruye en esa ejecución.
Los schedules arrancan detenidos; se activan desde la interfaz cuando el titular lo decide.
"""

# Sin `from __future__ import annotations`: Dagster inspecciona las anotaciones en ejecución.
import json
from datetime import date
from pathlib import Path

import polars as pl
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    ConfigurableResource,
    DefaultScheduleStatus,
    Definitions,
    Failure,
    MaterializeResult,
    MetadataValue,
    MonthlyPartitionsDefinition,
    MultiPartitionKey,
    MultiPartitionsDefinition,
    RunRequest,
    ScheduleEvaluationContext,
    StaticPartitionsDefinition,
    asset,
    asset_check,
    define_asset_job,
    schedule,
)

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.api.cli import SOURCE_NAME, http_client, last_complete_month
from prometheus_platform.data_platform.gold import (
    DATED_FACTS,
    GOLD_DIR,
    LAST_DAY,
    TABLES,
    GoldValidationError,
    build_gold,
    validate,
)
from prometheus_platform.data_platform.ingest import ingest, monthly_funding, monthly_klines
from prometheus_platform.data_platform.silver import (
    QualityReport,
    SilverValidationError,
    build_symbol,
    silver_path,
)
from prometheus_platform.domain.datasets import DatasetKind, Market
from prometheus_platform.ops.settings import load_settings

# Universo de las hipótesis pre-registradas del carry (H1: BTC, ETH; H2: SOL, BNB, XRP).
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
INTERVAL = "1h"
FIRST_MONTH = "2020-01-01"

MONTHS = MonthlyPartitionsDefinition(start_date=FIRST_MONTH)
BRONZE_PARTITIONS = MultiPartitionsDefinition(
    {"mes": MONTHS, "simbolo": StaticPartitionsDefinition(list(SYMBOLS))}
)


class Lakehouse(ConfigurableResource["Lakehouse"]):
    """Raíz del lakehouse. Por defecto, ``PQ_DATA_DIR`` (la misma configuración que la CLI)."""

    data_dir: str

    @property
    def root(self) -> Path:
        return Path(self.data_dir)


# --- bronze ---------------------------------------------------------------------------------


@asset(
    partitions_def=BRONZE_PARTITIONS,
    group_name="lakehouse",
    kinds={"parquet"},
    description="Archivos de Binance Data Vision tal como llegan, con su checksum (PQ-20).",
)
def bronze(context: AssetExecutionContext, lakehouse: Lakehouse) -> MaterializeResult[None]:
    key = context.partition_key
    if not isinstance(key, MultiPartitionKey):
        raise Failure(description=f"bronze espera una partición mes|símbolo, no {key!r}")
    month = date.fromisoformat(key.keys_by_dimension["mes"])
    symbol = key.keys_by_dimension["simbolo"]
    refs = [
        *monthly_klines(Market.SPOT, symbol, INTERVAL, month, month),
        *monthly_klines(Market.USDM, symbol, INTERVAL, month, month),
        *monthly_funding(symbol, month, month),
    ]
    # TODO(PQ-65): sumar el mes en curso desde la API REST de Binance cuando exista su adaptador.
    store = ParquetBronzeStore(lakehouse.root / "bronze", source=SOURCE_NAME, clock=SystemClock())
    with http_client() as client:
        report = ingest(refs, BinanceDataVisionSource(client), store)
    metadata = {
        "escritos": len(report.written),
        "ya_estaban": len(report.skipped),
        "no_publicados": len(report.missing),
        "rechazados": len(report.rejected),
        "fallidos": len(report.failed),
        "filas": report.rows_written,
    }
    if not report.ok:
        raise Failure(
            description=f"{symbol} {month:%Y-%m}: archivos rechazados o fallidos",
            metadata=metadata,
        )
    return MaterializeResult(metadata=metadata)


# --- silver ---------------------------------------------------------------------------------


@asset(
    deps=[bronze],
    group_name="lakehouse",
    kinds={"parquet"},
    description="Velas y funding tipados, validados y point-in-time de todos los símbolos (PQ-21).",
)
def silver(lakehouse: Lakehouse) -> MaterializeResult[None]:
    reports: list[QualityReport] = []
    for symbol in SYMBOLS:
        try:
            reports += build_symbol(lakehouse.root, symbol, INTERVAL)
        except SilverValidationError as exc:
            raise Failure(description=str(exc), metadata={"check": exc.check}) from exc
    return MaterializeResult(
        metadata={
            "tablas": len(reports),
            "filas": sum(r.rows for r in reports),
            "huecos": sum(r.gaps for r in reports),
            "outliers": sum(r.outliers for r in reports),
        }
    )


def _silver_tables(root: Path) -> list[tuple[str, Path, str]]:
    silver_root = root / "silver"
    tables = []
    for symbol in SYMBOLS:
        for market in (Market.SPOT, Market.USDM):
            path = silver_path(silver_root, DatasetKind.KLINES, symbol, market, INTERVAL)
            tables.append((f"klines/{market}/{symbol}", path, "open_time"))
        path = silver_path(silver_root, DatasetKind.FUNDING_RATE, symbol)
        tables.append((f"funding/{symbol}", path, "funding_time"))
    return tables


@asset_check(
    asset=silver, blocking=True, description="Cada tabla existe y su clave temporal no se repite"
)
def silver_tablas_y_claves(lakehouse: Lakehouse) -> AssetCheckResult:
    problems: dict[str, str] = {}
    for name, path, key in _silver_tables(lakehouse.root):
        if not path.is_file():
            problems[name] = "falta la tabla"
            continue
        times = pl.read_parquet(path, columns=[key])[key]
        if times.is_duplicated().any():
            problems[name] = f"{key} duplicado"
    return AssetCheckResult(
        passed=not problems,
        metadata={
            "problemas": MetadataValue.json(problems),
            "tablas": len(_silver_tables(lakehouse.root)),
        },
    )


@asset_check(asset=silver, description="Huecos detectados en silver (se informan, no se imputan)")
def silver_huecos(lakehouse: Lakehouse) -> AssetCheckResult:
    quality = lakehouse.root / "silver" / "_quality"
    gaps = {}
    for path in sorted(quality.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("gaps"):
            gaps[path.stem] = int(report["gaps"])
    return AssetCheckResult(
        passed=not gaps,
        severity=AssetCheckSeverity.WARN,
        metadata={"huecos_por_tabla": MetadataValue.json(gaps), "conocidos": "KE-007"},
    )


# --- research (externos: solo linaje) ---------------------------------------------------------

_RESEARCH_NOTE = (
    "Se genera a mano con `{cmd}`. No se materializa desde Dagster: cada ejecución suma "
    "ensayos a N (Deflated Sharpe, pre-registro §10)."
)
RESEARCH = [
    AssetSpec(
        AssetKey(["research", name]),
        deps=[silver],
        group_name="research",
        description=_RESEARCH_NOTE.format(cmd=cmd),
    )
    for name, cmd in (
        ("carry_H1", "uv run pq research carry --hypothesis H1"),
        ("carry_H2", "uv run pq research carry --hypothesis H2"),
        ("modelo_funding", "uv run pq research funding-model --figures <dir>"),
        ("simulacion", "uv run pq research simulate --figures <dir>"),
    )
]


# --- gold -----------------------------------------------------------------------------------


@asset(
    deps=[silver, *RESEARCH],
    group_name="lakehouse",
    kinds={"parquet", "duckdb"},
    description="Modelo en estrella para BI: 4 dimensiones y 9 hechos (PQ-46).",
)
def gold(lakehouse: Lakehouse) -> MaterializeResult[None]:
    try:
        report = build_gold(lakehouse.root)
    except GoldValidationError as exc:
        raise Failure(description=str(exc)) from exc
    return MaterializeResult(
        metadata={
            **{f"filas_{name}": rows for name, rows in report.rows.items()},
            "artefactos_faltantes": MetadataValue.json(report.missing),
        }
    )


def _read_gold(root: Path) -> dict[str, pl.DataFrame]:
    gold_dir = root / GOLD_DIR
    return {t.name: pl.read_parquet(gold_dir / f"{t.name}.parquet") for t in TABLES}


@asset_check(asset=gold, blocking=True, description=f"Ningún hecho con fecha pasa del {LAST_DAY}")
def gold_holdout_cerrado(lakehouse: Lakehouse) -> AssetCheckResult:
    tables = _read_gold(lakehouse.root)
    late = {
        t.name: tables[t.name].filter(pl.col("fecha") > LAST_DAY).height
        for t in DATED_FACTS
        if tables[t.name].filter(pl.col("fecha") > LAST_DAY).height
    }
    return AssetCheckResult(
        passed=not late, metadata={"filas_en_el_holdout": MetadataValue.json(late)}
    )


@asset_check(asset=gold, blocking=True, description="Esquema, claves e integridad referencial")
def gold_integridad(lakehouse: Lakehouse) -> AssetCheckResult:
    try:
        validate(_read_gold(lakehouse.root))
    except GoldValidationError as exc:
        return AssetCheckResult(passed=False, metadata={"error": str(exc)})
    return AssetCheckResult(passed=True)


# --- jobs y schedules (detenidos por defecto) -------------------------------------------------

bronze_mensual = define_asset_job("bronze_mensual", selection=AssetSelection.assets(bronze))
silver_y_gold = define_asset_job("silver_y_gold", selection=AssetSelection.assets(silver, gold))


@schedule(
    job=bronze_mensual,
    cron_schedule="0 6 * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.STOPPED,
)
def bronze_diario(context: ScheduleEvaluationContext) -> list[RunRequest]:
    """Cada día reintenta el último mes completo de cada símbolo: Data Vision publica tarde."""
    month = last_complete_month(context.scheduled_execution_time.date())
    return [
        RunRequest(
            run_key=f"{month:%Y-%m}-{symbol}-{context.scheduled_execution_time:%Y%m%d}",
            partition_key=MultiPartitionKey({"mes": month.isoformat(), "simbolo": symbol}),
        )
        for symbol in SYMBOLS
    ]


@schedule(
    job=silver_y_gold,
    cron_schedule="30 6 * * *",
    execution_timezone="UTC",
    default_status=DefaultScheduleStatus.STOPPED,
)
def silver_y_gold_diario() -> RunRequest:
    return RunRequest()


def build_definitions(data_dir: Path | None = None) -> Definitions:
    root = data_dir if data_dir is not None else load_settings().data_dir
    return Definitions(
        assets=[bronze, silver, gold, *RESEARCH],
        asset_checks=[silver_tablas_y_claves, silver_huecos, gold_holdout_cerrado, gold_integridad],
        jobs=[bronze_mensual, silver_y_gold],
        schedules=[bronze_diario, silver_y_gold_diario],
        resources={"lakehouse": Lakehouse(data_dir=str(root.resolve()))},
    )


defs = build_definitions()
