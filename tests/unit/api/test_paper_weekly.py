"""Informe semanal del paper trading (PQ-85): cifras de la semana, envío y PDF."""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import numpy as np
import polars as pl
import pytest
from pydantic import SecretStr
from tests.unit.api.test_paper_monitoring import runner_with
from tests.unit.api.test_paper_runner import AFTER_LATENCY, HIGH, T0, FakeMarket, Rig, settlements

from prometheus_platform.adapters.in_memory import FixedClock, RecordingNotifier
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.notifiers import TelegramNotifier
from prometheus_platform.api.cli import main
from prometheus_platform.api.dashboard.artifacts import Artifacts
from prometheus_platform.api.paper import weekly
from prometheus_platform.api.paper.report import (
    iso_week,
    last_complete_week,
    parse_iso_week,
    weekly_summary,
)
from prometheus_platform.domain.alerts import AlertSeverity
from prometheus_platform.domain.events import (
    DomainEvent,
    FundingSettled,
    KillSwitchTripped,
    OrderFilled,
    OrderSubmitted,
    PortfolioValued,
    RiskLimitBreached,
    RunnerStarted,
)
from prometheus_platform.domain.model import Side
from prometheus_platform.strategies.carry import spot_instrument

WEEKLY = "prometheus_platform.api.paper.weekly"
MONDAY = date(2026, 11, 16)  # semana ISO 2026-W47
WEEK_START = datetime(2026, 11, 16, tzinfo=UTC)
SPOT = spot_instrument("SOLUSDT")
D = Decimal


def valued(at: datetime, equity: str, price: str) -> PortfolioValued:
    return PortfolioValued(
        occurred_at=at,
        equity=D(equity),
        cash=D(0),
        gross_notional=D(price),
        marks=PortfolioValued.encode_marks({SPOT: D(price)}),
    )


def buy(at: datetime, order_id: str, price: str, fee: str) -> list[DomainEvent]:
    return [
        OrderSubmitted(
            occurred_at=at, client_order_id=order_id, instrument=SPOT, side=Side.BUY, quantity=D(1)
        ),
        OrderFilled(
            occurred_at=at,
            client_order_id=order_id,
            fill_price=D(price),
            fill_quantity=D(1),
            fee=D(fee),
            slippage=D("0.01"),
        ),
    ]


def settled(at: datetime, amount: str) -> FundingSettled:
    return FundingSettled(
        occurred_at=at,
        symbol="SOLUSDT",
        funding_time=at,
        rate=D("0.0001"),
        interval_hours=8,
        amount=D(amount),
        action="mantener",
        s_k="",
        target_open=True,
        was_open=True,
        rebalance=False,
    )


def journal_events() -> list[DomainEvent]:
    before = WEEK_START - timedelta(days=2)
    inside = WEEK_START + timedelta(days=2)
    after = WEEK_START + timedelta(days=8)
    return [
        RunnerStarted(
            occurred_at=before,
            broker="simulado",
            strategy_id="carry-h2",
            symbols="SOLUSDT",
            params="",
        ),
        *buy(before, "c-entrada-1", "100", "0.10"),
        valued(before, "1000", "100"),
        settled(before, "0.50"),
        # --- semana 2026-W47 ---
        *buy(inside, "c-entrada-2", "110", "0.20"),
        settled(inside, "0.30"),
        valued(inside, "1100", "110"),
        valued(inside + timedelta(hours=1), "990", "105"),
        RiskLimitBreached(occurred_at=inside, rule="max_drawdown", detail="x"),
        KillSwitchTripped(occurred_at=inside, reason="prueba", source="cli"),
        valued(WEEK_START + timedelta(days=6, hours=23), "1050", "120"),
        # --- semana siguiente: no cuenta ---
        *buy(after, "c-entrada-3", "130", "0.40"),
        settled(after, "9"),
        valued(after, "1200", "130"),
    ]


# --- semanas ISO ----------------------------------------------------------------------------


def test_the_last_complete_week_ends_on_the_previous_sunday() -> None:
    assert last_complete_week(datetime(2026, 11, 25, 9, tzinfo=UTC)) == MONDAY
    assert last_complete_week(datetime(2026, 11, 23, 0, 30, tzinfo=UTC)) == MONDAY
    assert last_complete_week(datetime(2026, 11, 22, 23, 59, tzinfo=UTC)) == date(2026, 11, 9)


