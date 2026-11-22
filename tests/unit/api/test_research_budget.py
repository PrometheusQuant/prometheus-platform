"""``pq research budget`` (PQ-83): lee solo estrategias aprobadas y solo el desarrollo."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli
from prometheus_platform.api import research_budget as rb
from prometheus_platform.domain.protocol import HOLDOUT_START


def evaluation(root: Path, family: str, name: str, *, passed: bool, returns: list[float]) -> None:
    folder = root / family / name
    folder.mkdir(parents=True)
    selected = "cfg-elegida"
    (folder / "summary.json").write_text(json.dumps({"selected": selected, "passed": passed}))
    dates = [HOLDOUT_START - timedelta(days=len(returns) - 1 - i) for i in range(len(returns))]
    pl.DataFrame(
        {"date": [str(d) for d in dates], selected: returns, "otra": [0.0] * len(returns)}
    ).write_parquet(folder / "daily_returns.parquet")


def research(tmp_path: Path, *, h2_daily: float = 0.0004) -> Path:
    root = tmp_path / "lake" / "research"
    rng = np.random.default_rng(3)
    n = 400
    h2 = list(rng.normal(h2_daily, 0.001, n))
    h2[-1] = 9.0  # la valoración del 2024-07-01 (holdout): si se colara, se vería
    evaluation(root, "carry", "H2", passed=True, returns=h2)
    evaluation(root, "carry", "H1", passed=False, returns=[0.01] * n)  # descartada
    (root / "simulation").mkdir(parents=True)
    (root / "simulation" / "summary.json").write_text(
        json.dumps({"probabilidad_quiebra_equilibrio": 0.004})
    )
    return root


def test_only_approved_strategies_and_only_development_days(tmp_path: Path) -> None:
    root = research(tmp_path)
    (approved,) = rb.approved_strategies(root)
    assert approved.name == "carry-H2"
    assert approved.config == "cfg-elegida"
    assert approved.returns.filter(pl.col("date") >= HOLDOUT_START).is_empty()  # KE-014
    assert float(approved.returns["ret"].max()) < 1  # type: ignore[arg-type]  # el 9,0 del holdout no entró


def test_run_writes_the_budget_with_the_exchange_cap(tmp_path: Path) -> None:
    root = research(tmp_path)
    budget = rb.run(root, n_paths=2000)
    result = budget.summary
    assert result["estrategias_aprobadas"] == ["carry-H2"]
    assert result["tope_por_exchange"] == {"binance": pytest.approx(0.125)}
    weight = result["presupuesto"]["carry-H2"]
    assert weight <= 0.125
    assert result["efectivo"] == pytest.approx(1 - weight)
    assert result["cvar95"] <= rb.CVAR_LIMIT
    assert result["dias_desarrollo"] == 399
    contributions = result["contribucion_cvar"]
    assert sum(contributions.values()) == pytest.approx(result["cvar95"])
    path = rb.write(budget, root / "budget")
    assert json.loads(path.read_text())["presupuesto"] == result["presupuesto"]
    scenarios = pl.read_parquet(root / "budget" / "scenarios.parquet")
    assert scenarios.columns == ["carry-H2"]
    assert scenarios.height == 2000


def test_without_approved_strategies_everything_stays_in_cash(tmp_path: Path) -> None:
    root = tmp_path / "research"
    (root / "simulation").mkdir(parents=True)
    (root / "simulation" / "summary.json").write_text(
        json.dumps({"probabilidad_quiebra_equilibrio": 0.004})
    )
    result = rb.run(root).summary
    assert result["estrategias_aprobadas"] == []
    assert result["efectivo"] == 1.0


def test_cli_writes_the_budget_and_registers_a_descriptive_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    research(tmp_path)
    assert cli.main(["research", "budget"]) == 0
    out = capsys.readouterr().out
    assert "estrategias aprobadas: carry-H2" in out
    assert "efectivo al 4 %" in out
    structlog.reset_defaults()
    assert (tmp_path / "lake/research/budget/summary.json").exists()
    (row,) = read_rows(tmp_path / "docs/estrategias/ensayos")
    assert (row.familia, row.cuenta_en_n, row.nombre) == ("descriptivo", False, "budget")


def test_cli_explains_a_missing_chapter_6_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "vacio"))
    assert cli.main(["research", "budget"]) == 2
    assert "pq research simulate" in capsys.readouterr().out
    structlog.reset_defaults()


def test_generated_timestamp_is_utc(tmp_path: Path) -> None:
    result = rb.run(research(tmp_path), n_paths=200).summary
    assert datetime.fromisoformat(result["generado"]).utcoffset() == UTC.utcoffset(None)
