import json
import os
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.api import cli
from prometheus_platform.research import carry_evaluation as ce
from prometheus_platform.research.reporting import plot_equity, write_outputs

from .conftest import HourlyFactory


def synthetic(market: HourlyFactory) -> ce.SymbolData:
    hourly, settlements = market(
        hours=24 * 220, rate=lambda h: 0.0004 if (h // 240) % 2 == 0 else 0.00002
    )
    return ce.SymbolData("BTCUSDT", hourly, settlements)


def test_cli_runs_the_evaluation_and_writes_the_report(
    market: HourlyFactory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setitem(ce.HYPOTHESES, "H1", ("BTCUSDT",))
    monkeypatch.setattr(ce, "load_symbol", lambda _root, _symbol: synthetic(market))

    assert (
        cli.main(["research", "carry", "--hypothesis", "H1", "--figures", str(tmp_path / "img")])
        == 0
    )
    out = capsys.readouterr().out
    assert "H1: elegida=" in out
    assert "G1" in out
    structlog.reset_defaults()

    summary = json.loads((tmp_path / "lake/research/carry/H1/summary.json").read_text())
    assert summary["n_trials"] == 20
    assert len(summary["gates"]) == 4
    returns = pl.read_parquet(tmp_path / "lake/research/carry/H1/daily_returns.parquet")
    assert returns.width == 10  # fecha + 9 configuraciones
    assert (tmp_path / "img/h1-curvas.png").stat().st_size > 10_000
    assert (tmp_path / "lake/mlflow/mlflow.db").exists()


def test_reporting_helpers(market: HourlyFactory, tmp_path: Path) -> None:
    class Registry:
        def __init__(self) -> None:
            self.items: list[ce.TrialRecord] = []

        def log_trial(self, trial: ce.TrialRecord) -> None:
            self.items.append(trial)

        def trials(self) -> list[ce.TrialRecord]:
            return self.items

    evaluation = ce.evaluate_hypothesis("H1", [synthetic(market)], Registry())
    assert write_outputs(evaluation, tmp_path / "out").name == "summary.json"
    assert plot_equity(evaluation, tmp_path / "f.png", evaluation.benchmark_returns).exists()
