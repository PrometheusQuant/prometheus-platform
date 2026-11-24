"""Evaluación de la tendencia en el desarrollo (PQ-68), con datos sintéticos.

Ningún test usa datos reales: no son ensayos y no suman a N.
"""

from __future__ import annotations

import json
import os
from datetime import timedelta
from functools import partial
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import read_rows
from prometheus_platform.api import cli
from prometheus_platform.data_platform.silver import silver_path
from prometheus_platform.domain.datasets import DatasetKind, Market
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research import trend_evaluation as te
from prometheus_platform.research.backtest import MAIN_COSTS
from prometheus_platform.research.carry_evaluation import TrialRecord
from prometheus_platform.research.trend import Hypothesis, SymbolMarket, TrendConfig, run_config
from prometheus_platform.research.validation import performance

from .test_trend import Registry, build

DAYS = 200
ORIGIN = HOLDOUT_START - timedelta(days=DAYS)
START = HOLDOUT_START - timedelta(days=70)  # 130 días de calentamiento ≥ 121


def walk(seed: int) -> partial[float]:
    rng = np.random.default_rng(seed)
    path = 100 * np.exp(np.cumsum(rng.normal(0.00005, 0.006, DAYS * 24 + 2)))
    return partial(lambda p, i: float(p[i]), path)


def markets() -> list[SymbolMarket]:
    out = []
    for seed, symbol in enumerate(te.SYMBOLS):
        hourly, settlements = build(DAYS, walk(30 + seed), start=ORIGIN)  # eligen L = 60
        out.append(SymbolMarket(symbol, hourly, settlements))
    return out


SMOKE = 3  # ensayos de tendencia ya registrados (p. ej. una prueba de humo): también suman a N


@pytest.fixture(scope="module")
def evaluated() -> tuple[Registry, dict[Hypothesis, te.TrendEvaluation]]:
    registry = Registry()
    for i in range(SMOKE):
        registry.log_trial(TrialRecord("T1", f"humo-{i}", metrics={"sharpe_daily": 0.01 * i}))
    return registry, te.evaluate_family(markets(), registry, start=START)


