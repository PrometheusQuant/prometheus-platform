"""Lakehouse de Polymarket: bronze con linaje y silver point-in-time (PQ-92).

**Bronze** guarda cada respuesta de la API tal cual llegó: el JSON crudo de cada registro, la URL
pedida y el instante de la descarga (``fetched_at``). Se particiona por el mes del ``endDate`` del
mercado::

    bronze/source=polymarket/dataset=<markets|prices|trades>/[fidelity=<f>/]year=<YYYY>/month=<MM>/<dataset>.parquet

**Silver** tipa y valida. Reglas que vienen del spike PQ-78 y del pre-registro PQ-87:

- Cada precio lleva ``knowledge_time`` = el instante del punto: se conoce cuando ocurre.
- La resolución solo se conoce **en** ``closedTime`` (``resolution_known_at``). Si falta, queda
  nula y el mercado no tiene resolución utilizable. ``resolution_asof`` aplica esa regla.
  ``closedTime`` es el fin de la resolución de UMA: en 45 mercados de marzo de 2024 con
  ``umaEndDate``, los dos coinciden al segundo (comprobado el 2026-11-24).
- El pago de cada resultado es el ``outcomePrices`` publicado, sin redondear: 1/0 en el caso normal,
  0,5 o decimales en las resoluciones parciales y en las de la época del AMM.
- ``["0", "0"]`` no es un pago definido: se marca con ``excluded_reason``.
- Un precio exactamente 0,5 que lleva 24 h o más sin moverse es un relleno con el libro vacío, no un
  precio (pre-registro §4): ``is_placeholder`` y ``price`` nulo.
- Deportes = etiqueta ``Sports`` del evento o ``feeType`` que empieza por ``sports``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from prometheus_platform.data_platform.silver import (
    QualityReport,
    SilverValidationError,
    write_silver,
)
from prometheus_platform.domain.ports import Clock, PredictionMarketSource
from prometheus_platform.domain.prediction_markets import PredictionMarketError, RawPage
from prometheus_platform.ops.logging import get_logger

SOURCE = "polymarket"
DAILY = 1440
MIN_MARKETS = 5000  # criterio de PQ-92 (y del capítulo 1.5): al menos 5.000 registros
PLACEHOLDER_PRICE = 0.5
PLACEHOLDER_AFTER = timedelta(hours=24)
_TS: pl.DataType = pl.Datetime("ms", "UTC")


# --- Bronze -----------------------------------------------------------------------------------


@dataclass
class PolymarketIngestReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    rows_written: int = 0

    @property
    def ok(self) -> bool:
        return not self.failed


def month_window(month: date) -> tuple[datetime, datetime]:
    """Primer y último segundo del mes. Gamma incluye los dos extremos de la ventana."""
    start = datetime(month.year, month.month, 1, tzinfo=UTC)
    nxt = datetime(month.year + (month.month == 12), month.month % 12 + 1, 1, tzinfo=UTC)
    return start, nxt - timedelta(seconds=1)


def bronze_path(bronze_root: Path, dataset: str, month: date, fidelity: int | None = None) -> Path:
    path = bronze_root / f"source={SOURCE}" / f"dataset={dataset}"
    if fidelity is not None:
        path /= f"fidelity={fidelity}"
    return path / f"year={month.year}" / f"month={month.month:02d}" / f"{dataset}.parquet"


def _write(path: Path, columns: dict[str, list[str | None]]) -> int:
    """Todo como texto, como en el resto de bronze. Escritura atómica."""
    table = pa.table({k: pa.array(v, type=pa.string()) for k, v in columns.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)
    return table.num_rows


def _fetch_all[T](
    jobs: list[T],
    fetch: Callable[[T], list[RawPage]],
    clock: Clock,
    workers: int,
) -> list[tuple[T, list[RawPage] | None, str]]:
    """Descarga cada trabajo, en paralelo si ``workers`` > 1, conservando el orden.

    Devuelve ``(trabajo, páginas o None si falló, fetched_at)``. Un fallo no detiene a los demás.
    """
    log = get_logger(component="polymarket_ingest")

    def one(job: T) -> tuple[T, list[RawPage] | None, str]:
        try:
            pages = fetch(job)
        except PredictionMarketError as exc:
            log.warning("polymarket_fetch_failed", job=str(job)[:40], error=str(exc))
            return job, None, ""
        return job, pages, clock.now().isoformat()

    if workers <= 1:
        return [one(job) for job in jobs]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))


def ingest_markets(  # noqa: PLR0913 - parámetros de la ingesta, todos con nombre
    source: PredictionMarketSource,
    bronze_root: Path,
    months: Iterable[date],
    *,
    min_volume: float,
    clock: Clock,
    refresh_since: date | None = None,
) -> PolymarketIngestReport:
    """Catálogo de mercados cerrados, un archivo por mes de ``endDate``.

    Un mes ya ingerido se salta, salvo que sea igual o posterior a ``refresh_since``: los
    mercados de un mes reciente pueden cerrarse después de la primera descarga.
    """
    log = get_logger(component="polymarket_ingest")
    report = PolymarketIngestReport()
    for month in months:
        path = bronze_path(bronze_root, "markets", month)
        label = f"markets/{month:%Y-%m}"
        if path.exists() and (refresh_since is None or month < refresh_since):
            report.skipped.append(label)
            continue
        start, end = month_window(month)
        try:
            pages = source.closed_markets(start, end, min_volume)
        except PredictionMarketError as exc:
            report.failed.append(label)
            log.warning(
                "polymarket_month_failed", dataset="markets", month=f"{month:%Y-%m}", error=str(exc)
            )
            continue
        fetched = clock.now().isoformat()
        cols: dict[str, list[str | None]] = {
            k: [] for k in ("id", "condition_id", "raw", "request", "fetched_at")
        }
        for page in pages:
            for row in page.rows:
                cols["id"].append(str(row.get("id")))
                cols["condition_id"].append(row.get("conditionId"))
                cols["raw"].append(json.dumps(row, ensure_ascii=False, sort_keys=True))
                cols["request"].append(page.request)
                cols["fetched_at"].append(fetched)
        report.rows_written += _write(path, cols)
        report.written.append(label)
        log.info(
            "polymarket_month_written",
            dataset="markets",
            month=f"{month:%Y-%m}",
            rows=len(cols["id"]),
        )
    return report


def ingest_prices(  # noqa: PLR0913 - parámetros de la ingesta, todos con nombre
    source: PredictionMarketSource,
    bronze_root: Path,
    markets: pl.DataFrame,
    *,
    clock: Clock,
    fidelity: int = DAILY,
    force: bool = False,
    workers: int = 1,
) -> PolymarketIngestReport:
    """Historial de precios de **cada resultado** de los mercados de silver, por mes de cierre.

    Un mes solo se escribe si todos sus tokens respondieron: si alguno falla, el mes queda como
    fallido y se reintenta en la próxima ejecución.
    """
    log = get_logger(component="polymarket_ingest")
    report = PolymarketIngestReport()
    usable = markets.filter(pl.col("end_date").is_not_null())
    for (month_start,), group in usable.group_by(
        pl.col("end_date").dt.truncate("1mo").alias("m"), maintain_order=True
    ):
        month = month_start.date() if isinstance(month_start, datetime) else month_start
        path = bronze_path(bronze_root, "prices", month, fidelity)
        label = f"prices/{fidelity}/{month:%Y-%m}"
        if path.exists() and not force:
            report.skipped.append(label)
            continue
        cols: dict[str, list[str | None]] = {
            k: []
            for k in (
                "token_id",
                "condition_id",
                "outcome_index",
                "t",
                "p",
                "request",
                "fetched_at",
            )
        }
        jobs = [
            (token, market["condition_id"], index)
            for market in group.iter_rows(named=True)
            for index, token in enumerate(market["token_ids"] or [])
        ]
        results = _fetch_all(
            jobs, lambda job: source.price_history(job[0], fidelity), clock, workers
        )
        failed = any(pages is None for _, pages, _ in results)
        for (token, condition, index), pages, fetched in results:
            for page in pages or []:
                for point in page.rows:
                    cols["token_id"].append(token)
                    cols["condition_id"].append(condition)
                    cols["outcome_index"].append(str(index))
                    cols["t"].append(str(point.get("t")))
                    cols["p"].append(str(point.get("p")))
                    cols["request"].append(page.request)
                    cols["fetched_at"].append(fetched)
        with_data = sum(1 for _, pages, _ in results if pages and any(p.rows for p in pages))
        log.info(
            "polymarket_outcomes",
            month=f"{month:%Y-%m}",
            outcomes=len(jobs),
            with_data=with_data,
        )
        if failed:
            report.failed.append(label)
            continue
        report.rows_written += _write(path, cols)
        report.written.append(label)
        log.info(
            "polymarket_month_written",
            dataset="prices",
            month=f"{month:%Y-%m}",
            rows=len(cols["t"]),
        )
    return report


def ingest_trades(  # noqa: PLR0913 - parámetros de la ingesta, todos con nombre
    source: PredictionMarketSource,
    bronze_root: Path,
    markets: pl.DataFrame,
    *,
    clock: Clock,
    max_pages: int,
    force: bool = False,
    workers: int = 1,
) -> PolymarketIngestReport:
    """Operaciones de cada mercado, por mes de cierre (Data API v2).

    La API solo cubre unos tres años móviles (spike PQ-78 §3): lo que no se guarda ahora se pierde.
    ``max_pages`` acota los mercados muy líquidos (1.000 operaciones por página).
    """
    log = get_logger(component="polymarket_ingest")
    report = PolymarketIngestReport()
    usable = markets.filter(pl.col("end_date").is_not_null())
    for (month_start,), group in usable.group_by(
        pl.col("end_date").dt.truncate("1mo").alias("m"), maintain_order=True
    ):
        month = month_start.date() if isinstance(month_start, datetime) else month_start
        path = bronze_path(bronze_root, "trades", month)
        label = f"trades/{month:%Y-%m}"
        if path.exists() and not force:
            report.skipped.append(label)
            continue
        cols: dict[str, list[str | None]] = {
            k: [] for k in ("condition_id", "raw", "request", "fetched_at")
        }
        conditions: list[str] = group["condition_id"].to_list()
        results = _fetch_all(conditions, lambda c: source.trades(c, max_pages), clock, workers)
        failed = any(pages is None for _, pages, _ in results)
        for condition, pages, fetched in results:
            for page in pages or []:
                for row in page.rows:
                    cols["condition_id"].append(condition)
                    cols["raw"].append(json.dumps(row, ensure_ascii=False, sort_keys=True))
                    cols["request"].append(page.request)
                    cols["fetched_at"].append(fetched)
        if failed:
            report.failed.append(label)
            continue
        report.rows_written += _write(path, cols)
        report.written.append(label)
        log.info(
            "polymarket_month_written",
            dataset="trades",
            month=f"{month:%Y-%m}",
            rows=len(cols["raw"]),
        )
    return report


def read_bronze(bronze_root: Path, dataset: str, fidelity: int | None = None) -> pl.DataFrame:
    base = bronze_root / f"source={SOURCE}" / f"dataset={dataset}"
    if fidelity is not None:
        base /= f"fidelity={fidelity}"
    files = sorted(base.glob("year=*/month=*/*.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(f) for f in files], how="vertical")


# --- Silver -----------------------------------------------------------------------------------


def _utc(value: Any) -> datetime | None:
    """Fechas de Gamma: ``2024-11-05T12:00:00Z``, ``2024-11-06 15:17:41+00`` o ausentes."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T").replace("Z", "+00:00")
    if text.endswith(("+00", "-00")):
        text += ":00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_sports(tags: list[str], fee_type: str | None) -> bool:
    """Regla 3 del pre-registro PQ-87."""
    return any(t.lower() == "sports" for t in tags) or (fee_type or "").lower().startswith("sports")


