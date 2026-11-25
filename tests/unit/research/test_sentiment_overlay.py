"""Overlay de sentimiento sobre el momentum (PQ-128), con datos sintéticos.

Ningún test usa datos reales: no son ensayos y no suman a N.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli
from prometheus_platform.data_platform import sentiment as se
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research import momentum as mo
from prometheus_platform.research import momentum_evaluation as me
from prometheus_platform.research import sentiment_overlay as so
from prometheus_platform.research.carry_evaluation import TrialRecord

from .test_momentum import COSTS, EVAL_START, MONDAY, noisy_universe, run, universe
from .test_trend import Registry

UTC = HOLDOUT_START.tzinfo


def fng(values: dict[date, int]) -> pl.DataFrame:
    days = sorted(values)
    return pl.DataFrame(
        {
            "date": days,
            "value": [values[d] for d in days],
            "knowledge_time": [datetime(d.year, d.month, d.day, 1, tzinfo=UTC) for d in days],
        },
        schema={"date": pl.Date, "value": pl.Int64, "knowledge_time": pl.Datetime("ms", "UTC")},
    )


def test_the_monday_decision_uses_sundays_value_not_mondays() -> None:
    monday = MONDAY.date()
    sunday = monday - timedelta(days=1)
    # El valor del lunes (5) todavía no se conoce a las 00:00: manda el del domingo.
    assert so.out_mondays(fng({sunday: 60, monday: 5}), [MONDAY]) == frozenset()
    assert so.out_mondays(fng({sunday: 25, monday: 90}), [MONDAY]) == {MONDAY}
    assert so.out_mondays(fng({sunday: 26}), [MONDAY]) == frozenset()  # 26 ya es «miedo»


def test_an_old_value_means_no_filter() -> None:
    eight_days = MONDAY.date() - timedelta(days=8)
    six_days = MONDAY.date() - timedelta(days=6)
    assert so.out_mondays(fng({eight_days: 10}), [MONDAY]) == frozenset()
    assert so.out_mondays(fng({six_days: 10}), [MONDAY]) == {MONDAY}
    assert so.out_mondays(fng({}), [MONDAY]) == frozenset()


def test_mondays_lists_every_monday_at_midnight() -> None:
    days = so.mondays(MONDAY - timedelta(days=3), MONDAY + timedelta(days=15))
    assert days == [MONDAY, MONDAY + timedelta(days=7), MONDAY + timedelta(days=14)]


def test_without_weeks_out_the_base_is_untouched() -> None:
    base = run(universe(), mo.MomentumConfig(7))
    same = run(universe(), mo.MomentumConfig(7, out=frozenset(), overlay="S1"))
    assert same.daily_equity.equals(base.daily_equity)
    assert same.weeks_out == []


def test_a_week_out_goes_to_cash_and_stays_flat() -> None:
    second = MONDAY + timedelta(days=7)
    result = run(universe(), mo.MomentumConfig(7, out=frozenset({second}), overlay="S1"))
    assert result.weeks_out == [second]
    equity = result.daily_equity.filter(
        (pl.col("date") > second + timedelta(days=1))
        & (pl.col("date") <= second + timedelta(days=7))
    )["equity"]
    assert equity.n_unique() == 1  # sin posiciones ni funding, el capital no se mueve


def test_the_overlay_name_and_trial_carry_the_filter() -> None:
    config = mo.MomentumConfig(28, mo.Hypothesis.X2, out=frozenset({MONDAY}), overlay="S2")
    assert config.name == "S2-X2-L28"
    registry = Registry()
    mo.run_and_register(universe(), config, COSTS, registry, costs_label="principal")
    trial = registry.items[0]
    assert trial.hypothesis == "S2"
    assert trial.params["base"] == "X2"
    assert "semanas_fuera" in trial.metrics


def extreme_fear_every_other_week() -> pl.DataFrame:
    start = EVAL_START.date() - timedelta(days=30)
    days = [start + timedelta(days=i) for i in range((HOLDOUT_START.date() - start).days)]
    return fng({d: (10 if (d.toordinal() // 7) % 2 else 60) for d in days})


@pytest.fixture(scope="module")
def evaluated() -> tuple[Registry, dict[str, so.OverlayEvaluation]]:
    registry = Registry()
    for i in range(6):
        registry.log_trial(TrialRecord("X1", f"momentum-{i}", metrics={"sharpe_daily": 0.01 * i}))
    evaluations = so.evaluate(
        noisy_universe(),
        registry,
        extreme_fear_every_other_week(),
        lookbacks={mo.Hypothesis.X1: 7, mo.Hypothesis.X2: 14},
        costs=COSTS,
        start=EVAL_START,
    )
    return registry, evaluations


def test_registers_the_two_overlays_and_counts_the_family(
    evaluated: tuple[Registry, dict[str, so.OverlayEvaluation]],
) -> None:
    registry, evaluations = evaluated
    assert [t.name for t in registry.items[6:]] == ["S1-X1-L7", "S2-X2-L14"]
    assert set(evaluations) == {"S1", "S2"}
    for evaluation in evaluations.values():
        assert evaluation.n_trials == 8
        assert [g.name for g in evaluation.gates] == ["G1", "G2", "G3", "G4", "G5"]
        assert evaluation.secondary["semanas_fuera"] > 0
        assert evaluation.secondary["semanas_fuera"] < evaluation.secondary["lunes_evaluados"]
        assert set(evaluation.returns) == {evaluation.selected, evaluation.base_name}


def test_g5_compares_with_the_base_without_filter(
    evaluated: tuple[Registry, dict[str, so.OverlayEvaluation]],
) -> None:
    _, evaluations = evaluated
    s1 = evaluations["S1"]
    g5 = s1.gates[4]
    assert s1.base_name == "X1-L7"
    assert g5.value == pytest.approx(s1.selected_performance.sharpe - s1.secondary["sharpe_base"])
    assert g5.passed == (
        g5.value > 0 and s1.secondary["mediana_cpcv"] > s1.secondary["mediana_cpcv_base"]
    )


def test_selected_lookback_reads_the_momentum_choice(tmp_path: Path) -> None:
    path = tmp_path / "momentum" / "X1" / "summary.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"selected": "X1-L28"}), encoding="utf-8")
    assert so.selected_lookback(tmp_path, mo.Hypothesis.X1) == 28
    path.write_text(json.dumps({"selected": "X2-L7"}), encoding="utf-8")
    with pytest.raises(ValueError, match="inesperada"):
        so.selected_lookback(tmp_path, mo.Hypothesis.X1)


def test_cli_registers_both_overlays_in_the_ticket_lane(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    lake = tmp_path / "lake"
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "boris")
    data = {m.symbol: m for m in noisy_universe()}
    universe_file = tmp_path / cli.MOMENTUM_UNIVERSE_FILE
    universe_file.parent.mkdir(parents=True)
    universe_file.write_text(
        json.dumps({"universo": sorted(data), "menor_volumen_10pb": ["FFF"]}), encoding="utf-8"
    )
    for hyp in ("X1", "X2"):
        summary = lake / "research" / "momentum" / hyp / "summary.json"
        summary.parent.mkdir(parents=True)
        summary.write_text(json.dumps({"selected": f"{hyp}-L14"}), encoding="utf-8")
    silver = lake / "silver" / se.SILVER_FILE
    silver.parent.mkdir(parents=True)
    extreme_fear_every_other_week().write_parquet(silver)
    monkeypatch.setattr(me, "load_market", lambda _root, symbol: data[symbol])
    monkeypatch.setattr(so, "evaluate", partial(so.evaluate, start=EVAL_START))

    assert cli.main(["research", "sentimiento"]) == 0
    out = capsys.readouterr().out
    assert "S1: semanas fuera=" in out
    assert "G5" in out
    structlog.reset_defaults()

    for name in ("S1", "S2"):
        summary = json.loads((lake / f"research/sentimiento/{name}/summary.json").read_text())
        assert summary["base"] in {"X1-L14", "X2-L14"}
        assert "retorno_base_en_semanas_fuera" in summary["secondary"]
    rows = list(read_rows(tmp_path / "docs/estrategias/ensayos"))
    assert [r.nombre for r in rows] == ["S1-X1-L14", "S2-X2-L14"]
    assert {r.carril for r in rows} == {"boris"}
    assert {r.familia for r in rows} == {"tendencia"}