def test_registers_the_twelve_pre_registered_configurations_once(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    registry, _ = evaluated
    new = registry.items[SMOKE:]
    names = [t.name for t in new]
    assert len(names) == te.PRE_REGISTERED_TRIALS == 12
    assert len(set(names)) == 12
    assert {t.hypothesis for t in new} == {"T1", "T2"}
    assert not any("sin-vol" in n or n.startswith("B1") for n in names)  # benchmarks fuera de N
    assert {t.tags["costs"] for t in new} == {"principal"}
    assert {t.tags["period"] for t in new} == {"desarrollo"}


def test_each_hypothesis_selects_by_mean_cpcv_sharpe_with_the_same_n(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    _, evaluations = evaluated
    assert set(evaluations) == {Hypothesis.T1, Hypothesis.T2}
    for hypothesis, evaluation in evaluations.items():
        assert len(evaluation.returns) == 6
        assert all(n.startswith(str(hypothesis)) for n in evaluation.returns)
        best = max(evaluation.cpcv_mean_sharpe.values())
        assert evaluation.cpcv_mean_sharpe[evaluation.selected] == best
        assert evaluation.n_trials == 12 + SMOKE  # N = todos los ensayos de tendencia
        assert [g.name for g in evaluation.gates] == ["G1", "G2", "G3", "G4"]
        assert 0 <= evaluation.pbo <= 1
        assert 0 <= evaluation.dsr <= 1
        assert evaluation.b3_name == evaluation.selected.rsplit("-vol", 1)[0] + "-sin-vol"
        assert set(evaluation.secondary) >= {"vol_realizada", "rotacion_anual", "peor_dia"}
    # N y V[SR] no dependen del orden: las dos hipótesis los comparten.
    t1, t2 = evaluations[Hypothesis.T1], evaluations[Hypothesis.T2]
    assert (t1.n_trials, t1.var_sharpe) == (t2.n_trials, t2.var_sharpe)


def test_evaluation_never_reaches_the_holdout(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    _, evaluations = evaluated
    for evaluation in evaluations.values():
        last = pl.Series([evaluation.dates[-1]]).str.to_datetime(time_zone="UTC")[0]
        assert last <= HOLDOUT_START


def test_t1_never_has_funding_and_b1_is_buy_and_hold(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    _, evaluations = evaluated
    t1 = evaluations[Hypothesis.T1]
    assert t1.decomposition["funding"] == 0
    assert t1.benchmark.days == t1.selected_performance.days
    assert evaluations[Hypothesis.T2].benchmark == t1.benchmark  # el mismo B1 para las dos


def write_silver(root: Path, symbol: str) -> None:
    hours = pl.datetime_range(
        HOLDOUT_START - timedelta(days=2),
        HOLDOUT_START + timedelta(days=2),
        interval="1h",
        eager=True,
        time_zone="UTC",
    )
    bars = pl.DataFrame({"open_time": hours, "open": 100.0, "close": 101.0})
    for market in (Market.SPOT, Market.USDM):
        path = silver_path(root, DatasetKind.KLINES, symbol, market, "1h")
        path.parent.mkdir(parents=True, exist_ok=True)
        bars.write_parquet(path)
    funding = pl.DataFrame(
        {"funding_time": hours.gather_every(8), "funding_rate": 0.0001, "extra": 1}
    )
    path = silver_path(root, DatasetKind.FUNDING_RATE, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    funding.write_parquet(path)


def test_load_market_cuts_the_holdout_before_anything_else(tmp_path: Path) -> None:
    write_silver(tmp_path, "BTCUSDT")
    market = te.load_market(tmp_path, "BTCUSDT")
    assert market.hourly["open_time"].max() == HOLDOUT_START - timedelta(hours=1)
    assert market.settlements is not None
    assert market.settlements.filter(pl.col("funding_time") >= HOLDOUT_START).is_empty()  # KE-014
    assert market.settlements.columns == ["funding_time", "funding_rate"]


def test_cli_registers_in_the_ticket_lane_and_writes_both_hypotheses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "boris")
    data = {m.symbol: m for m in markets()}
    monkeypatch.setattr(te, "load_market", lambda _root, symbol: data[symbol])
    monkeypatch.setattr(te, "evaluate_family", partial(te.evaluate_family, start=START))

    assert cli.main(["research", "trend", "--figures", str(tmp_path / "img")]) == 0
    out = capsys.readouterr().out
    assert "T1: elegida=T1-" in out
    assert "T2: elegida=T2-" in out
    structlog.reset_defaults()

    for hypothesis in ("T1", "T2"):
        summary = json.loads(
            (tmp_path / f"lake/research/trend/{hypothesis}/summary.json").read_text()
        )
        assert summary["n_trials"] == 12
        assert summary["benchmark_B3"]["name"].endswith("-sin-vol")
        assert "rotacion_anual" in summary["secondary"]
        assert (tmp_path / f"img/{hypothesis.lower()}-curvas.png").stat().st_size > 10_000

    rows = list(read_rows(tmp_path / "docs/estrategias/ensayos"))
    assert len(rows) == 12
    assert {r.carril for r in rows} == {"boris"}
    assert {r.familia for r in rows} == {"tendencia"}
    assert (tmp_path / "docs/estrategias/ensayos/boris.jsonl").exists()
    assert rows[0].comando == f"pq research trend --figures {tmp_path / 'img'}"


def test_gates_follow_the_pre_registered_thresholds(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    _, evaluations = evaluated
    for e in evaluations.values():
        g1, g2, g3, g4 = e.gates
        perf = e.selected_performance
        assert (g1.value, g1.passed) == (e.dsr, e.dsr > 0.95)
        assert (g2.value, g2.passed) == (e.pbo, e.pbo < 0.5)
        assert (g3.value, g3.passed) == (perf.t_stat, perf.t_stat > 3)
        assert g4.passed == (perf.sharpe > e.benchmark.sharpe and perf.cagr > 0.04)
        assert e.passed == all(g.passed for g in e.gates)


def test_b3_is_the_selected_signal_without_vol_targeting(
    evaluated: tuple[Registry, dict[Hypothesis, te.TrendEvaluation]],
) -> None:
    _, evaluations = evaluated
    lookbacks = set()
    for hypothesis, e in evaluations.items():
        lookback = int(e.selected.split("-L")[1].split("-")[0])
        lookbacks.add(lookback)
        b3 = TrendConfig(lookback, 0.2, hypothesis, vol_targeting=False)
        frame, _ = run_config(markets(), b3, MAIN_COSTS, start=START)
        assert e.b3 == performance(frame["ret"].to_numpy())
    assert lookbacks != {20}, "la historia sintética debe elegir alguna L distinta de 20"


def test_cpcv_purges_150_days_around_each_test_block() -> None:
    splits = te.splits(2000)
    assert len(splits) == 15  # C(6, 2)
    for split in splits:
        train, test = set(split.train.tolist()), split.test
        nearest = min(abs(i - j) for i in train for j in (test.min(), test.max()))
        assert nearest > 150  # §8: ventana máxima de 120 días más 30 de volatilidad
