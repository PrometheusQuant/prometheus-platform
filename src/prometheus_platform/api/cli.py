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
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.binance_rest import SOURCE_NAME as API_SOURCE_NAME
from prometheus_platform.adapters.binance_rest import BinanceRestSource, day_refs
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.notifiers import notifier_from_settings
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.api.paper.compose import (
    PaperPaths,
    RunnerAlreadyRunningError,
    build,
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
from prometheus_platform.data_platform.silver import SilverValidationError, build_symbol
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.datasets import ArchiveRef, DatasetKind, Granularity, Market
from prometheus_platform.domain.ports import Notifier
from prometheus_platform.ops.logging import configure_logging
from prometheus_platform.ops.settings import Settings, load_settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.research.carry_evaluation import HYPOTHESES
from prometheus_platform.strategies.carry import H2_PARAMS

SOURCE_NAME = "binance_data_vision"


GOLD_DOCS = Path("docs/arquitectura/modelo-gold.md")
PAPER_DIR = "paper"


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
    return parser


Commands = Any  # argparse._SubParsersAction no es público


def _add_ingest(commands: Commands) -> None:
    ingest_cmd = commands.add_parser("ingest", help="Ingesta bronze desde Binance")
    ingest_cmd.add_argument(
        "--source",
        choices=["data-vision", "api"],
        default="data-vision",
        help="data-vision: meses publicados (auditados); api: días recientes por la API pública",
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
        "stats", help="Validación estadística de la optimización: t, ANOVA, Friedman (cap. 7.4)"
    )
    finance = studies.add_parser(
        "finance", help="Costes cotizados, VAN, TIR y capital de equilibrio (cap. 8.3-8.4)"
    )
    finance.add_argument(
        "--update-doc", type=Path, help="reescribe el bloque PQ-49 de este documento Markdown"
    )


def _add_operations(commands: Commands) -> None:
    report = commands.add_parser("report", help="Informe ejecutivo en Quarto (PQ-39)")
    report_actions = report.add_subparsers(dest="action", required=True)
    inputs = report_actions.add_parser(
        "inputs", help="Escribe cifras, tablas y figuras del informe"
    )
    inputs.add_argument("--out", type=Path, default=Path("reports/storytelling"))

    paper = commands.add_parser("paper", help="Paper trading: kill-switch y estado (PQ-53)")
    paper_actions = paper.add_subparsers(dest="action", required=True)
    kill = paper_actions.add_parser("kill", help="Activa (o rearma) el kill-switch")
    kill.add_argument("--reason", default="activado a mano por CLI")
    kill.add_argument("--reset", action="store_true", help="rearmar la operación")
    kill.add_argument("--confirm", action="store_true", help="obligatorio con --reset")
    kill.add_argument("--by", default="", help="quién rearma (obligatorio con --reset)")
    paper_actions.add_parser("status", help="Estado del kill-switch")
    run = paper_actions.add_parser(
        "run", help="Runner del carry H2 con el bróker simulado y datos en vivo (PQ-54)"
    )
    run.add_argument("--once", action="store_true", help="un solo ciclo y termina")
    run.add_argument("--interval", type=float, default=60.0, help="segundos entre ciclos")
    run.add_argument("--capital", type=_decimal_arg, default=Decimal(1000), help="USD iniciales")
    run.add_argument("--symbols", default=",".join(HYPOTHESES["H2"]))
    run.add_argument("--k", type=int, default=H2_PARAMS.k)
    run.add_argument("--theta", type=float, default=H2_PARAMS.theta)

    alert = commands.add_parser("alert", help="Canal de alertas (PQ-38)")
    alert_actions = alert.add_subparsers(dest="action", required=True)
    alert_actions.add_parser("test", help="Envía una alerta de prueba por el canal configurado")


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


def _silver_build(data_dir: Path, symbol: str, interval: str) -> int:
    try:
        reports = build_symbol(data_dir, symbol, interval)
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


def _research_model(data_dir: Path, figures: Path, target_mode: str) -> int:
    from prometheus_platform.adapters.mlflow_registry import MlflowRegistry  # noqa: PLC0415
    from prometheus_platform.research.carry_evaluation import TrialRecord  # noqa: PLC0415
    from prometheus_platform.research.funding_model import run_study  # noqa: PLC0415
    from prometheus_platform.research.reporting import plot_roc, write_model_study  # noqa: PLC0415

    study = run_study(_development_panel(data_dir), target_mode=target_mode)
    tags = {"target_mode": target_mode, "period": "desarrollo"}
    registry = MlflowRegistry(data_dir / "mlflow" / "mlflow.db", "funding-model")
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


def _research(args: argparse.Namespace, data_dir: Path) -> int:
    if args.study == "finance":
        return _research_finance(data_dir, args.update_doc)
    if args.study == "stats":
        return _research_stats(data_dir)
    if args.study == "eda":
        return _research_eda(data_dir, args.figures)
    if args.study == "simulate":
        return _research_simulate(data_dir, args.figures, args.paths)
    if args.study == "funding-model":
        return _research_model(data_dir, args.figures, args.target_mode)
    return _research_carry(data_dir, args.hypothesis, args.figures)


def _report_inputs(data_dir: Path, out: Path) -> int:
    from prometheus_platform.api.report import build_report_inputs  # noqa: PLC0415

    missing = build_report_inputs(data_dir, Path.cwd(), out)
    for artifact in missing:
        print(f"aviso: falta el artefacto «{artifact}»; sus cifras quedan como n/d")
    print(f"entradas del informe en {out}")
    return 0


def _paper_run(args: argparse.Namespace, settings: Settings) -> int:
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    paths = PaperPaths(settings.data_dir / PAPER_DIR)
    with http_client() as client:
        try:
            if not math.isfinite(args.theta) or args.interval <= 0:
                raise ValueError("--theta debe ser finito y --interval positivo")
            config = RunnerConfig(symbols=symbols, params=CarryParams(args.k, args.theta))
            with single_instance(paths):
                runner = build(
                    settings=settings,
                    config=config,
                    client=client,
                    clock=SystemClock(),
                    paths=paths,
                    capital=args.capital,
                )
                print(f"runner de paper: bróker simulado, {','.join(symbols)}, {config.describe()}")
                healthy = runner.run(
                    interval_seconds=args.interval, max_ticks=1 if args.once else None
                )
        except (ValueError, RunnerAlreadyRunningError) as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("runner detenido a mano (el estado queda en el diario y en el bróker)")
            return 0
    return 0 if healthy else 1


def _decimal_arg(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except ArithmeticError as exc:
        raise argparse.ArgumentTypeError(f"no es un número: {text!r}") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError(f"debe ser positivo: {text!r}")
    return value


def _paper(args: argparse.Namespace, settings: Settings) -> int:
    if args.action == "run":
        return _paper_run(args, settings)
    paths = PaperPaths(settings.data_dir / PAPER_DIR)
    switch = KillSwitch(paths.kill_switch, SystemClock(), JsonlEventJournal(paths.journal))
    if args.action == "status":
        state = switch.state()
        print(
            "kill-switch: ARMADO (operación permitida)"
            if state is None
            else f"kill-switch: ACTIVADO {state}"
        )
        print(f"bandera: {switch.flag_path.resolve()}")
        return 0
    if not args.reset:
        tripped = switch.trip(args.reason, source="cli")
        print("kill-switch ACTIVADO" if tripped else "el kill-switch ya estaba activado")
        print(f"bandera: {switch.flag_path.resolve()}")
        print("el runner cancela las órdenes y cierra las posiciones en su próximo ciclo;")
        print("verifica con `pq paper status` y en Binance (órdenes abiertas)")
        return 0
    if not (args.confirm and args.by.strip()):
        print("para rearmar hacen falta --confirm y --by <nombre>", file=sys.stderr)
        return 2
    print("kill-switch rearmado" if switch.reset(args.by) else "el kill-switch no estaba activado")
    return 0


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
    args = build_parser().parse_args(argv)
    settings = load_settings()
    notifier = notifier_from_settings(settings)
    configure_logging(settings, notifier=notifier)
    data_dir = settings.data_dir
    handlers: dict[str, Callable[[], int]] = {
        "ingest": lambda: _ingest(args, data_dir / "bronze"),
        "silver": lambda: _silver_build(data_dir, args.symbol, args.interval),
        "gold": lambda: _gold(args.action, data_dir, getattr(args, "out", GOLD_DOCS)),
        "research": lambda: _research(args, data_dir),
        "report": lambda: _report_inputs(data_dir, args.out),
        "paper": lambda: _paper(args, settings),
        "alert": lambda: _alert_test(notifier, settings.environment.value),
    }
    return handlers[args.command]()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