def test_iso_week_labels_round_trip() -> None:
    assert iso_week(MONDAY) == "2026-W47"
    assert parse_iso_week("2026-W47") == MONDAY
    assert parse_iso_week("2027-W01") == date(2027, 1, 4)
    with pytest.raises(ValueError, match="AAAA-Www"):
        parse_iso_week("2026-47")


# --- cifras de la semana --------------------------------------------------------------------


def test_weekly_summary_counts_only_events_inside_the_week() -> None:
    summary = weekly_summary(journal_events(), MONDAY)

    assert (summary.week, summary.start, summary.end) == ("2026-W47", MONDAY, date(2026, 11, 22))
    assert summary.orders == 1
    assert summary.funding == D("0.30")
    assert summary.fees == D("0.20")
    assert summary.slippage == D("0.01")
    assert summary.breaches == 1
    assert summary.kill_trips == 1
    # la equity de partida es la del cierre de la semana anterior
    assert (summary.equity_start, summary.equity_end) == (D(1000), D(1050))
    assert summary.change == D("0.05")
    assert summary.max_drawdown == D(1) - D(990) / D(1100)
    assert [v for _, v in summary.curve] == [D(1000), D(1100), D(990), D(1050)]


def test_strategy_pnl_of_the_week_is_the_change_of_the_cumulative_pnl() -> None:
    (row,) = weekly_summary(journal_events(), MONDAY).strategies

    # semana anterior: 1 SOL a 100, marca 100, funding 0,50 → acumulado 0,40
    # al cierre de la semana: 2 SOL (100 y 110), marca 120, funding 0,80 → acumulado 30,50
    assert (row.strategy, row.exchange) == ("carry-h2", "BINANCE")
    assert row.pnl == D("30.10")
    assert row.funding == D("0.30")
    assert row.costs == D("0.21")
    assert row.exposure == D(240)


def test_a_week_without_events_says_so_instead_of_inventing_numbers() -> None:
    summary = weekly_summary(journal_events(), date(2026, 10, 5))

    assert summary.orders == 0
    assert summary.equity_end is None
    assert summary.change is None
    details = summary.details()
    assert details["equity al cierre"] == "n/d"
    assert details["variación semanal"] == "n/d"


def test_details_are_plain_text_for_telegram() -> None:
    details = weekly_summary(journal_events(), MONDAY).details()

    assert details["semana"] == "2026-W47 (2026-11-16 a 2026-11-22, UTC)"
    assert details["variación semanal"] == "+5.000%"
    assert details["caída máxima en la semana"] == "10.00%"
    assert details["kill-switch activado"] == "1 vez"
    assert details["PnL carry-h2 (BINANCE)"] == "+30.10 USD"


# --- envío automático desde el runner -------------------------------------------------------


