"""CLI ``pq``: punto de entrada de las operaciones de la plataforma.

Ejemplos::

    pq ingest klines --market um --symbol BTCUSDT --interval 1h --start 2020-01
    pq ingest klines --market spot --symbol ETHUSDT --interval 1d --start 2020-01 --end 2024-12
    pq ingest funding --symbol BTCUSDT --start 2020-01

Sin ``--end`` se ingiere hasta el último mes completo, porque Data Vision publica los archivos
mensuales una vez cerrado el mes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime

import httpx

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.data_platform.ingest import (
    IngestReport,
    ingest,
    monthly_funding,
    monthly_klines,
)
from prometheus_platform.domain.datasets import Market
from prometheus_platform.ops.logging import configure_logging
from prometheus_platform.ops.settings import load_settings

SOURCE_NAME = "binance_data_vision"


def _month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"mes inválido {value!r}: usa AAAA-MM") from None


def last_complete_month(today: date) -> date:
    return date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pq", description="Plataforma PrometheusQuant")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser("ingest", help="Ingesta bronze desde Binance Data Vision")
    datasets = ingest_cmd.add_subparsers(dest="dataset", required=True)

    def add_range(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--symbol", required=True, type=str.upper, help="p. ej. BTCUSDT")
        sub.add_argument("--start", required=True, type=_month, help="primer mes (AAAA-MM)")
        sub.add_argument(
            "--end", type=_month, help="último mes (AAAA-MM); por defecto, el último completo"
        )

    klines = datasets.add_parser("klines", help="Velas OHLCV")
    klines.add_argument("--market", choices=[m.value for m in Market], default=Market.USDM.value)
    klines.add_argument("--interval", required=True, help="p. ej. 1h, 1d")
    add_range(klines)

    funding = datasets.add_parser("funding", help="Funding rate de perpetuos USDⓈ-M")
    add_range(funding)
    return parser


def http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True)


def _print_report(report: IngestReport) -> None:
    print(
        f"escritos={len(report.written)} ya_ingeridos={len(report.skipped)} "
        f"no_publicados={len(report.missing)} rechazados={len(report.rejected)} "
        f"fallidos={len(report.failed)} filas={report.rows_written}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(settings)

    clock = SystemClock()
    end = args.end or last_complete_month(clock.now().date())
    if args.dataset == "klines":
        refs = monthly_klines(Market(args.market), args.symbol, args.interval, args.start, end)
    else:
        refs = monthly_funding(args.symbol, args.start, end)

    store = ParquetBronzeStore(settings.data_dir / "bronze", source=SOURCE_NAME, clock=clock)
    with http_client() as client:
        report = ingest(refs, BinanceDataVisionSource(client), store)
    _print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
