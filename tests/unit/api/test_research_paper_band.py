"""``pq research paper-banda`` (PQ-120): el paper frente a la banda de 30 días, sin extrapolar."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli


def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    lake = tmp_path / "lake"
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    return lake


def test_without_the_band_it_says_which_command_computes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env(monkeypatch, tmp_path)
    assert cli.main(["research", "paper-banda"]) == 2
    structlog.reset_defaults()
    assert "pq research simulate" in capsys.readouterr().out


def test_with_the_band_but_no_paper_the_verdict_is_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lake = env(monkeypatch, tmp_path)
    summary = lake / "research" / "simulation" / "summary.json"
    summary.parent.mkdir(parents=True)
    band = {"days": 30, "p5": -0.004, "p50": 0.002, "p95": 0.009, "paths": 1000}
    summary.write_text(json.dumps({"banda_30_dias": band}))

    assert cli.main(["research", "paper-banda"]) == 0
    structlog.reset_defaults()

    out = capsys.readouterr().out
    assert "banda de 30 días" in out
    assert "INSUFICIENTE" in out  # sin valoraciones del paper no se extrapola
    (row,) = list(read_rows(tmp_path / "docs/estrategias/ensayos"))
    assert (row.familia, row.cuenta_en_n, row.nombre) == ("descriptivo", False, "paper-banda")