@pytest.fixture
def sunday(tmp_path: Path) -> Rig:
    """El rig del runner el domingo T0 a las 17:01, con tres liquidaciones altas."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    return Rig(tmp_path, clock, market)


def test_the_runner_sends_the_weekly_summary_when_sunday_ends(sunday: Rig) -> None:
    rig = sunday
    notifier = RecordingNotifier()
    runner = runner_with(rig, notifier)
    runner.tick()  # T0 es domingo

    rig.at(T0 + timedelta(days=1, minutes=1))  # lunes
    runner.tick()

    daily, weekly_alert = notifier.alerts
    assert daily.title.startswith("resumen diario")
    assert weekly_alert.severity is AlertSeverity.INFO
    assert weekly_alert.title == "resumen semanal del paper trading (simulado)"
    assert weekly_alert.details["semana"].startswith("2026-W44")
    assert weekly_alert.details["órdenes ejecutadas"] == "2"


def test_other_days_send_only_the_daily_summary(sunday: Rig) -> None:
    rig = sunday
    notifier = RecordingNotifier()
    runner = runner_with(rig, notifier)
    rig.at(T0 + timedelta(days=1))  # lunes
    runner.tick()

    rig.at(T0 + timedelta(days=2, minutes=1))  # martes
    runner.tick()

    summaries = [a.title for a in notifier.alerts if a.title.startswith("resumen")]
    assert summaries == ["resumen diario del paper trading (simulado)"]


# --- entradas del PDF y CLI -----------------------------------------------------------------


@pytest.fixture
def lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    journal = JsonlEventJournal(tmp_path / "paper" / "diario.jsonl")
    for event in journal_events():
        journal.append(event)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PQ_ENVIRONMENT", "dev")
    return tmp_path


def test_build_inputs_writes_figures_tables_and_the_template(tmp_path: Path) -> None:
    out = tmp_path / "W47"
    weekly.build_inputs(weekly_summary(journal_events(), MONDAY), out, "simulado")

    values = json.loads((out / "_semana.yml").read_text(encoding="utf-8"))["s"]
    assert values["semana"] == "2026-W47"
    assert values["variacion"] == "+5.000%"
    assert values["broker"] == "simulado"
    assert "| carry-h2 | BINANCE |" in (out / "_tablas" / "estrategias.md").read_text("utf-8")
    assert (out / "_img" / "equity.png").stat().st_size > 0
    assert (out / "semana.qmd").read_text("utf-8").startswith("---")


def test_build_inputs_without_valuations_skips_the_figure(tmp_path: Path) -> None:
    out = tmp_path / "vacia"
    weekly.build_inputs(weekly_summary([], MONDAY), out, None)

    assert not (out / "_img" / "equity.png").exists()
    assert json.loads((out / "_semana.yml").read_text("utf-8"))["s"]["tiene_curva"] is False
    assert "Sin datos" in (out / "_tablas" / "estrategias.md").read_text("utf-8")


def test_cli_writes_the_inputs_of_the_requested_week(
    lake: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["paper", "weekly-report", "--week", "2026-W47"]) == 0

    out = lake / "informes" / "paper" / "2026-W47"
    assert (out / "_semana.yml").exists()
    assert "2026-W47" in capsys.readouterr().out


def test_cli_rejects_a_malformed_week(lake: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["paper", "weekly-report", "--week", "47"]) == 2
    assert "AAAA-Www" in capsys.readouterr().err


def test_cli_pdf_runs_quarto_and_reports_its_failure(
    lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[Sequence[str]] = []

    def fake_run(cmd: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out = Path(str(kwargs["cwd"]))
        (out / "semana.pdf").write_bytes(b"%PDF-1.7")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(f"{WEEKLY}.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(f"{WEEKLY}.subprocess.run", fake_run)
    assert main(["paper", "weekly-report", "--week", "2026-W47", "--pdf"]) == 0
    assert calls == [["quarto", "render", "semana.qmd", "--to", "typst"]]
    pdf = lake / "informes" / "paper" / "2026-W47" / "informe-paper-2026-W47.pdf"
    assert pdf.read_bytes() == b"%PDF-1.7"

    monkeypatch.setattr(f"{WEEKLY}.shutil.which", lambda name: None)
    assert main(["paper", "weekly-report", "--week", "2026-W47", "--pdf"]) == 2
    assert "Quarto" in capsys.readouterr().err


def test_cli_send_without_a_channel_fails_clearly(
    lake: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["paper", "weekly-report", "--week", "2026-W47", "--send"]) == 1
    assert "PQ_TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


# --- Telegram: envío del PDF ----------------------------------------------------------------

TOKEN = "123456:" + "ABC-falso"


def test_telegram_sends_a_document_with_its_caption(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    pdf = tmp_path / "informe.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    notifier = TelegramNotifier(
        httpx.Client(transport=httpx.MockTransport(handler)), SecretStr(TOKEN), "42"
    )

    assert notifier.send_document(pdf, "informe semanal 2026-W47")
    [request] = seen
    assert request.url.path.endswith("/sendDocument")
    body = request.read()
    assert b'name="chat_id"' in body
    assert b"informe semanal 2026-W47" in body
    assert b'filename="informe.pdf"' in body


def test_telegram_document_failures_never_leak_the_token(tmp_path: Path) -> None:
    fallback = io.StringIO()
    pdf = tmp_path / "informe.pdf"
    pdf.write_bytes(b"%PDF-1.7")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no llega a {request.url}")

    for handler in (down, lambda r: httpx.Response(413, json={"ok": False})):
        notifier = TelegramNotifier(
            httpx.Client(transport=httpx.MockTransport(handler)),
            SecretStr(TOKEN),
            "42",
            fallback=fallback,
        )
        assert not notifier.send_document(pdf, "x")
    assert notifier.send_document(tmp_path / "no-existe.pdf", "x") is False
    assert TOKEN not in fallback.getvalue()
    assert "HTTP 413" in fallback.getvalue()


# --- incidentes, costes frente al modelo y paridad con el backtest ---------------------------


def test_incidents_of_the_week_list_breaches_and_kill_switch_changes() -> None:
    inside = WEEK_START + timedelta(days=2)
    summary = weekly_summary(journal_events(), MONDAY)

    assert [(i.at, i.kind, i.detail) for i in summary.incidents] == [
        (inside, "riesgo", "max_drawdown: x"),
        (inside, "kill-switch", "activado por cli: prueba"),
    ]
    assert weekly_summary(journal_events(), MONDAY + timedelta(days=7)).incidents == ()


def test_costs_are_compared_with_the_model_of_each_symbol() -> None:
    (row,) = weekly_summary(journal_events(), MONDAY).costs

    # 1 SOL de contado a 110: el modelo de las alts cobra 10 pb de comisión y 5 pb de slippage
    assert row.leg == "contado"
    assert row.notional == D(110)
    assert (row.fee, row.fee_model) == (D("0.20"), D("0.1100"))
    assert (row.slippage, row.slippage_model) == (D("0.01"), D("0.0550"))
    details = weekly_summary(journal_events(), MONDAY).details()
    assert details["costes reales / modelo"] == "1.27x"


def test_without_fills_there_is_no_cost_ratio() -> None:
    assert (
        weekly_summary(journal_events(), date(2026, 10, 5)).details()["costes reales / modelo"]
        == "n/d"
    )


def test_parity_places_the_week_inside_or_outside_the_backtest_band() -> None:
    summary = weekly_summary(journal_events(), MONDAY)  # la semana rindió +5 %
    calm = np.full(200, 0.0001)  # el backtest esperaba ~+0,07 % por semana

    parity = weekly.parity(summary, calm)

    assert parity is not None
    assert parity.paper == D("0.05")
    assert parity.p5 == pytest.approx(1.0001**7 - 1)
    assert parity.p95 == pytest.approx(1.0001**7 - 1)
    assert parity.verdict == "por encima de la banda"
    assert weekly.parity(summary, np.full(5, 0.0001)) is None  # muy poca historia
    assert weekly.parity(weekly_summary([], MONDAY), calm) is None  # sin variación


def test_inputs_include_costs_incidents_and_parity(tmp_path: Path) -> None:
    summary = weekly_summary(journal_events(), MONDAY)
    out = tmp_path / "W47"
    weekly.build_inputs(summary, out, "simulado", weekly.parity(summary, np.full(200, 0.0001)))

    values = json.loads((out / "_semana.yml").read_text("utf-8"))["s"]
    assert values["paridad"] == "por encima de la banda"
    assert values["costes_ratio"] == "1.27x"
    assert "| contado | 110.00 |" in (out / "_tablas" / "costes.md").read_text("utf-8")
    assert "max_drawdown: x" in (out / "_tablas" / "incidentes.md").read_text("utf-8")

    weekly.build_inputs(weekly_summary([], MONDAY), out, None, None)
    values = json.loads((out / "_semana.yml").read_text("utf-8"))["s"]
    assert values["paridad"].startswith("n/d")
    assert "Sin incidentes" in (out / "_tablas" / "incidentes.md").read_text("utf-8")


def test_cli_uses_the_h2_development_returns_for_parity(
    lake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    days = [date(2023, 1, 1) + timedelta(days=i) for i in range(200)]
    art = Artifacts(
        carry={"H2": {"selected": "k3"}},
        carry_returns={"H2": pl.DataFrame({"date": [str(d) for d in days], "k3": [0.0001] * 200})},
    )
    monkeypatch.setattr(
        "prometheus_platform.api.dashboard.artifacts.load_artifacts", lambda data_dir: art
    )

    assert main(["paper", "weekly-report", "--week", "2026-W47"]) == 0

    out = lake / "informes" / "paper" / "2026-W47" / "_semana.yml"
    assert json.loads(out.read_text("utf-8"))["s"]["paridad"] == "por encima de la banda"
