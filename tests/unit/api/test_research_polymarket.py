"""``pq research polymarket`` (PQ-93): registra los 6 ensayos una vez y escribe los resultados."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest
import structlog
from tests.unit.research.polymarket_data import (
    D0,
    raw_market,
    silver_markets,
    silver_prices,
)

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.polymarket_evaluation import load_other_strategies


def lake(tmp_path: Path) -> Path:
    root = tmp_path / "lake"
    markets = silver_markets(
        *(raw_market(str(i), closed=D0 + timedelta(days=5 + i), event=f"e{i}") for i in range(8))
    )
    prices = silver_prices(markets, {str(i): [0.7, 0.85, 0.9] for i in range(8)})
    base = root / "silver" / "polymarket"
    base.mkdir(parents=True)
    markets.write_parquet(base / "markets.parquet")
    prices.write_parquet(base / "prices_1440.parquet")
    return root


def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "boris")


def test_cli_registers_six_trials_in_the_ticket_lane_and_writes_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env(monkeypatch, tmp_path)
    root = lake(tmp_path)

    assert cli.main(["research", "polymarket"]) == 0
    structlog.reset_defaults()

    out = capsys.readouterr().out
    assert "P1 (fuera-de-deportes): P1-B80, 8 apuestas" in out
    assert "G5" in out
    rows = list(read_rows(tmp_path / "docs/estrategias/ensayos"))
    assert [r.nombre for r in rows] == ["P1-B70", "P1-B80", "P1-B90", "P2-B70", "P2-B80", "P2-B90"]
    assert {(r.familia, r.carril, r.cuenta_en_n) for r in rows} == {("polymarket", "boris", True)}
    summary = json.loads((root / "research/polymarket/P1/summary.json").read_text())
    assert summary["principal"] == "P1-B80"
    assert len(summary["gates"]) == 5
    bets = pl.read_parquet(root / "research/polymarket/P1/bets.parquet")
    assert bets.height == 8
    daily = pl.read_parquet(root / "research/polymarket/P1/daily_pnl.parquet")
    assert daily.columns == ["date", "P1-B70", "P1-B80", "P1-B90"]


def test_cli_refuses_a_second_run_unless_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env(monkeypatch, tmp_path)
    lake(tmp_path)
    assert cli.main(["research", "polymarket"]) == 0
    structlog.reset_defaults()

    assert cli.main(["research", "polymarket"]) == 2
    structlog.reset_defaults()
    assert "suma a N" in capsys.readouterr().err
    assert len(list(read_rows(tmp_path / "docs/estrategias/ensayos"))) == 6

    assert cli.main(["research", "polymarket", "--repetir"]) == 0
    structlog.reset_defaults()
    assert len(list(read_rows(tmp_path / "docs/estrategias/ensayos"))) == 12


def test_cli_explains_missing_silver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError, match="pq polymarket"):
        cli.main(["research", "polymarket"])
    structlog.reset_defaults()


def test_other_strategies_exclude_their_holdout_and_accept_text_dates(tmp_path: Path) -> None:
    for sub, as_text in (("carry/H2", True), ("trend/T1", False)):
        folder = tmp_path / sub
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps({"selected": "cfg"}))
        dates = [HOLDOUT_START - timedelta(days=2 - i) for i in range(3)]  # el último: holdout
        pl.DataFrame(
            {"date": [str(d) for d in dates] if as_text else dates, "cfg": [0.1, 0.2, 9.0]}
        ).write_parquet(folder / "daily_returns.parquet")
    (tmp_path / "otra").mkdir()

    loaded = load_other_strategies(tmp_path)

    assert set(loaded) == {"carry_H2", "tendencia_T1"}
    for frame in loaded.values():
        assert frame["ret"].to_list() == [0.1, 0.2]  # el 9,0 del holdout no entra
        assert frame["date"].dtype == pl.Date
