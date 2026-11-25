"""CLI ``pq``: punto de entrada de las operaciones de la plataforma.

Ejemplos::

    pq ingest klines --market um --symbol BTCUSDT --interval 1h --start 2020-01
    pq ingest klines --market spot --symbol ETHUSDT --interval 1d --start 2020-01 --end 2024-12
    pq ingest funding --symbol BTCUSDT --start 2020-01
    pq silver build --symbol BTCUSDT --interval 1h
    pq research carry --hypothesis H1 --figures docs/estrategias/01-carry/img
    pq research trend --figures docs/estrategias/02-tendencia/img

Sin ``--end`` se ingiere hasta el último mes completo, porque Data Vision publica los archivos
mensuales una vez cerrado el mes.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import polars as pl

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.binance_rest import SOURCE_NAME as API_SOURCE_NAME
from prometheus_platform.adapters.binance_rest import BinanceRestSource, day_refs
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.exchange_funding import SOURCES as EXCHANGE_SOURCES
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.notifiers import notifier_from_settings
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.adapters.trial_ledger import (
    RegistryTee,
    TrialLedger,
    counts,
    git_author,
    read_rows,
)
from prometheus_platform.api import polymarket_cli
from prometheus_platform.api.paper import cost_cli
from prometheus_platform.api.paper.compose import (
    BROKERS,
    PAPER_DIR,
    PaperPaths,
    RunnerAlreadyRunningError,
    build,
    build_watchdog,
    paper_dir,
    single_instance,
)
from prometheus_platform.api.paper.runner import RunnerConfig
from prometheus_platform.data_platform.gold import GoldValidationError, build_gold, render_docs_page
from prometheus_platform.data_platform.ingest import (
    IngestReport,
    ingest,
    monthly_funding,
    monthly_klines,
)
from prometheus_platform.data_platform.silver import (
    SilverValidationError,
    build_exchange_funding,
    build_symbol,
)
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Granularity, Market
from prometheus_platform.domain.model import Venue
from prometheus_platform.domain.ports import Notifier
from prometheus_platform.ops.logging import configure_logging
from prometheus_platform.ops.settings import Settings, load_settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.research.carry_evaluation import HYPOTHESES
from prometheus_platform.strategies.carry import H2_PARAMS

if TYPE_CHECKING:
    from wsgiref.simple_server import WSGIServer

    from prometheus_platform.adapters.uptime_ping import UptimePinger
    from prometheus_platform.api.paper.report import WeeklySummary
    from prometheus_platform.api.paper.weekly import Parity

SOURCE_NAME = "binance_data_vision"


GOLD_DOCS = Path("docs/arquitectura/modelo-gold.md")


def _month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"mes inválido {value!r}: usa AAAA-MM") from None


def _day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"día inválido {value!r}: usa AAAA-MM-DD") from None


def last_complete_month(today: date) -> date:
    return date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pq", description="Plataforma PrometheusQuant")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_ingest(commands)
    _add_layers(commands)
    _add_research(commands)
    _add_operations(commands)
    polymarket_cli.add_parser(commands)
    return parser


Commands = Any  # argparse._SubParsersAction no es público


def _add_ingest(commands: Commands) -> None:
    ingest_cmd = commands.add_parser("ingest", help="Ingesta bronze desde Binance")
    ingest_cmd.add_argument(
        "--source",
        choices=["data-vision", "api", "bybit", "okx"],
        default="data-vision",
        help=(
            "data-vision: meses publicados (auditados); api: días recientes por la API pública;"
            " bybit u okx: funding mensual de ese exchange (PQ-79)"
        ),
    )
    datasets = ingest_cmd.add_subparsers(dest="dataset", required=True)

    def add_range(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--symbol", required=True, type=str.upper, help="p. ej. BTCUSDT")
        sub.add_argument("--start", type=_month, help="data-vision: primer mes (AAAA-MM)")
        sub.add_argument(
            "--end", type=_month, help="data-vision: último mes; por defecto, el último completo"
        )
        sub.add_argument(
            "--since", type=_day, help="api: primer día (AAAA-MM-DD); por defecto, el día 1 del mes"
        )

    klines = datasets.add_parser("klines", help="Velas OHLCV")
    klines.add_argument("--market", choices=[m.value for m in Market], default=Market.USDM.value)
    klines.add_argument("--interval", required=True, help="p. ej. 1h, 1d")
    add_range(klines)

    funding = datasets.add_parser("funding", help="Funding rate de perpetuos USDⓈ-M")
    add_range(funding)


def _add_layers(commands: Commands) -> None:
    silver_cmd = commands.add_parser("silver", help="Capa silver: datos tipados y validados")
    silver_actions = silver_cmd.add_subparsers(dest="action", required=True)
    build = silver_actions.add_parser("build", help="Reconstruye silver desde bronze")
    build.add_argument("--symbol", required=True, type=str.upper)
    build.add_argument("--interval", default="1h", help="intervalo de las velas (por defecto 1h)")
    build.add_argument(
        "--exchange",
        choices=["bybit", "okx"],
        help="solo el funding de ese exchange (PQ-79); sin él, las tablas de Binance",
    )

    gold_cmd = commands.add_parser("gold", help="Capa gold: modelo en estrella para BI (PQ-46)")
    gold_actions = gold_cmd.add_subparsers(dest="action", required=True)
    gold_actions.add_parser("build", help="Reconstruye gold desde silver y los resultados")
    gold_docs = gold_actions.add_parser("docs", help="Genera la página del modelo gold")
    gold_docs.add_argument("--out", type=Path, default=GOLD_DOCS)


def _add_research(commands: Commands) -> None:
    research = commands.add_parser("research", help="Evaluaciones pre-registradas")
    studies = research.add_subparsers(dest="study", required=True)
    carry = studies.add_parser("carry", help="Carry de funding: periodo de desarrollo")
    carry.add_argument("--hypothesis", choices=["H1", "H2"], required=True)
    carry.add_argument("--figures", type=Path, help="carpeta donde guardar las figuras")
    trend = studies.add_parser(
        "trend", help="Tendencia (T1 y T2): periodo de desarrollo, las 12 configuraciones (PQ-68)"
    )
    trend.add_argument("--figures", type=Path, help="carpeta donde guardar las figuras")
    carry_holdout = studies.add_parser(
        "carry-holdout",
        help="Carry H2: abre el holdout UNA SOLA VEZ con la configuración elegida (PQ-50)",
    )
    carry_holdout.add_argument("--figures", type=Path, help="carpeta donde guardar las figuras")
    carry_holdout.add_argument(
        "--confirmo-un-solo-uso",
        action="store_true",
        help="obligatorio: el holdout se abre una vez y no tiene vuelta atrás",
    )
    trend_holdout = studies.add_parser(
        "trend-holdout",
        help="Tendencia: abre el holdout UNA SOLA VEZ con la configuración elegida (PQ-68)",
    )
    trend_holdout.add_argument("--figures", type=Path, help="carpeta donde guardar las figuras")
    trend_holdout.add_argument(
        "--confirmo-un-solo-uso",
        action="store_true",
        help="obligatorio: el holdout se abre una vez y no tiene vuelta atrás",
    )
    studies.add_parser(
        "momentum-universo",
        help="Universo del momentum transversal: top 15 por volumen de dic-2020 (PQ-114)",
    )
    eda = studies.add_parser("eda", help="Estadística descriptiva y correlaciones de las features")
    eda.add_argument("--figures", type=Path, required=True)
    model = studies.add_parser("funding-model", help="Modelo predictivo del funding (cap. 5)")
    model.add_argument("--figures", type=Path, required=True)
    model.add_argument("--target-mode", choices=["level", "residual"], default="residual")
    simulate = studies.add_parser(
        "simulate", help="Markov, bondad de ajuste y Monte Carlo (cap. 6)"
    )
    simulate.add_argument("--figures", type=Path, required=True)
    simulate.add_argument("--paths", type=int, default=10_000)
    studies.add_parser(
        "paper-banda",
        help="¿Caen los últimos 30 días del paper en la banda p5-p95 del Monte Carlo? (PQ-120)",
    )
    studies.add_parser(
        "stats", help="Validación estadística de la optimización: t, ANOVA, Friedman (cap. 7.4)"
    )
    studies.add_parser(
        "exchanges", help="Funding de Binance frente a Bybit y OKX en el desarrollo (PQ-79)"
    )
    studies.add_parser(
        "budget", help="Presupuesto de capital entre estrategias aprobadas con tope de CVaR (PQ-83)"
    )
    finance = studies.add_parser(
        "finance", help="Costes cotizados, VAN, TIR y capital de equilibrio (cap. 8.3-8.4)"
    )
    finance.add_argument(
        "--update-doc", type=Path, help="reescribe el bloque PQ-49 de este documento Markdown"
    )
    ledger = studies.add_parser(
        "registro", help="Registro de ensayos compartido: N por familia (PQ-112)"
    )
    ledger.add_argument("action", choices=["resumen", "importar-mlflow", "verificar"])


def _add_paper_backup_parser(paper_actions: Any) -> None:
    backup = paper_actions.add_parser(
        "backup", help="Respaldos cifrados (age) de data/paper y su restauración (PQ-73)"
    )
    backup_actions = backup.add_subparsers(dest="backup_action", required=True)
    keygen = backup_actions.add_parser("keygen", help="Crea el par de claves age (una vez)")
    keygen.add_argument("--out", type=Path, required=True, help="archivo de la clave privada")
    create = backup_actions.add_parser("create", help="Cifra data/paper y poda lo viejo")
    create.add_argument("--out", type=Path, required=True, help="carpeta de los respaldos")
    restore = backup_actions.add_parser("restore", help="Restaura un respaldo en data/paper")
    restore.add_argument("archive", type=Path, help="paper-<fecha>.tar.gz.age")
    restore.add_argument("--identity", type=Path, required=True, help="clave privada age")
    restore.add_argument("--force", action="store_true", help="reemplaza el diario existente")


def _add_operations(commands: Commands) -> None:
    report = commands.add_parser("report", help="Informe ejecutivo en Quarto (PQ-39)")
    report_actions = report.add_subparsers(dest="action", required=True)
    inputs = report_actions.add_parser(
        "inputs", help="Escribe cifras, tablas y figuras del informe"
    )
    inputs.add_argument("--out", type=Path, default=Path("reports/storytelling"))
    public = report_actions.add_parser(
        "public", help="Página pública de resultados para el jurado (PQ-89)"
    )
    public.add_argument("--out", type=Path, default=Path("docs/resultados.md"))

    paper = commands.add_parser("paper", help="Paper trading: kill-switch y estado (PQ-53)")
    paper_actions = paper.add_subparsers(dest="action", required=True)
    kill = paper_actions.add_parser("kill", help="Activa (o rearma) el kill-switch")
    kill.add_argument("--reason", default="activado a mano por CLI")
    kill.add_argument("--reset", action="store_true", help="rearmar la operación")
    kill.add_argument("--confirm", action="store_true", help="obligatorio con --reset")
    kill.add_argument("--by", default="", help="quién rearma (obligatorio con --reset)")
    kill.add_argument(
        "--strategy", default="", help="solo esa estrategia (p. ej. carry-h2); sin ella, todo"
    )
    status = paper_actions.add_parser(
        "status", help="Estado del kill-switch global y por estrategia"
    )
    for sub in (kill, status):  # cada bróker tiene su carpeta y su kill-switch (PQ-52)
        sub.add_argument("--broker", choices=list(BROKERS), default="simulado")
    run = paper_actions.add_parser(
        "run", help="Runner del carry H2 con el bróker simulado y datos en vivo (PQ-54)"
    )
    run.add_argument("--once", action="store_true", help="un solo ciclo y termina")
    run.add_argument("--interval", type=float, default=60.0, help="segundos entre ciclos")
    run.add_argument("--capital", type=_decimal_arg, default=Decimal(1000), help="USD iniciales")
    run.add_argument("--symbols", default=",".join(HYPOTHESES["H2"]))
    run.add_argument("--k", type=int, default=H2_PARAMS.k)
    run.add_argument("--theta", type=float, default=H2_PARAMS.theta)
    run.add_argument(
        "--market-data",
        choices=["rest", "stream"],
        default="rest",
        help="stream: precios por websocket con respaldo REST (PQ-80); rest: la API cada ciclo",
    )
    run.add_argument(
        "--carry-share",
        type=_decimal_arg,
        default=None,
        help="parte del capital del carry en (0, 1]; el resto queda en efectivo (PQ-83)",
    )
    run.add_argument(
        "--broker",
        choices=list(BROKERS),
        default="simulado",
        help="binance-demo: órdenes reales con dinero ficticio en Binance Demo (PQ-52), "
        "con su propia carpeta data/paper-binance-demo",
    )
    run.add_argument(
        "--metrics-port",
        type=int,
        default=0,
        help="sirve /metrics para Prometheus en 127.0.0.1:PUERTO (PQ-71); 0 = no",
    )
    run.add_argument(
        "--exchange-cap",
        action="append",
        default=[],
        metavar="EXCHANGE=TOPE",
        help="tope de capital por exchange, p. ej. BINANCE=0.125 (pq research budget)",
    )
    watchdog = paper_actions.add_parser(
        "watchdog", help="Vigila el heartbeat del runner y alerta si deja de reportar (PQ-55)"
    )
    watchdog.add_argument("--once", action="store_true", help="una revisión y termina (cron)")
    watchdog.add_argument("--interval", type=float, default=60.0, help="segundos entre revisiones")
    paper_actions.add_parser(
        "bot", help="Bot de Telegram: /estado, /pnl y /kill desde los chats autorizados (PQ-72)"
    )
    _add_paper_backup_parser(paper_actions)
    weekly = paper_actions.add_parser(
        "weekly-report", help="Informe semanal del paper trading: PDF y envío a Telegram (PQ-85)"
    )
    weekly.add_argument(
        "--week", default="", help="semana ISO AAAA-Www; por defecto, la última ya terminada"
    )
    weekly.add_argument("--pdf", action="store_true", help="genera el PDF con Quarto")
    weekly.add_argument(
        "--send", action="store_true", help="envía el PDF (o, sin --pdf, el resumen) al canal"
    )
    cost_cli.add_parsers(paper_actions)

    _add_monitor_parser(commands)

    alert = commands.add_parser("alert", help="Canal de alertas (PQ-38)")
    alert_actions = alert.add_subparsers(dest="action", required=True)
    alert_actions.add_parser("test", help="Envía una alerta de prueba por el canal configurado")


def _add_monitor_parser(commands: Commands) -> None:
    monitor = commands.add_parser("monitor", help="Monitoreo de la fase 6 de CRISP-ML(Q)")
    monitor_actions = monitor.add_subparsers(dest="action", required=True)
    drift = monitor_actions.add_parser(
        "drift", help="Drift de datos, modelo y desempeño frente a lo esperado (PQ-86)"
    )
    drift.add_argument(
        "--send", action="store_true", help="alerta al canal si algo cruza su umbral"
    )
    drift.add_argument(
        "--ticket", action="store_true", help="abre un issue de GitHub por alerta (con gh)"
    )


def http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True)


# Margen tras el cierre del día: la última vela y la liquidación de las 00:00 ya publicadas.
SETTLE_MARGIN = timedelta(minutes=5)


def _ingest_api(args: argparse.Namespace, bronze_root: Path, clock: SystemClock) -> int:
    """Días recientes desde la API pública (PQ-65). Idempotente: no vuelve a pedir días que ya
    están completos en bronze ni meses que Data Vision ya publicó."""
    today = clock.now().date()
    since = args.since or today.replace(day=1)
    if args.dataset == "klines":
        first = ArchiveRef(
            Market(args.market),
            DatasetKind.KLINES,
            args.symbol,
            since,
            args.interval,
            Granularity.DAILY,
        )
    else:
        first = ArchiveRef(
            Market.USDM, DatasetKind.FUNDING_RATE, args.symbol, since, None, Granularity.DAILY
        )
    store = ParquetBronzeStore(bronze_root, source=API_SOURCE_NAME, clock=clock)
    audited = ParquetBronzeStore(bronze_root, source=SOURCE_NAME, clock=clock)

    def settled(ref: ArchiveRef) -> bool:
        month = replace(ref, period=ref.period.replace(day=1), granularity=Granularity.MONTHLY)
        closed = datetime.combine(ref.period + timedelta(days=1), datetime.min.time(), UTC)
        return audited.path_for(month).exists() or store.written_after(ref, closed + SETTLE_MARGIN)

    refs = [r for r in day_refs(first, today) if not settled(r)]
    with http_client() as client:
        report = ingest(refs, BinanceRestSource(client, now=clock.now), store)
    _print_report(report)
    return 0 if report.ok else 1


def _ingest_exchange(args: argparse.Namespace, bronze_root: Path, clock: SystemClock) -> int:
    """Funding mensual de Bybit u OKX en bronze, con su propia fuente (PQ-79)."""
    if args.dataset != "funding" or args.start is None:
        print(
            f"ERROR con --source {args.source} solo hay funding y --start es obligatorio",
            file=sys.stderr,
        )
        return 2
    refs = monthly_funding(
        args.symbol, args.start, args.end or last_complete_month(clock.now().date())
    )
    store = ParquetBronzeStore(bronze_root, source=f"{args.source}_api", clock=clock)
    with http_client() as client:
        report = ingest(refs, EXCHANGE_SOURCES[args.source](client), store)
    _print_report(report)
    return 0 if report.ok else 1


def _print_report(report: IngestReport) -> None:
    print(
        f"escritos={len(report.written)} ya_ingeridos={len(report.skipped)} "
        f"no_publicados={len(report.missing)} rechazados={len(report.rejected)} "
        f"fallidos={len(report.failed)} filas={report.rows_written}"
    )


def _sources_line(sources: dict[str, int]) -> str:
    line = f"api={sources['filas_api']}"
    if sources["filas_api_reemplazadas"]:
        line += (
            f" api_reemplazada_por_data_vision={sources['filas_api_reemplazadas']}"
            f" diferencias(solo_api={sources['solo_api']},"
            f" solo_data_vision={sources['solo_data_vision']},"
            f" valores={sources['valores_distintos']})"
        )
    return line


def _silver_build(data_dir: Path, symbol: str, interval: str, exchange: str | None = None) -> int:
    try:
        reports = (
            [build_exchange_funding(data_dir, exchange, symbol)]
            if exchange
            else build_symbol(data_dir, symbol, interval)
        )
    except SilverValidationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    for report in reports:
        extra = f" outliers={report.outliers}" if report.table.startswith("klines") else ""
        sources = f" {_sources_line(report.fuentes)}" if report.fuentes else ""
        print(f"{report.table}: filas={report.rows} huecos={report.gaps}{extra}{sources}")
    return 0


def _gold(action: str, data_dir: Path, out: Path) -> int:
    if action == "docs":
        out.write_text(render_docs_page(), encoding="utf-8")
        print(f"documentación del modelo gold en {out}")
        return 0
    try:
        report = build_gold(data_dir)
    except GoldValidationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    for name, rows in report.rows.items():
        print(f"{name}: filas={rows}")
    for missing in report.missing:
        print(f"aviso: falta {missing}; sus tablas quedan vacías")
    print(f"capa gold en {data_dir / 'gold'} (CSV para Power BI en {data_dir / 'gold' / 'export'})")
    return 0


def _research_carry(
    data_dir: Path, hypothesis: str, figures: Path | None, ledger: TrialLedger
) -> int:
    # Importación diferida: MLflow, Optuna y matplotlib solo se cargan para investigar.
    from prometheus_platform.adapters.mlflow_registry import MlflowRegistry  # noqa: PLC0415
    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.reporting import plot_equity, write_outputs  # noqa: PLC0415

    data = [ce.load_symbol(data_dir / "silver", s) for s in ce.HYPOTHESES[hypothesis]]
    mlflow = MlflowRegistry(data_dir / "mlflow" / "mlflow.db", "carry-funding")
    # N sale del registro compartido (todos los carriles); MLflow recibe una copia.
    evaluation = ce.evaluate_hypothesis(hypothesis, data, RegistryTee(ledger, mlflow))
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


def _holdout_blocked(confirmed: bool, ledger: TrialLedger, execution: str) -> bool:
    """Protecciones comunes de un holdout de un solo uso; True si NO se debe abrir."""
    if not confirmed:
        print("El holdout se abre una sola vez: repite con --confirmo-un-solo-uso", file=sys.stderr)
        return True
    opened = [
        r
        for r in read_rows(ledger.directory)
        if r.familia == ledger.familia and r.nombre == execution
    ]
    if opened:
        print(
            f"El holdout de {ledger.familia} ya se abrió el {opened[0].fecha} ({opened[0].carril}):"
            " no se repite.",
            file=sys.stderr,
        )
        return True
    return False


def _research_carry_holdout(
    data_dir: Path, figures: Path | None, confirmed: bool, ledger: TrialLedger
) -> int:
    """Abre el holdout de H2 una sola vez (pre-registro del carry §7, PQ-50), sin re-ajustes."""
    import json  # noqa: PLC0415

    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.reporting import (  # noqa: PLC0415
        plot_holdout,
        write_holdout_outputs,
    )

    if _holdout_blocked(confirmed, ledger, ce.HOLDOUT_EXECUTION):
        return 2
    development = data_dir / "research" / "carry" / "H2" / "summary.json"
    if not development.exists():
        print(f"Falta la evaluación de desarrollo: {development}", file=sys.stderr)
        return 2
    summary = json.loads(development.read_text(encoding="utf-8"))
    if not summary.get("passed"):
        print("H2 no pasó los gates de desarrollo: el holdout no se abre (§8).", file=sys.stderr)
        return 2
    selected = ce.selected_config(str(summary["selected"])).name
    # Primero la fila: desde aquí el holdout cuenta como abierto aunque algo falle después.
    params = {"hipotesis": "H2", "configuracion": selected}
    ledger.log_execution(ce.HOLDOUT_EXECUTION, params=params)
    data = [ce.load_symbol(data_dir / "silver", s) for s in ce.HYPOTHESES["H2"]]
    evaluation = ce.evaluate_holdout("H2", data, selected)
    path = write_holdout_outputs(evaluation, data_dir / "research" / "carry" / "holdout")
    if figures is not None:
        plot_holdout(evaluation, figures / "holdout-curva.png", title="Carry H2")
    verdict = "PASA" if evaluation.passed else "NO PASA"
    print(f"Holdout H2 {selected}: {verdict} resumen={path}")
    for criterion in evaluation.criteria:
        mark = "OK " if criterion.passed else "NO "
        print(f"  {criterion.name} {mark}{criterion.criterion}: {criterion.value:.4f}")
    return 0


def _research_trend_holdout(
    data_dir: Path, figures: Path | None, confirmed: bool, ledger: TrialLedger
) -> int:
    """Abre el holdout de tendencia una sola vez (pre-registro §7), sin re-ajustes ni repetirlo."""
    import json  # noqa: PLC0415

    from prometheus_platform.research import trend_evaluation as te  # noqa: PLC0415
    from prometheus_platform.research.reporting import (  # noqa: PLC0415
        plot_holdout,
        write_holdout_outputs,
    )

    if _holdout_blocked(confirmed, ledger, te.HOLDOUT_EXECUTION):
        return 2
    development = data_dir / "research" / "trend" / "T1" / "summary.json"
    if not development.exists():
        print(f"Falta la evaluación de desarrollo: {development}", file=sys.stderr)
        return 2
    summary = json.loads(development.read_text(encoding="utf-8"))
    if not summary.get("passed"):
        print("T1 no pasó los gates de desarrollo: el holdout no se abre (§8).", file=sys.stderr)
        return 2
    config = te.selected_config(str(summary["selected"]))
    # Primero la fila: desde aquí el holdout cuenta como abierto aunque algo falle después.
    ledger.log_execution(te.HOLDOUT_EXECUTION, params={"configuracion": config.name})
    data = [te.load_market_holdout(data_dir / "silver", s) for s in te.SYMBOLS]
    evaluation = te.evaluate_holdout(data, config)
    path = write_holdout_outputs(evaluation, data_dir / "research" / "trend" / "holdout")
    if figures is not None:
        plot_holdout(evaluation, figures / "holdout-curva.png")
    verdict = "PASA" if evaluation.passed else "NO PASA"
    print(f"Holdout {config.name}: {verdict} resumen={path}")
    for criterion in evaluation.criteria:
        mark = "OK " if criterion.passed else "NO "
        print(f"  {criterion.name} {mark}{criterion.criterion}: {criterion.value:.4f}")
    return 0


def _research_trend(data_dir: Path, figures: Path | None, ledger: TrialLedger) -> int:
    from prometheus_platform.research import trend_evaluation as te  # noqa: PLC0415
    from prometheus_platform.research.reporting import (  # noqa: PLC0415
        plot_equity,
        write_trend_outputs,
    )

    data = [te.load_market(data_dir / "silver", s) for s in te.SYMBOLS]
    # Las 12 configuraciones se registran (N) antes de evaluar cualquiera de las dos hipótesis.
    evaluations = te.evaluate_family(data, ledger)
    for hypothesis, evaluation in evaluations.items():
        path = write_trend_outputs(evaluation, data_dir / "research" / "trend" / str(hypothesis))
        if figures is not None:
            plot_equity(
                evaluation,
                figures / f"{str(hypothesis).lower()}-curvas.png",
                evaluation.benchmark_returns,
                benchmark_label="B1 comprar y mantener",
            )
        verdict = "PASA" if evaluation.passed else "NO PASA"
        print(f"{hypothesis}: elegida={evaluation.selected} gates={verdict} resumen={path}")
        for gate in evaluation.gates:
            mark = "OK " if gate.passed else "NO "
            print(f"  {gate.name} {mark}{gate.criterion}: {gate.value:.4f}")
    return 0


def _development_panel(data_dir: Path) -> pl.DataFrame:
    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.panel import development_only  # noqa: PLC0415

    symbols = [s for group in ce.HYPOTHESES.values() for s in group]
    return pl.concat(
        [
            development_only(ce.load_symbol(data_dir / "silver", s).settlements).with_columns(
                pl.lit(s).alias("symbol")
            )
            for s in symbols
        ],
        how="diagonal_relaxed",
    )


def _research_model(data_dir: Path, figures: Path, target_mode: str, ledger: TrialLedger) -> int:
    from prometheus_platform.adapters.mlflow_registry import MlflowRegistry  # noqa: PLC0415
    from prometheus_platform.research.carry_evaluation import TrialRecord  # noqa: PLC0415
    from prometheus_platform.research.funding_model import run_study  # noqa: PLC0415
    from prometheus_platform.research.reporting import plot_roc, write_model_study  # noqa: PLC0415

    study = run_study(_development_panel(data_dir), target_mode=target_mode)
    tags = {"target_mode": target_mode, "period": "desarrollo"}
    registry = RegistryTee(
        ledger, MlflowRegistry(data_dir / "mlflow" / "mlflow.db", "funding-model")
    )
    for r in study.regression:
        registry.log_trial(
            TrialRecord(
                "regresion",
                f"{r.name}:{'tuned' if r.tuned else 'default'}",
                {k: str(v) for k, v in r.best_params.items()},
                {"rmse": r.rmse, "mae": r.mae, "r2": r.r2},
                tags,
            )
        )
    for c in study.classification:
        registry.log_trial(
            TrialRecord(
                "clasificacion",
                f"{c.name}:{'tuned' if c.tuned else 'default'}",
                {k: str(v) for k, v in c.best_params.items()},
                {"auc": c.auc, "f1": c.f1},
                tags,
            )
        )
    path = write_model_study(study, data_dir / "research" / "funding_model" / target_mode)
    plot_roc(study, figures / "roc-funding.png")
    best = study.regression[0]
    print(f"filas={study.rows} mejor_regresion={best.name} rmse={best.rmse:.4f} resumen={path}")
    print(f"diebold_mariano={study.diebold_mariano}")
    return 0


def _research_simulate(data_dir: Path, figures: Path, paths: int) -> int:
    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.panel import development_only  # noqa: PLC0415
    from prometheus_platform.research.reporting import (  # noqa: PLC0415
        plot_simulation,
        write_simulation,
    )
    from prometheus_platform.research.simulation import (  # noqa: PLC0415
        development_sequences,
        run_simulation_study,
    )

    panels = [
        development_only(ce.load_symbol(data_dir / "silver", s).settlements)
        for s in ce.HYPOTHESES["H2"]
    ]
    study = run_simulation_study(development_sequences(panels), n_paths=paths)
    path = write_simulation(study, data_dir / "research" / "simulation")
    plot_simulation(study, figures)
    print(f"resumen={path}")
    for row in [study.historical, *study.validation]:
        print(f"  {row.model}: ciclos/año={row.cycles:.1f} retorno={row.mean_return:.2%}")
    return 0


def _research_paper_band(data_dir: Path) -> int:
    """Criterio 4 del go/no-go: el retorno de 30 días del paper frente a la banda (PQ-120)."""
    from prometheus_platform.api.paper.report import build_view  # noqa: PLC0415
    from prometheus_platform.research.simulation import ReturnBand, check_band  # noqa: PLC0415

    summary = data_dir / "research" / "simulation" / "summary.json"
    band_data = json.loads(summary.read_text()).get("banda_30_dias") if summary.exists() else None
    if not band_data:
        print("ERROR falta la banda de 30 días: corre antes `pq research simulate` (PQ-120).")
        return 2
    band = ReturnBand(**band_data)
    view = build_view(JsonlEventJournal(PaperPaths(data_dir / PAPER_DIR).journal).replay())
    start = view.valuations[0].occurred_at if view.valuations else None
    equity = [
        ((v.occurred_at - start).total_seconds() / 86_400, float(v.equity))
        for v in view.valuations
        if start is not None
    ]
    result = check_band(band, equity)
    print(
        f"banda de {band.days} días (Monte Carlo, H2 sin quiebra): p5 {band.p5:+.4%}, "
        f"p50 {band.p50:+.4%}, p95 {band.p95:+.4%}"
    )
    print(f"veredicto: {result.verdict.upper()} ({result.detail})")
    return 0


def _research_budget(data_dir: Path) -> int:
    from prometheus_platform.api import research_budget as rb  # noqa: PLC0415

    research = data_dir / "research"
    try:
        budget = rb.run(research)
    except FileNotFoundError as exc:
        print(f"ERROR falta un artefacto: {exc.filename}. Corre antes `pq research simulate`.")
        return 2
    path = rb.write(budget, research / "budget")
    result = budget.summary
    approved = ", ".join(result["estrategias_aprobadas"]) or "ninguna"
    print(f"estrategias aprobadas: {approved}; tope por exchange: {result['tope_por_exchange']}")
    for name, weight in result["presupuesto"].items():
        print(f"  {name}: {weight:.0%}")
    print(
        f"  efectivo al 4 %: {result['efectivo']:.0%} · retorno esperado "
        f"{result['retorno_esperado']:.2%} · CVaR95 {result['cvar95']:.2%} · resumen={path}"
    )
    return 0


def _research_exchanges(data_dir: Path) -> int:
    import json  # noqa: PLC0415

    from prometheus_platform.research import carry_evaluation as ce  # noqa: PLC0415
    from prometheus_platform.research.exchanges import compare  # noqa: PLC0415

    symbols = [s for group in ce.HYPOTHESES.values() for s in group]
    rows = compare(data_dir / "silver", symbols)
    out = data_dir / "research" / "exchanges"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "summary.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        if row["liquidaciones_comunes"] < 2:
            print(f"  {row['simbolo']} {row['exchange']}: {row.get('nota', '')}")
            continue
        print(
            f"  {row['simbolo']} {row['exchange']}: n={row['liquidaciones_comunes']}"
            f" mediana binance={row['mediana_binance']:.1%} otro={row['mediana_otro']:.1%}"
            f" correlación={row['correlacion']:.2f} otro paga más={row['otro_paga_mas']:.0%}"
        )
    print(f"resumen={path}")
    return 0


def _research_eda(data_dir: Path, figures: Path) -> int:
    from prometheus_platform.research.eda import (  # noqa: PLC0415
        correlation_matrix,
        describe_table,
        plot_correlation,
    )

    panel = _development_panel(data_dir)
    out = data_dir / "research" / "eda"
    out.mkdir(parents=True, exist_ok=True)
    table = describe_table(panel)
    table.write_csv(out / "describe.csv")
    corr = correlation_matrix(panel)
    corr.write_csv(out / "correlation.csv")
    plot_correlation(corr, figures / "correlacion-features.png")
    print(f"filas={panel.height} salida={out}")
    return 0


def _research_stats(data_dir: Path) -> int:
    from prometheus_platform.research.hypothesis_tests import (  # noqa: PLC0415
        run_validation,
        verdict,
        write_validation,
    )

    result = run_validation(data_dir)
    path = write_validation(result, data_dir / "research" / "stats")
    for test in (result.he1, result.he2):
        low, high = test.ci95_annualized
        print(
            f"{test.hypothesis}: p_HAC={test.p_hac:.4f} IC95=[{low:+.2%}, {high:+.2%}] anual"
            f" → {verdict(test.reject_h0, 'media')}"
        )
    he3 = result.he3
    print(
        f"HE3: Friedman p={he3.friedman_p:.2e} W={he3.kendall_w:.3f}; ANOVA p={he3.anova_p:.3f}"
        f" → {verdict(he3.reject_h0, 'grupo')}"
    )
    print(f"resultados en {path}")
    return 0


def _research_finance(data_dir: Path, doc: Path | None) -> int:
    from prometheus_platform.research.finance import (  # noqa: PLC0415
        render_markdown,
        run_finance,
        update_document,
        write_finance,
    )

    summary = run_finance(data_dir)
    path = write_finance(summary, data_dir / "research" / "finance")
    for e in summary.evaluaciones:
        if e["infraestructura"].startswith("Oracle") and e["capital"] == 1_000 and e["anios"] == 3:
            equilibrio = e["capital_equilibrio"]
            print(
                f"{e['escenario']}: r_P={e['retorno_anual']:.2%} VAN(3 años, 1.000 USD)="
                f"{e['van']:.2f} USD; capital de equilibrio="
                + ("no existe" if equilibrio is None else f"{equilibrio:,.0f} USD")
            )
    if doc is not None:
        update_document(doc, render_markdown(summary))
        print(f"bloque PQ-49 actualizado en {doc}")
    print(f"resultados en {path}")
    return 0


def _ledger(settings: Settings, familia: str, comando: str) -> TrialLedger:
    return TrialLedger(
        settings.research_ledger_dir,
        familia=familia,
        carril=settings.research_lane,
        autor=settings.research_author or git_author(),
        comando=comando,
    )


def _research(args: argparse.Namespace, settings: Settings, argv: Sequence[str]) -> int:
    """Cada ejecución deja su fila en el registro compartido **antes** de investigar (PQ-112)."""
    data_dir = settings.data_dir
    if args.study == "registro":
        return _research_ledger(args.action, settings)
    command = " ".join(["pq", *argv])
    if args.study == "carry":
        ledger = _ledger(settings, "carry", command)
        return _research_carry(data_dir, args.hypothesis, args.figures, ledger)
    if args.study == "trend":
        return _research_trend(data_dir, args.figures, _ledger(settings, "tendencia", command))
    holdouts = {"carry-holdout": ("carry", _research_carry_holdout)}
    holdouts["trend-holdout"] = ("tendencia", _research_trend_holdout)
    if args.study in holdouts:
        family, run_holdout = holdouts[args.study]
        ledger = _ledger(settings, family, command)
        return run_holdout(data_dir, args.figures, args.confirmo_un_solo_uso, ledger)
    if args.study == "funding-model":
        ledger = _ledger(settings, "modelo-funding", command)
        return _research_model(data_dir, args.figures, args.target_mode, ledger)
    # Descriptivos: no son ensayos (no eligen nada), pero la ejecución queda registrada.
    descriptive: dict[str, Callable[[], int]] = {
        "finance": lambda: _research_finance(data_dir, args.update_doc),
        "stats": lambda: _research_stats(data_dir),
        "exchanges": lambda: _research_exchanges(data_dir),
        "budget": lambda: _research_budget(data_dir),
        "eda": lambda: _research_eda(data_dir, args.figures),
        "simulate": lambda: _research_simulate(data_dir, args.figures, args.paths),
        "paper-banda": lambda: _research_paper_band(data_dir),
        "momentum-universo": _research_momentum_universe,
    }
    _ledger(settings, "descriptivo", command).log_execution(args.study)
    return descriptive[args.study]()


MOMENTUM_UNIVERSE_FILE = Path("docs/estrategias/03-momentum-transversal/universo.json")


def _research_momentum_universe() -> int:
    """Elige el universo del pre-registro §3 y lo publica con su comprobación; no es un ensayo."""
    import json  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    from prometheus_platform.adapters.data_vision_universe import (  # noqa: PLC0415
        list_usdm_symbols,
        monthly_quote_volume,
    )
    from prometheus_platform.research import momentum_universe as mu  # noqa: PLC0415

    december = date(2020, 12, 1)
    with httpx.Client(timeout=60) as client:
        listed = list_usdm_symbols(client)
        source = BinanceDataVisionSource(client)
        pool = mu.candidates(listed)
        with ThreadPoolExecutor(max_workers=4) as executor:  # sin saturar a Data Vision
            found = executor.map(lambda s: monthly_quote_volume(source, s, december), pool)
            volumes = {s: v for s, v in zip(pool, found, strict=True) if v is not None}
    universe = mu.select_universe(volumes)
    payload = {
        "regla": "pre-registro §3: perpetuos USDⓈ-M listados antes de 2021 (archivo diario de"
        " 2020-12 en Data Vision), sin stablecoins ni apalancados; top 15 por volumen en USDT"
        " de 2020-12",
        "fecha_seleccion": datetime.now(UTC).date().isoformat(),
        "simbolos_en_data_vision": len(listed),
        "candidatos_por_nombre": len(pool),
        "candidatos_con_datos_de_2020_12": universe.candidates,
        "universo": list(universe.symbols),
        "menor_volumen_10pb": list(universe.smallest),
        "volumen_usdt_2020_12": dict(sorted(volumes.items(), key=lambda kv: -kv[1])),
    }
    MOMENTUM_UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MOMENTUM_UNIVERSE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(listed)} símbolos en Data Vision; {universe.candidates} candidatos con 2020-12")
    print("universo:", ", ".join(universe.symbols))
    print("10 pb de slippage:", ", ".join(universe.smallest))
    print(f"escrito en {MOMENTUM_UNIVERSE_FILE}")
    return 0


def _research_ledger(action: str, settings: Settings) -> int:
    from prometheus_platform.adapters.mlflow_registry import historical_rows  # noqa: PLC0415

    directory = settings.research_ledger_dir
    if action == "resumen":
        for familia, n in sorted(counts(directory).items()):
            print(f"{familia}: N = {n}")
        return 0
    database = settings.data_dir / "mlflow" / "mlflow.db"
    if not database.exists():
        print(f"ERROR no hay MLflow local en {database}", file=sys.stderr)
        return 2
    autor = settings.research_author or git_author()
    history = historical_rows(database, carril=settings.research_lane, autor=autor)
    known = {r.etiquetas.get("mlflow_run_id") for r in read_rows(directory)} - {None}
    if action == "importar-mlflow":
        ledger = _ledger(settings, "", "importar-mlflow")
        new = [r for r in history if r.etiquetas["mlflow_run_id"] not in known]
        for row in new:
            ledger.append(row)
        print(f"importadas {len(new)} filas; ya estaban {len(history) - len(new)}")
        return 0
    missing = [r for r in history if r.etiquetas["mlflow_run_id"] not in known]
    for row in missing:
        print(f"falta en el registro: {row.familia} {row.hipotesis} {row.nombre} ({row.fecha})")
    print("registro y MLflow cuadran" if not missing else f"faltan {len(missing)} ensayos")
    return 0 if not missing else 1


def _report_inputs(data_dir: Path, out: Path) -> int:
    from prometheus_platform.api.report import build_report_inputs  # noqa: PLC0415

    missing = build_report_inputs(data_dir, Path.cwd(), out)
    for artifact in missing:
        print(f"aviso: falta el artefacto «{artifact}»; sus cifras quedan como n/d")
    print(f"entradas del informe en {out}")
    return 0


def _report_public(data_dir: Path, out: Path) -> int:
    from prometheus_platform.api.report import build_public_page  # noqa: PLC0415

    out.write_text(build_public_page(data_dir, Path.cwd(), SystemClock().now()), encoding="utf-8")
    print(f"página pública en {out}: revísala y súbela con su PR")
    return 0


def _paper_watchdog(args: argparse.Namespace, settings: Settings, notifier: Notifier | None) -> int:
    if args.interval <= 0:
        print("ERROR --interval debe ser positivo", file=sys.stderr)
        return 2
    dog = build_watchdog(
        settings=settings,
        notifier=notifier,
        clock=SystemClock(),
        paths=PaperPaths(settings.data_dir / PAPER_DIR),
    )
    pinger = _uptime_pinger(settings)
    try:
        while True:
            health = dog.check()
            print(f"runner de paper: {health.value}")
            if pinger is not None:  # PQ-97: si los pings dejan de llegar, el servicio externo avisa
                pinger.ping(healthy=health.value == "ok")
            if args.once:
                return 0 if health.value == "ok" else 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


def _uptime_pinger(settings: Settings) -> UptimePinger | None:
    if settings.healthcheck_url is None:
        return None
    from prometheus_platform.adapters.uptime_ping import UptimePinger  # noqa: PLC0415

    client = httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
    return UptimePinger(client, settings.healthcheck_url)


def _paper_bot(args: argparse.Namespace, settings: Settings, notifier: Notifier | None) -> int:
    from prometheus_platform.api.paper.bot import serve  # noqa: PLC0415

    del args  # el bot no tiene opciones: todo sale de la configuración
    return serve(settings, notifier, settings.data_dir / PAPER_DIR)


def _paper_backup(args: argparse.Namespace, settings: Settings, notifier: Notifier | None) -> int:
    from prometheus_platform.api.paper import backup  # noqa: PLC0415

    del notifier  # los fallos salen por el código de salida: los vigila el cron o systemd
    paper_dir = settings.data_dir / PAPER_DIR
    now = SystemClock().now()
    try:
        if args.backup_action == "keygen":
            public = backup.generate_identity(args.out)
            print(f"clave privada en {args.out}: guárdala fuera del servidor y no la compartas")
            print(f"clave pública (va en PQ_BACKUP_AGE_RECIPIENT del servidor): {public}")
        elif args.backup_action == "create":
            target = backup.create_backup(paper_dir, args.out, settings.backup_age_recipient, now)
            removed = backup.prune(args.out, timedelta(days=settings.backup_keep_days), now)
            print(f"respaldo: {target} ({len(removed)} viejos borrados)")
        else:
            names = backup.restore_backup(args.archive, args.identity, paper_dir, force=args.force)
            print(f"restaurados en {paper_dir}: {', '.join(names)}")
            print("arranca el runner: reconcilia el estado deseado con el bróker en su 1er ciclo")
    except (backup.BackupError, RunnerAlreadyRunningError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    return 0


def _paper_weekly_report(
    args: argparse.Namespace, settings: Settings, notifier: Notifier | None
) -> int:
    from prometheus_platform.adapters.notifiers import TelegramNotifier  # noqa: PLC0415
    from prometheus_platform.api.paper import weekly  # noqa: PLC0415
    from prometheus_platform.api.paper.report import (  # noqa: PLC0415
        build_view,
        last_complete_week,
        parse_iso_week,
        weekly_summary,
    )

    now = SystemClock().now()
    try:
        monday = parse_iso_week(args.week) if args.week else last_complete_week(now)
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    if args.send and notifier is None:
        print(
            "ERROR sin canal: configura PQ_TELEGRAM_BOT_TOKEN y PQ_TELEGRAM_CHAT_ID",
            file=sys.stderr,
        )
        return 1
    events = list(JsonlEventJournal(PaperPaths(settings.data_dir / PAPER_DIR).journal).replay())
    summary = weekly_summary(events, monday)
    out = settings.data_dir / "informes" / "paper" / summary.week
    weekly.build_inputs(
        summary, out, build_view(events).broker, _weekly_parity(summary, settings.data_dir)
    )
    print(f"entradas del informe {summary.week} en {out}")
    pdf = None
    if args.pdf:
        try:
            pdf = weekly.render_pdf(summary, out)
        except (weekly.WeeklyReportError, OSError, subprocess.SubprocessError) as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 2
        print(f"PDF en {pdf}")
    if not args.send or notifier is None:
        return 0
    alert = Alert(
        severity=AlertSeverity.INFO,
        title=f"informe semanal del paper trading {summary.week}",
        occurred_at=now,
        environment=settings.environment.value,
        details=summary.details(),
    )
    if pdf is not None and isinstance(notifier, TelegramNotifier):
        delivered = notifier.send_document(pdf, alert.render(settings.alert_tz))
    else:
        delivered = notifier.notify(alert)
    print(f"enviado: {'sí' if delivered else 'no'}")
    return 0 if delivered else 1


def _weekly_parity(summary: WeeklySummary, data_dir: Path) -> Parity | None:
    """Paridad con el backtest de H2; ``None`` (y un aviso) si falta su evaluación."""
    from prometheus_platform.api.dashboard import portfolio  # noqa: PLC0415
    from prometheus_platform.api.dashboard.artifacts import load_artifacts  # noqa: PLC0415
    from prometheus_platform.api.paper.weekly import parity  # noqa: PLC0415

    art = load_artifacts(data_dir)
    evaluation, returns = art.carry.get("H2"), art.carry_returns.get("H2")
    if evaluation is None or returns is None:
        print("aviso: falta la evaluación de H2; la paridad con el backtest queda como n/d")
        return None
    return parity(summary, portfolio.development_returns(returns, str(evaluation.get("selected"))))


def _paper_run(
    args: argparse.Namespace, settings: Settings, notifier: Notifier | None = None
) -> int:
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    paths = PaperPaths(paper_dir(settings.data_dir, args.broker))
    with http_client() as client:
        try:
            if not math.isfinite(args.theta) or args.interval <= 0:
                raise ValueError("--theta debe ser finito y --interval positivo")
            config = RunnerConfig(
                symbols=symbols,
                params=CarryParams(args.k, args.theta),
                drawdown_alert=Decimal(str(settings.paper_drawdown_alert)),
                carry_share=args.carry_share,
            )
            caps = _exchange_caps(args.exchange_cap)
            with single_instance(paths):
                runner = build(
                    settings=settings,
                    config=config,
                    client=client,
                    clock=SystemClock(),
                    paths=paths,
                    capital=args.capital,
                    notifier=notifier,
                    exchange_caps=caps,
                    market_data=args.market_data,
                    broker=args.broker,
                )
                print(
                    f"runner de paper: bróker {args.broker}, {','.join(symbols)}, "
                    f"{config.describe()}"
                )
                metrics = _start_metrics(paths, args.metrics_port)
                try:
                    healthy = runner.run(
                        interval_seconds=args.interval, max_ticks=1 if args.once else None
                    )
                finally:
                    if metrics is not None:
                        metrics.shutdown()
        except (ValueError, RunnerAlreadyRunningError) as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("runner detenido a mano (el estado queda en el diario y en el bróker)")
            return 0
    return 0 if healthy else 1


def _start_metrics(paths: PaperPaths, port: int) -> WSGIServer | None:
    """``/metrics`` del runner en 127.0.0.1 (PQ-71); ``None`` con el puerto 0."""
    if port <= 0:
        return None
    from prometheus_platform.api.paper.metrics import serve_metrics  # noqa: PLC0415

    server = serve_metrics(paths, port)
    print(f"métricas en http://127.0.0.1:{server.server_address[1]}/metrics")
    return server


def _exchange_caps(items: Sequence[str]) -> dict[Venue, Decimal]:
    caps = {}
    for item in items:
        name, sep, value = item.partition("=")
        try:
            venue = Venue(name.strip().upper())
            cap = Decimal(value)
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(
                f"--exchange-cap {item!r}: usa EXCHANGE=TOPE, p. ej. BINANCE=0.125"
            ) from exc
        if not sep or not cap.is_finite() or not Decimal(0) < cap <= 1:
            raise ValueError(f"--exchange-cap {item!r}: el tope va en (0, 1]")
        caps[venue] = cap
    return caps


def _decimal_arg(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except ArithmeticError as exc:
        raise argparse.ArgumentTypeError(f"no es un número: {text!r}") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError(f"debe ser positivo: {text!r}")
    return value


def _paper(args: argparse.Namespace, settings: Settings, notifier: Notifier | None) -> int:
    processes = {
        "run": _paper_run,
        "watchdog": _paper_watchdog,
        "bot": _paper_bot,
        "backup": _paper_backup,
        "weekly-report": _paper_weekly_report,
        "costes": cost_cli.costs_report,
        "muestreo-costes": cost_cli.sample_costs_command,
    }
    if args.action in processes:
        return processes[args.action](args, settings, notifier)
    paths = PaperPaths(paper_dir(settings.data_dir, args.broker))
    journal = JsonlEventJournal(paths.journal)
    if args.action == "status":
        return _paper_status(paths, journal)
    return _paper_kill(args, paths, journal)


def _paper_status(paths: PaperPaths, journal: JsonlEventJournal) -> int:
    state = KillSwitch(paths.kill_switch, SystemClock(), journal).state()
    print(
        "kill-switch: ARMADO (operación permitida)"
        if state is None
        else f"kill-switch: ACTIVADO {state}"
    )
    print(f"bandera: {paths.kill_switch.resolve()}")
    for strategy_id, flag in paths.strategy_kill_switches().items():
        detail = KillSwitch(flag, SystemClock(), journal).state()
        print(f"estrategia {strategy_id}: DETENIDA {detail}")
    return 0


def _paper_kill(args: argparse.Namespace, paths: PaperPaths, journal: JsonlEventJournal) -> int:
    """Kill-switch global o de una estrategia (``--strategy``, PQ-83)."""
    try:
        flag = paths.strategy_kill_switch(args.strategy) if args.strategy else paths.kill_switch
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    switch = KillSwitch(flag, SystemClock(), journal)
    scope = f" de la estrategia {args.strategy}" if args.strategy else ""
    if not args.reset:
        reason = f"{args.strategy}: {args.reason}" if args.strategy else args.reason
        tripped = switch.trip(reason, source="cli")
        print(
            f"kill-switch{scope} ACTIVADO"
            if tripped
            else f"el kill-switch{scope} ya estaba activado"
        )
        print(f"bandera: {switch.flag_path.resolve()}")
        print("el runner cancela las órdenes y cierra las posiciones en su próximo ciclo;")
        print("verifica con `pq paper status` y en Binance (órdenes abiertas)")
        return 0
    if not (args.confirm and args.by.strip()):
        print("para rearmar hacen falta --confirm y --by <nombre>", file=sys.stderr)
        return 2
    rearmed = switch.reset(args.by)
    print(
        f"kill-switch{scope} rearmado" if rearmed else f"el kill-switch{scope} no estaba activado"
    )
    return 0


def _monitor_drift(args: argparse.Namespace, settings: Settings, notifier: Notifier | None) -> int:
    """Corre los tres detectores; código 1 si alguno cruza su umbral (útil en cron)."""
    from prometheus_platform.api import drift  # noqa: PLC0415
    from prometheus_platform.api.dashboard import portfolio  # noqa: PLC0415
    from prometheus_platform.api.dashboard.artifacts import load_artifacts  # noqa: PLC0415
    from prometheus_platform.api.paper.report import build_view  # noqa: PLC0415
    from prometheus_platform.research.nowcast import tuned_params  # noqa: PLC0415

    data_dir = settings.data_dir
    report = drift.DriftReport(generated_at=SystemClock().now())
    try:
        panels = drift.load_panels(data_dir)
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        report.skipped["datos y modelo"] = f"no se pudo leer silver ({type(exc).__name__})"
        panels = {}
    if panels:
        drift.check_data(report, panels)
        try:
            drift.check_model(report, panels, tuned_params(data_dir))
        except (OSError, ValueError) as exc:
            report.skipped["modelo"] = f"falta el estudio del modelo ({type(exc).__name__})"
    art = load_artifacts(data_dir)
    evaluation, returns = art.carry.get("H2"), art.carry_returns.get("H2")
    daily = (
        portfolio.development_returns(returns, str(evaluation.get("selected")))
        if evaluation is not None and returns is not None
        else None
    )
    view = build_view(JsonlEventJournal(PaperPaths(data_dir / PAPER_DIR).journal).replay())
    drift.check_performance(report, view, daily)

    path = drift.write_report(report, data_dir / "monitoring" / "drift")
    for line in drift.summary_lines(report):
        print(line)
    print(f"informe en {path}")
    alerts = report.alerts(settings.environment.value)
    for found in alerts:
        alert = found
        if args.ticket:
            try:
                alert = replace(
                    found, details={**found.details, "ticket": drift.open_ticket(found)}
                )
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                print(f"ERROR no se pudo abrir el issue: {exc}", file=sys.stderr)
        print(f"ALERTA {alert.title}: {alert.details.get('ticket', 'sin ticket')}")
        if args.send and notifier is not None:
            notifier.notify(alert)
    if not alerts:
        print("sin drift: ningún detector cruzó su umbral")
    return 1 if alerts else 0


def _alert_test(notifier: Notifier | None, environment: str) -> int:
    if notifier is None:
        print("sin canal de alertas: configura PQ_TELEGRAM_BOT_TOKEN y PQ_TELEGRAM_CHAT_ID")
        return 1
    alert = Alert(
        severity=AlertSeverity.WARNING,
        title="alerta de prueba",
        occurred_at=SystemClock().now(),
        environment=environment,
        details={"origen": "pq alert test"},
    )
    delivered = notifier.notify(alert)
    print(f"canal={type(notifier).__name__} entregada={'sí' if delivered else 'no'}")
    return 0 if delivered else 1


def _ingest(args: argparse.Namespace, bronze_root: Path) -> int:
    clock = SystemClock()
    if args.source == "api":
        return _ingest_api(args, bronze_root, clock)
    if args.source in EXCHANGE_SOURCES:
        return _ingest_exchange(args, bronze_root, clock)
    if args.start is None:
        print("ERROR --start (AAAA-MM) es obligatorio con --source data-vision", file=sys.stderr)
        return 2
    end = args.end or last_complete_month(clock.now().date())
    if args.dataset == "klines":
        refs = monthly_klines(Market(args.market), args.symbol, args.interval, args.start, end)
    else:
        refs = monthly_funding(args.symbol, args.start, end)

    store = ParquetBronzeStore(bronze_root, source=SOURCE_NAME, clock=clock)
    with http_client() as client:
        report = ingest(refs, BinanceDataVisionSource(client), store)
    _print_report(report)
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    settings = load_settings()
    notifier = notifier_from_settings(settings)
    configure_logging(settings, notifier=notifier)
    data_dir = settings.data_dir
    handlers: dict[str, Callable[[], int]] = {
        "ingest": lambda: _ingest(args, data_dir / "bronze"),
        "silver": lambda: _silver_build(data_dir, args.symbol, args.interval, args.exchange),
        "gold": lambda: _gold(args.action, data_dir, getattr(args, "out", GOLD_DOCS)),
        "research": lambda: _research(args, settings, argv),
        "report": lambda: (
            _report_inputs(data_dir, args.out)
            if args.action == "inputs"
            else _report_public(data_dir, args.out)
        ),
        "paper": lambda: _paper(args, settings, notifier),
        "monitor": lambda: _monitor_drift(args, settings, notifier),
        "alert": lambda: _alert_test(notifier, settings.environment.value),
        "polymarket": lambda: polymarket_cli.run(args, data_dir, http_client),
    }
    return handlers[args.command]()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
