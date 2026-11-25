"""Comandos ``pq polymarket``: ingesta bronze y silver de Polymarket (PQ-92).

Orden habitual::

    pq polymarket mercados --desde 2023-01 --hasta 2026-10   # catálogo de mercados cerrados
    pq polymarket silver                                      # silver de mercados (y precios)
    pq polymarket precios                                     # serie diaria de cada resultado
    pq polymarket silver                                      # ahora también los precios
    pq polymarket operaciones --desde 2023-11                 # operaciones (ventana de ~3 años)

``precios`` y ``operaciones`` recorren los mercados del silver: hay que construirlo antes.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.polymarket import PolymarketSource
from prometheus_platform.data_platform.ingest import months
from prometheus_platform.data_platform.polymarket import (
    DAILY,
    PolymarketIngestReport,
    build_silver,
    ingest_markets,
    ingest_prices,
    ingest_trades,
    silver_dir,
)
from prometheus_platform.data_platform.silver import SilverValidationError

REFRESH_MONTHS = 3  # los mercados de los últimos meses pueden cerrarse después de descargarlos


def _month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"mes inválido {value!r}: usa AAAA-MM") from None


def add_parser(commands: Any) -> None:
    pm = commands.add_parser("polymarket", help="Polymarket: ingesta bronze y silver (PQ-92)")
    actions = pm.add_subparsers(dest="action", required=True)

    mercados = actions.add_parser("mercados", help="Catálogo de mercados cerrados, por mes")
    mercados.add_argument("--desde", type=_month, required=True, help="AAAA-MM")
    mercados.add_argument("--hasta", type=_month, required=True, help="AAAA-MM")
    mercados.add_argument("--volumen-minimo", type=float, default=1000.0, help="USD (pre-registro)")
    mercados.add_argument(
        "--refrescar-desde",
        type=_month,
        help=f"vuelve a descargar desde este mes (por defecto, los últimos {REFRESH_MONTHS})",
    )

    precios = actions.add_parser("precios", help="Serie de precios de cada resultado")
    precios.add_argument("--fidelidad", type=int, default=DAILY, help="minutos (1440 = diaria)")
    precios.add_argument(
        "--forzar", action="store_true", help="vuelve a descargar los meses ya guardados"
    )
    _month_filter(precios)
    precios.add_argument(
        "--creados-hasta",
        type=_day,
        help=(
            "solo mercados creados hasta este día (AAAA-MM-DD). Un mes así queda INCOMPLETO:"
            " para completarlo, vuelve a ejecutar ese mes con --forzar"
        ),
    )

    operaciones = actions.add_parser(
        "operaciones", help="Operaciones de cada mercado (Data API v2)"
    )
    operaciones.add_argument(
        "--max-paginas", type=int, default=50, help="1.000 operaciones por página"
    )
    operaciones.add_argument("--forzar", action="store_true")
    _month_filter(operaciones)

    actions.add_parser("silver", help="Reconstruye el silver de Polymarket desde bronze")


def _day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"día inválido {value!r}: usa AAAA-MM-DD") from None


def _month_filter(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--hilos", type=int, default=8, help="peticiones en paralelo (límite de la API: 1.000/10 s)"
    )
    parser.add_argument("--desde", type=_month, help="solo mercados que cierran desde este mes")
    parser.add_argument("--hasta", type=_month, help="solo mercados que cierran hasta este mes")


def _refresh_default(today: date) -> date:
    year, month = today.year, today.month - REFRESH_MONTHS
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, 1)


def _silver_markets(data_dir: Path, args: argparse.Namespace) -> pl.DataFrame:
    path = silver_dir(data_dir) / "markets.parquet"
    if not path.exists():
        raise SystemExit(
            f"No existe {path}: ejecuta antes `pq polymarket mercados` y `pq polymarket silver`"
        )
    frame = pl.read_parquet(path)
    if args.desde is not None:
        frame = frame.filter(
            pl.col("end_date") >= datetime(args.desde.year, args.desde.month, 1, tzinfo=UTC)
        )
    if args.hasta is not None:
        end = date(args.hasta.year + (args.hasta.month == 12), args.hasta.month % 12 + 1, 1)
        frame = frame.filter(pl.col("end_date") < datetime(end.year, end.month, 1, tzinfo=UTC))
    return frame


def _created_until(markets: pl.DataFrame, day: date) -> pl.DataFrame:
    """Mercados creados hasta ``day`` incluido. Avisa de los meses que quedarán incompletos."""
    limit = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=UTC)
    keep = pl.col("created_at").is_not_null() & (pl.col("created_at") <= limit)
    month = pl.col("end_date").dt.strftime("%Y-%m")
    partial = sorted(
        set(markets.filter(keep.not_()).select(month)["end_date"].to_list())
        & set(markets.filter(keep).select(month)["end_date"].to_list())
    )
    if partial:
        print(f"AVISO meses incompletos (sin los creados después de {day}): {', '.join(partial)}")
    return markets.filter(keep)


def _print(report: PolymarketIngestReport) -> int:
    print(
        f"escritos {len(report.written)}, ya estaban {len(report.skipped)}, "
        f"fallidos {len(report.failed)}, filas {report.rows_written}"
    )
    for label in report.failed:
        print(f"  FALLÓ {label} (se reintenta en la próxima ejecución)")
    return 0 if report.ok else 1


def run(
    args: argparse.Namespace, data_dir: Path, client_factory: Callable[[], httpx.Client]
) -> int:
    clock = SystemClock()
    bronze = data_dir / "bronze"
    if args.action == "silver":
        try:
            reports = build_silver(data_dir)
        except SilverValidationError as exc:
            print(f"silver no se construyó: {exc}")
            return 1
        for quality in reports:
            print(f"{quality.table}: {quality.rows} filas ({quality.first} → {quality.last})")
            for check in quality.checks:
                print(f"  - {check}")
        return 0
    with client_factory() as client:
        source = PolymarketSource(client)
        if args.action == "mercados":
            refresh = args.refrescar_desde or _refresh_default(clock.now().date())
            report = ingest_markets(
                source,
                bronze,
                months(args.desde, args.hasta),
                min_volume=args.volumen_minimo,
                clock=clock,
                refresh_since=refresh,
            )
        elif args.action == "precios":
            markets = _silver_markets(data_dir, args)
            if args.creados_hasta is not None:
                markets = _created_until(markets, args.creados_hasta)
            report = ingest_prices(
                source,
                bronze,
                markets,
                clock=clock,
                fidelity=args.fidelidad,
                force=args.forzar,
                workers=args.hilos,
            )
        else:
            report = ingest_trades(
                source,
                bronze,
                _silver_markets(data_dir, args),
                clock=clock,
                max_pages=args.max_paginas,
                force=args.forzar,
                workers=args.hilos,
            )
    return _print(report)
