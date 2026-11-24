"""Monitoreo de drift (PQ-86): detectores sobre datos cargados, tickets y CLI."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api import drift
from prometheus_platform.api.cli import main
from prometheus_platform.api.dashboard.artifacts import Artifacts
from prometheus_platform.api.paper.report import build_view
from prometheus_platform.domain.alerts import Alert
from prometheus_platform.domain.events import PortfolioValued
from prometheus_platform.domain.protocol import HOLDOUT_END
from prometheus_platform.research.funding_model import FEATURES, TARGET

RNG = np.random.default_rng(3)
DEV_START = datetime(2021, 1, 1, tzinfo=UTC)
LIVE_START = HOLDOUT_END + timedelta(days=1)
NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)


def panel(start: datetime, n: int, *, shift: float = 0.0, flip: bool = False) -> pl.DataFrame:
    """Liquidaciones sintéticas: una de cada cuatro en régimen alto (anualizado ≈ 40 %)."""
    base = np.where(np.arange(n) % 4 == 0, 0.40, 0.05) + shift
    data = {name: base + RNG.normal(0, 0.01, n) for name in FEATURES}
    data["annualized"] = base + RNG.normal(0, 0.01, n)
    data["funding_interval_hours"] = np.full(n, 8.0)
    target = np.where(np.arange(n) % 4 == 0, 0.05, 0.40) if flip else base
    data[TARGET] = target + RNG.normal(0, 0.01, n)
    times = [start + timedelta(hours=8 * i) for i in range(n)]
    return pl.DataFrame(data).with_columns(pl.Series("funding_time", times))


def symbol_panel(*, live_rows: int = 120, shift: float = 0.0, flip: bool = False) -> pl.DataFrame:
    return pl.concat(
        [panel(DEV_START, 900), panel(LIVE_START, live_rows, shift=shift, flip=flip)],
        how="diagonal_relaxed",
    )


# --- datos ------------------------------------------------------------------------------------


def test_data_drift_alerts_only_for_the_symbol_that_moved() -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_data(report, {"BTCUSDT": symbol_panel(), "SOLUSDT": symbol_panel(shift=0.5)})

    by_symbol = {d.symbol: d for d in report.data}
    assert not by_symbol["BTCUSDT"].alert
    assert by_symbol["SOLUSDT"].alert
    (alert,) = report.alerts("paper")
    assert alert.title == "drift de datos"
    assert set(alert.details) >= {"SOLUSDT", "umbral", "acción", "runbook"}
    assert "PDCA" in alert.details["acción"]


def test_data_drift_skips_symbols_without_enough_live_data() -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_data(report, {"XRPUSDT": symbol_panel(live_rows=10)})

    assert report.data == []
    assert "10 liquidaciones" in report.skipped["datos XRPUSDT"]


def test_the_holdout_never_enters_the_reference_nor_the_live_sample() -> None:
    holdout = panel(datetime(2025, 1, 1, tzinfo=UTC), 300, shift=5.0)  # valores imposibles
    report = drift.DriftReport(generated_at=NOW)
    drift.check_data(
        report, {"BTCUSDT": pl.concat([symbol_panel(), holdout], how="diagonal_relaxed")}
    )

    (result,) = report.data
    assert result.n_reference == 900
    assert result.n_live == 120
    assert not result.alert


# --- modelo -----------------------------------------------------------------------------------


def test_a_model_that_still_works_is_well_calibrated() -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_model(report, {"BTCUSDT": symbol_panel()}, {"max_depth": 4})

    assert report.model is not None
    assert report.model.n == 120
    assert not report.model.alert
    assert report.alerts("paper") == []


def test_a_model_whose_relation_flipped_crosses_the_ece_threshold() -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_model(report, {"BTCUSDT": symbol_panel(flip=True)}, {"max_depth": 4})

    assert report.model is not None
    assert report.model.alert
    (alert,) = report.alerts("paper")
    assert alert.title == "drift de modelo"
    assert alert.details["liquidaciones"] == "120"


def test_the_model_is_not_evaluated_without_live_outcomes() -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_model(report, {"BTCUSDT": symbol_panel(live_rows=5)}, {"max_depth": 4})

    assert report.model is None
    assert "modelo" in report.skipped


# --- desempeño --------------------------------------------------------------------------------


def valuations(path: Path, equities: Sequence[float]) -> None:
    journal = JsonlEventJournal(path)
    start = datetime(2026, 11, 13, tzinfo=UTC)
    for day, equity in enumerate(equities):
        journal.append(
            PortfolioValued(
                occurred_at=start + timedelta(days=day),
                equity=Decimal(str(equity)),
                cash=Decimal(0),
                gross_notional=Decimal(0),
            )
        )


CALM = np.random.default_rng(11).normal(0.0002, 0.002, 300)  # ~0,2 % diario


def test_performance_inside_the_band_does_not_alert(tmp_path: Path) -> None:
    valuations(tmp_path / "d.jsonl", [1000 * 1.0001**d for d in range(11)])
    report = drift.DriftReport(generated_at=NOW)
    drift.check_performance(
        report, build_view(JsonlEventJournal(tmp_path / "d.jsonl").replay()), CALM
    )

    assert report.performance is not None
    assert report.performance.days == 10
    assert not report.performance.alert


def test_a_paper_crash_is_outside_the_band(tmp_path: Path) -> None:
    valuations(tmp_path / "d.jsonl", [1000, 990, 950, 900])
    report = drift.DriftReport(generated_at=NOW)
    drift.check_performance(
        report, build_view(JsonlEventJournal(tmp_path / "d.jsonl").replay()), CALM
    )

    assert report.performance is not None
    assert report.performance.alert
    (alert,) = report.alerts("paper")
    assert alert.title == "drift de desempeño"
    assert alert.details["días de paper"] == "3"


def test_performance_needs_the_h2_evaluation_and_a_day_of_paper(tmp_path: Path) -> None:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_performance(report, build_view([]), None)
    assert "H2" in report.skipped["desempeño"]

    report = drift.DriftReport(generated_at=NOW)
    drift.check_performance(report, build_view([]), CALM)
    assert "menos de un día" in report.skipped["desempeño"]


# --- tickets ----------------------------------------------------------------------------------


class FakeGh:
    def __init__(self, existing: str = "", fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.existing, self.fail = existing, fail

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        if self.fail:
            return subprocess.CompletedProcess(cmd, 1, "", "no autenticado")
        out = {"list": self.existing, "create": "https://github.com/x/y/issues/7\n"}.get(cmd[2], "")
        return subprocess.CompletedProcess(cmd, 0, out, "")


def drift_alert() -> Alert:
    report = drift.DriftReport(generated_at=NOW)
    drift.check_data(report, {"SOLUSDT": symbol_panel(shift=0.5)})
    (alert,) = report.alerts("paper")
    return alert


def test_a_ticket_is_opened_once_per_detector() -> None:
    gh = FakeGh()
    assert drift.open_ticket(drift_alert(), gh) == "https://github.com/x/y/issues/7"
    assert [c[1:3] for c in gh.calls] == [
        ["issue", "list"],
        ["label", "create"],
        ["issue", "create"],
    ]
    body = gh.calls[-1][gh.calls[-1].index("--body") + 1]
    assert "prohibido retocar sin un nuevo ciclo PDCA" in body

    already = FakeGh(existing="https://github.com/x/y/issues/3\n")
    assert drift.open_ticket(drift_alert(), already) == "https://github.com/x/y/issues/3"
    assert len(already.calls) == 1  # no crea un duplicado


def test_a_gh_failure_is_reported() -> None:
    with pytest.raises(RuntimeError, match="gh issue list"):
        drift.open_ticket(drift_alert(), FakeGh(fail=True))


# --- CLI --------------------------------------------------------------------------------------


@pytest.fixture
def lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PQ_ENVIRONMENT", "paper")
    panels = {"BTCUSDT": symbol_panel(), "SOLUSDT": symbol_panel(shift=0.5)}
    monkeypatch.setattr(drift, "load_panels", lambda data_dir: panels)
    monkeypatch.setattr(
        "prometheus_platform.research.nowcast.tuned_params", lambda data_dir: {"max_depth": 4}
    )
    days = [str(DEV_START.date() + timedelta(days=i)) for i in range(300)]
    art = Artifacts(
        carry={"H2": {"selected": "k3"}},
        carry_returns={"H2": pl.DataFrame({"date": days, "k3": CALM})},
    )
    monkeypatch.setattr(
        "prometheus_platform.api.dashboard.artifacts.load_artifacts", lambda data_dir: art
    )
    valuations(tmp_path / "paper" / "diario.jsonl", [1000, 1000.1, 1000.2])
    return tmp_path


def test_cli_writes_the_report_and_exits_1_on_an_alert(
    lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tickets: list[str] = []

    def fake_ticket(alert: Alert) -> str:
        tickets.append(alert.title)
        return "url-1"

    monkeypatch.setattr(drift, "open_ticket", fake_ticket)

    assert main(["monitor", "drift", "--ticket"]) == 1

    out = capsys.readouterr().out
    assert "ALERTA drift de datos: url-1" in out
    assert tickets == ["drift de datos"]
    saved = json.loads((lake / "monitoring" / "drift" / "drift-2026-11-23.json").read_text())
    assert saved["thresholds"]["psi"] == 0.25
    assert {d["symbol"]: d["alert"] for d in saved["data"]} == {"BTCUSDT": False, "SOLUSDT": True}
    assert saved["model"]["alert"] is False
    assert saved["performance"]["days"] == 2


def test_cli_without_silver_still_checks_the_performance(
    lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(data_dir: Path) -> dict[str, pl.DataFrame]:
        raise FileNotFoundError(data_dir)

    monkeypatch.setattr(drift, "load_panels", missing)

    assert main(["monitor", "drift"]) == 0

    out = capsys.readouterr().out
    assert "sin evaluar (datos y modelo)" in out
    assert "sin drift" in out


def test_a_ticket_failure_does_not_hide_the_alert(
    lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(alert: object) -> str:
        raise RuntimeError("gh issue list falló (1)")

    monkeypatch.setattr(drift, "open_ticket", broken)

    assert main(["monitor", "drift", "--ticket"]) == 1
    captured = capsys.readouterr()
    assert "no se pudo abrir el issue" in captured.err
    assert "ALERTA drift de datos: sin ticket" in captured.out
