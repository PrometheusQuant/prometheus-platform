"""Holdout de tendencia (PQ-68, pre-registro §7 y §8): un solo uso, sin re-ajustes."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import timedelta
from functools import partial
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import TrialLedger, read_rows
from prometheus_platform.api import cli
from prometheus_platform.data_platform.silver import silver_path
from prometheus_platform.domain.datasets import DatasetKind, Market
from prometheus_platform.domain.protocol import HOLDOUT_END, HOLDOUT_START
from prometheus_platform.research import trend_evaluation as te
from prometheus_platform.research.trend import SymbolMarket

from .test_trend import build

WARMUP_DAYS = 130  # ≥ 121 cierres para L = 120
HOLDOUT_DAYS = (te.HOLDOUT_STOP - HOLDOUT_START).days  # 822
ORIGIN = HOLDOUT_START - timedelta(days=WARMUP_DAYS)
TOTAL_DAYS = WARMUP_DAYS + HOLDOUT_DAYS


def walk(seed: int) -> partial[float]:
    rng = np.random.default_rng(seed)
    path = 100 * np.exp(np.cumsum(rng.normal(0.00005, 0.006, TOTAL_DAYS * 24 + 2)))
    return partial(lambda p, i: float(p[i]), path)


@pytest.fixture(scope="module")
def mercados() -> list[SymbolMarket]:
    out = []
    for seed, symbol in enumerate(te.SYMBOLS):
        hourly, settlements = build(TOTAL_DAYS, walk(70 + seed), start=ORIGIN)
        out.append(SymbolMarket(symbol, hourly, settlements))
    return out


@pytest.fixture(scope="module")
def evaluacion(mercados: list[SymbolMarket]) -> te.HoldoutEvaluation:
    return te.evaluate_holdout(mercados, te.selected_config("T1-L120-vol20"))


def test_holdout_cubre_exactamente_el_periodo_pre_registrado(
    evaluacion: te.HoldoutEvaluation,
) -> None:
    assert HOLDOUT_END + timedelta(seconds=1) == te.HOLDOUT_STOP
    assert evaluacion.period == (HOLDOUT_START, te.HOLDOUT_STOP)
    assert evaluacion.dates[0].startswith("2024-07-0")
    assert evaluacion.dates[-1].startswith("2026-10-01")  # valoración con la vela de las 23:00
    assert len(evaluacion.returns) == len(evaluacion.benchmark_returns) == HOLDOUT_DAYS
    assert evaluacion.selected == "T1-L120-vol20"


def test_criterios_de_exito_del_pre_registro(evaluacion: te.HoldoutEvaluation) -> None:
    perf = evaluacion.performance
    assert [(c.name, c.value) for c in evaluacion.criteria] == [
        ("H1", perf.sharpe),
        ("H2", perf.cagr),
        ("H3", perf.max_drawdown),
    ]
    assert [c.passed for c in evaluacion.criteria] == [
        perf.sharpe > 0.5,
        perf.cagr > 0.04,
        perf.max_drawdown > -0.30,
    ]
    assert evaluacion.passed is all(c.passed for c in evaluacion.criteria)


def test_solo_se_evalua_una_configuracion_pre_registrada() -> None:
    assert te.selected_config("T2-L60-vol40").lookback == 60
    with pytest.raises(ValueError, match="pre-registradas"):
        te.selected_config("T1-L90-vol20")


def test_load_market_holdout_corta_al_fin_del_holdout(tmp_path: Path) -> None:
    hours = pl.datetime_range(
        HOLDOUT_END - timedelta(days=2),
        HOLDOUT_END + timedelta(days=2),
        interval="1h",
        eager=True,
        time_zone="UTC",
    )
    bars = pl.DataFrame({"open_time": hours, "open": 100.0, "close": 101.0})
    for market in (Market.SPOT, Market.USDM):
        path = silver_path(tmp_path, DatasetKind.KLINES, "BTCUSDT", market, "1h")
        path.parent.mkdir(parents=True, exist_ok=True)
        bars.write_parquet(path)
    funding = pl.DataFrame({"funding_time": hours.gather_every(8), "funding_rate": 0.0001})
    path = silver_path(tmp_path, DatasetKind.FUNDING_RATE, "BTCUSDT")
    path.parent.mkdir(parents=True, exist_ok=True)
    funding.write_parquet(path)

    cargado = te.load_market_holdout(tmp_path, "BTCUSDT")
    assert cargado.hourly.filter(pl.col("open_time") >= te.HOLDOUT_STOP).is_empty()
    assert not cargado.hourly.is_empty()
    assert cargado.settlements is not None
    assert cargado.settlements.filter(pl.col("funding_time") >= te.HOLDOUT_STOP).is_empty()


# --- CLI: protecciones de un solo uso ----------------------------------------------------------


@pytest.fixture
def entorno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mercados: list[SymbolMarket]
) -> Iterator[Path]:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "boris")
    data = {m.symbol: m for m in mercados}
    monkeypatch.setattr(te, "load_market_holdout", lambda _root, symbol: data[symbol])
    yield tmp_path
    structlog.reset_defaults()


def _desarrollo(root: Path, *, passed: bool = True) -> None:
    path = root / "lake/research/trend/T1/summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"selected": "T1-L120-vol20", "passed": passed}))


def _filas(root: Path) -> list[str]:
    return [r.nombre for r in read_rows(root / "docs/estrategias/ensayos")]


def test_sin_confirmacion_no_abre_nada(entorno: Path) -> None:
    _desarrollo(entorno)
    assert cli.main(["research", "trend-holdout"]) == 2
    assert _filas(entorno) == []
    assert not (entorno / "lake/research/trend/holdout").exists()


@pytest.mark.parametrize("passed", [None, False])
def test_sin_desarrollo_aprobado_no_abre_nada(entorno: Path, passed: bool | None) -> None:
    if passed is not None:
        _desarrollo(entorno, passed=passed)
    assert cli.main(["research", "trend-holdout", "--confirmo-un-solo-uso"]) == 2
    assert _filas(entorno) == []


def test_abre_una_vez_registra_sin_sumar_a_n_y_no_se_repite(
    entorno: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _desarrollo(entorno)
    args = ["research", "trend-holdout", "--confirmo-un-solo-uso", "--figures", str(entorno)]
    assert cli.main(args) == 0
    assert "Holdout T1-L120-vol20:" in capsys.readouterr().out
    summary = json.loads((entorno / "lake/research/trend/holdout/summary.json").read_text())
    assert summary["seleccionada"] == "T1-L120-vol20"
    assert summary["dias"] == HOLDOUT_DAYS
    assert [c["name"] for c in summary["criterios"]] == ["H1", "H2", "H3"]
    assert (entorno / "holdout-curva.png").stat().st_size > 10_000

    [fila] = list(read_rows(entorno / "docs/estrategias/ensayos"))
    assert (fila.nombre, fila.familia, fila.carril) == ("holdout", "tendencia", "boris")
    assert fila.cuenta_en_n is False
    assert fila.params == {"configuracion": "T1-L120-vol20"}
    ledger = TrialLedger(
        entorno / "docs/estrategias/ensayos",
        familia="tendencia",
        carril="boris",
        autor="x",
        comando="x",
        commit="x",
    )
    assert ledger.trials() == []  # evaluar la configuración elegida no es un ensayo nuevo

    assert cli.main(args) == 2  # segunda vez: se niega
    assert "ya se abrió" in capsys.readouterr().err
    assert _filas(entorno) == ["holdout"]
