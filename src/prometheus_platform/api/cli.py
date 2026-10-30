"""CLI ``pq``: punto de entrada de las operaciones de la plataforma.

Ejemplos::

    pq ingest klines --market um --symbol BTCUSDT --interval 1h --start 2020-01
    pq ingest klines --market spot --symbol ETHUSDT --interval 1d --start 2020-01 --end 2024-12
    pq ingest funding --symbol BTCUSDT --start 2020-01
    pq silver build --symbol BTCUSDT --interval 1h
    pq research carry --hypothesis H1 --figures docs/estrategias/01-carry/img

Sin ``--end`` se ingiere hasta el último mes completo, porque Data Vision publica los archivos
mensuales una vez cerrado el mes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.data_platform.ingest import (
    IngestReport,
    ingest,
    monthly_funding,
    monthly_klines,
)
from prometheus_platform.data_platform.silver import (
    SilverValidationError,
    bronze_files,
    build_funding,
    build_klines,
    read_bronze,
    silver_path,
    write_silver,
)
from prometheus_platform.domain.datasets import DatasetKind, Market
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

    silver_cmd = commands.add_parser("silver", help="Capa silver: datos tipados y validados")
    silver_actions = silver_cmd.add_subparsers(dest="action", required=True)
    build = silver_actions.add_parser("build", help="Reconstruye silver desde bronze")
    build.add_argument("--symbol", required=True, type=str.upper)
    build.add_argument("--interval", default="1h", help="intervalo de las velas (por defecto 1h)")

    research = commands.add_parser("research", help="Evaluaciones pre-registradas")
    studies = research.add_subparsers(dest="study", required=True)
    carry = studies.add_parser("carry", help="Carry de funding: periodo de desarrollo")
    carry.add_argument("--hypothesis", choices=["H1", "H2"], required=True)
    carry.add_argument("--figures", type=Path, help="carpeta donde guardar las figuras")
    eda = studies.add_parser("eda", help="Estadística descriptiva y correlaciones de las features")
    eda.add_argument("--figures", type=Path, required=True)
    return parser


def http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True)


def _print_report(report: IngestReport) -> None:
    print(
        f"escritos={len(report.written)} ya_ingeridos={len(report.skipped)} "
        f"no_publicados={len(report.missing)} rechazados={len(report.rejected)} "
        f"fallidos={len(report.failed)} filas={report.rows_written}"
    )


def _silver_build(data_dir: Path, symbol: str, interval: str) -> int:
    bronze, silver = data_dir / "bronze", data_dir / "silver"
    quality = silver / "_quality"
    try:
        for market in (Market.SPOT, Market.USDM):
            files = bronze_files(bronze, DatasetKind.KLINES, market, symbol, interval)
            frame, report = build_klines(read_bronze(files), market, symbol, interval)
            path = silver_path(silver, DatasetKind.KLINES, symbol, market, interval)
            write_silver(frame, report, path, quality)
            print(f"{report.table}: filas={report.rows} huecos={report.gaps}", end=" ")
            print(f"outliers={report.outliers}")
        files = bronze_files(bronze, DatasetKind.FUNDING_RATE, Market.USDM, symbol, None)
        frame, report = build_funding(read_bronze(files), symbol)
        write_silver(frame, report, silver_path(silver, DatasetKind.FUNDING_RATE, symbol), quality)
        print(f"{report.table}: filas={report.rows} huecos={report.gaps}")
    except SilverValidationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


def _research_carry(data_dir: Path, hypothesis: str, figures: Path | None) -> int:
    # Importación diferida: MLflow, Optuna y matplotlib solo se cargan para investigar.
    from prometheus_platform.adapters.mlflow_registry import MlflowRegistry  # noqa: PLC0415
    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.reporting import plot_equity, write_outputs  # noqa: PLC0415

    data = [ce.load_symbol(data_dir / "silver", s) for s in ce.HYPOTHESES[hypothesis]]
    registry = MlflowRegistry(data_dir / "mlflow" / "mlflow.db", "carry-funding")
    evaluation = ce.evaluate_hypothesis(hypothesis, data, registry)
    path = write_outputs(evaluation, data_dir / "research" / "carry" / hypothesis)
    if figures is not None:
        plot_equity(
            evaluation, figures / f"{hypothesis.lower()}-curvas.png", evaluation.benchmark_returns
        )
    verdict = "PASA" if evaluation.passed else "NO PASA"
    print(f"{hypothesis}: elegida={evaluation.selected} gates={verdict} resumen={path}")
    for gate in evaluation.gates:
        print(f"  {gate.name} {'OK ' if gate.passed else 'NO '} {gate.criterion}: {gate.value:.4f}")
    return 0


def _research_eda(data_dir: Path, figures: Path) -> int:
    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.eda import (  # noqa: PLC0415
        correlation_matrix,
        describe_table,
        plot_correlation,
    )
    from prometheus_platform.research.panel import development_only  # noqa: PLC0415

    symbols = [s for group in ce.HYPOTHESES.values() for s in group]
    panel = pl.concat(
        [
            development_only(ce.load_symbol(data_dir / "silver", s).settlements).with_columns(
                pl.lit(s).alias("symbol")
            )
            for s in symbols
        ],
        how="diagonal_relaxed",
    )
    out = data_dir / "research" / "eda"
    out.mkdir(parents=True, exist_ok=True)
    table = describe_table(panel)
    table.write_csv(out / "describe.csv")
    corr = correlation_matrix(panel)
    corr.write_csv(out / "correlation.csv")
    plot_correlation(corr, figures / "correlacion-features.png")
    print(f"filas={panel.height} simbolos={len(symbols)} salida={out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    configure_logging(settings)
    if args.command == "silver":
        return _silver_build(settings.data_dir, args.symbol, args.interval)
    if args.command == "research" and args.study == "eda":
        return _research_eda(settings.data_dir, args.figures)
    if args.command == "research":
        return _research_carry(settings.data_dir, args.hypothesis, args.figures)

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