def _market_record(raw: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    tags = [
        str(t.get("label")) for t in raw.get("tags") or [] if isinstance(t, dict) and t.get("label")
    ]
    events = raw.get("events") or []
    event = events[0] if events and isinstance(events[0], dict) else {}
    payouts = [_float(p) for p in _json_list(raw.get("outcomePrices"))]
    closed = _utc(raw.get("closedTime"))
    excluded = None
    if payouts and all(p == 0 for p in payouts):
        excluded = "pago sin definir (todos 0)"
    elif not payouts or any(p is None for p in payouts):
        excluded = "sin outcomePrices"
    elif closed is None:
        excluded = "sin closedTime"
    return {
        "market_id": str(raw.get("id")),
        "condition_id": raw.get("conditionId"),
        "event_id": str(event.get("id")) if event.get("id") is not None else None,
        "question": raw.get("question"),
        "slug": raw.get("slug"),
        "tags": tags,
        "fee_type": raw.get("feeType"),
        "is_sports": is_sports(tags, raw.get("feeType")),
        "neg_risk": bool(raw.get("negRisk")),
        "outcomes": [str(o) for o in _json_list(raw.get("outcomes"))],
        "token_ids": [str(t) for t in _json_list(raw.get("clobTokenIds"))],
        "payouts": payouts,
        "volume_usd": _float(raw.get("volumeNum")),
        "created_at": _utc(raw.get("createdAt")),
        "start_date": _utc(raw.get("startDate")),
        "end_date": _utc(raw.get("endDate")),
        "closed_time": closed,
        "uma_resolution_status": raw.get("umaResolutionStatus"),
        "resolution_known_at": closed,
        "excluded_reason": excluded,
        "fetched_at": fetched_at,
    }


_MARKET_SCHEMA: dict[str, pl.DataType] = {
    "market_id": pl.String(),
    "condition_id": pl.String(),
    "event_id": pl.String(),
    "question": pl.String(),
    "slug": pl.String(),
    "tags": pl.List(pl.String()),
    "fee_type": pl.String(),
    "is_sports": pl.Boolean(),
    "neg_risk": pl.Boolean(),
    "outcomes": pl.List(pl.String()),
    "token_ids": pl.List(pl.String()),
    "payouts": pl.List(pl.Float64()),
    "volume_usd": pl.Float64(),
    "created_at": _TS,
    "start_date": _TS,
    "end_date": _TS,
    "closed_time": _TS,
    "uma_resolution_status": pl.String(),
    "resolution_known_at": _TS,
    "excluded_reason": pl.String(),
    "fetched_at": pl.String(),
}


def build_markets(bronze: pl.DataFrame) -> tuple[pl.DataFrame, QualityReport]:
    """Catálogo tipado. Un mercado descargado varias veces se queda con la última descarga."""
    table = "polymarket/markets"
    report = QualityReport(table=table)
    if bronze.is_empty():
        raise SilverValidationError(table, "bronze vacío", "no hay mercados ingeridos")
    records = [
        _market_record(json.loads(raw), fetched)
        for raw, fetched in bronze.select("raw", "fetched_at").iter_rows()
    ]
    frame = pl.DataFrame(records, schema=_MARKET_SCHEMA)
    frame = frame.sort("fetched_at").unique(
        subset=["condition_id"], keep="last", maintain_order=True
    )
    report.duplicates_removed = len(records) - frame.height
    report.checks.append("un registro por condition_id (la descarga más reciente)")

    missing_id = frame.filter(pl.col("condition_id").is_null())
    if missing_id.height:
        raise SilverValidationError(
            table, "condition_id presente", f"{missing_id.height} mercados sin él"
        )
    report.checks.append("condition_id presente")
    bad = frame.filter(
        pl.col("payouts").list.eval((pl.element() < 0) | (pl.element() > 1)).list.any()
    )
    if bad.height:
        raise SilverValidationError(
            table, "pagos en [0, 1]", f"{bad.height} mercados, p. ej. {bad.row(0)[0]}"
        )
    report.checks.append("pagos en [0, 1]")
    mismatch = frame.filter(pl.col("token_ids").list.len() != pl.col("outcomes").list.len()).height
    report.checks.append(f"tokens distintos del número de resultados: {mismatch}")

    report.rows = frame.height
    binary = frame.filter(pl.col("outcomes").list.len() == 2).height
    usable = frame.filter(pl.col("excluded_reason").is_null()).height
    report.checks += [
        f"binarios: {binary}",
        f"utilizables (con pago y closedTime): {usable}",
        f"al menos {MIN_MARKETS} mercados: {'sí' if frame.height >= MIN_MARKETS else 'NO'}",
    ]
    for reason, count in (
        frame.group_by("excluded_reason")
        .len()
        .drop_nulls("excluded_reason")
        .sort("excluded_reason")
        .iter_rows()
    ):
        report.checks.append(f"excluidos por «{reason}»: {count}")
    report.checks.append(f"deportes: {frame.filter(pl.col('is_sports')).height}")
    if frame.height:
        report.first = str(frame["end_date"].min())
        report.last = str(frame["end_date"].max())
    return frame.sort("end_date", "market_id"), report


def build_prices(bronze: pl.DataFrame, markets: pl.DataFrame) -> tuple[pl.DataFrame, QualityReport]:
    """Precios por resultado con ``knowledge_time`` y la marca de relleno del pre-registro."""
    table = "polymarket/prices"
    report = QualityReport(table=table)
    if bronze.is_empty():
        raise SilverValidationError(table, "bronze vacío", "no hay precios ingeridos")
    frame = bronze.select(
        pl.col("token_id"),
        pl.col("condition_id"),
        pl.col("outcome_index").cast(pl.Int8),
        (pl.col("t").cast(pl.Int64) * 1000).cast(_TS).alias("event_time"),
        pl.col("p").cast(pl.Float64).alias("raw_price"),
        pl.col("request").alias("source_request"),
    )
    before = frame.height
    frame = frame.unique(
        subset=["token_id", "event_time", "raw_price"], keep="first", maintain_order=True
    )
    conflicting = frame.filter(pl.struct("token_id", "event_time").is_duplicated())
    if conflicting.height:
        raise SilverValidationError(
            table,
            "duplicados en conflicto",
            f"{conflicting.height} filas con el mismo token e instante",
        )
    report.duplicates_removed = before - frame.height
    report.checks.append("sin duplicados en conflicto")
    out_of_range = frame.filter((pl.col("raw_price") < 0) | (pl.col("raw_price") > 1))
    if out_of_range.height:
        raise SilverValidationError(table, "precios en [0, 1]", f"{out_of_range.height} filas")
    report.checks.append("precios en [0, 1]")

    frame = frame.sort("token_id", "event_time")
    is_half = pl.col("raw_price") == PLACEHOLDER_PRICE
    run = (is_half != is_half.shift(1).over("token_id")).fill_null(True).cum_sum().over("token_id")
    frame = frame.with_columns(run.alias("_run")).with_columns(
        pl.col("event_time").min().over("token_id", "_run").alias("_run_start")
    )
    placeholder = is_half & ((pl.col("event_time") - pl.col("_run_start")) >= PLACEHOLDER_AFTER)
    frame = (
        frame.with_columns(placeholder.alias("is_placeholder"))
        .with_columns(
            pl.when(pl.col("is_placeholder"))
            .then(None)
            .otherwise(pl.col("raw_price"))
            .alias("price"),
            pl.col("event_time").alias("knowledge_time"),
        )
        .drop("_run", "_run_start")
    )

    closes = markets.select("condition_id", "closed_time")
    frame = (
        frame.join(closes, on="condition_id", how="left")
        .with_columns(
            (
                pl.col("closed_time").is_not_null() & (pl.col("event_time") > pl.col("closed_time"))
            ).alias("after_close")
        )
        .drop("closed_time")
    )
    unknown = frame.filter(~pl.col("condition_id").is_in(markets["condition_id"].implode())).height
    expected = markets.select(pl.col("token_ids").explode().drop_nulls())["token_ids"]
    without_history = expected.filter(~expected.is_in(frame["token_id"].implode())).len()
    seconds = (
        frame["event_time"].dt.hour().cast(pl.Int32) * 3600
        + frame["event_time"].dt.minute().cast(pl.Int32) * 60
        + frame["event_time"].dt.second().cast(pl.Int32)
    )
    off_midnight = int((seconds > 60).sum())  # los diarios llegan a las 00:00:0x
    report.rows = frame.height
    report.checks += [
        f"precios de relleno (0,5 sin moverse ≥ 24 h): {frame['is_placeholder'].sum()}",
        f"puntos posteriores a closedTime: {frame['after_close'].sum()}",
        f"puntos de mercados que no están en silver: {unknown}",
        f"tokens del catálogo sin historial: {without_history}",
        f"puntos a más de 1 min de las 00:00 UTC: {off_midnight}",
        f"tokens: {frame['token_id'].n_unique()}",
    ]
    if frame.height:
        report.first = str(frame["event_time"].min())
        report.last = str(frame["event_time"].max())
    return frame.select(
        "token_id", "condition_id", "outcome_index", "event_time", "knowledge_time",
        "price", "raw_price", "is_placeholder", "after_close", "source_request",
    ), report  # fmt: skip


def resolution_asof(markets: pl.DataFrame, at: datetime) -> pl.DataFrame:
    """El catálogo tal como se conocía en ``at``: sin pagos si la resolución no se conocía aún."""
    known = pl.col("resolution_known_at").is_not_null() & (pl.col("resolution_known_at") <= at)
    return markets.with_columns(
        pl.when(known).then(pl.col("payouts")).otherwise(None).alias("payouts"),
        known.alias("resolved_asof"),
    )


def prices_asof(prices: pl.DataFrame, at: datetime) -> pl.DataFrame:
    """Último precio válido (no relleno) de cada token conocido en ``at``."""
    return (
        prices.filter((pl.col("knowledge_time") <= at) & pl.col("price").is_not_null())
        .sort("token_id", "knowledge_time")
        .group_by("token_id", maintain_order=True)
        .last()
    )


def silver_dir(data_dir: Path) -> Path:
    return data_dir / "silver" / SOURCE


def build_markets_silver(data_dir: Path) -> tuple[pl.DataFrame, QualityReport]:
    frame, report = build_markets(read_bronze(data_dir / "bronze", "markets"))
    write_silver(
        frame, report, silver_dir(data_dir) / "markets.parquet", data_dir / "silver" / "_quality"
    )
    return frame, report


def build_silver(data_dir: Path, fidelity: int = DAILY) -> list[QualityReport]:
    """Reconstruye las tablas silver de Polymarket desde bronze."""
    markets, markets_report = build_markets_silver(data_dir)
    reports = [markets_report]
    bronze_prices = read_bronze(data_dir / "bronze", "prices", fidelity)
    if not bronze_prices.is_empty():
        prices, report = build_prices(bronze_prices, markets)
        report.table = f"polymarket/prices_{fidelity}"
        write_silver(
            prices,
            report,
            silver_dir(data_dir) / f"prices_{fidelity}.parquet",
            data_dir / "silver" / "_quality",
        )
        reports.append(report)
    return reports
