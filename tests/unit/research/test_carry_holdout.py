"""Holdout del carry H2 (PQ-50, pre-registro §7 y §8): un solo uso, sin re-ajustes."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
import structlog

from prometheus_platform.adapters.trial_ledger import TrialLedger, read_rows
from prometheus_platform.api import cli
from prometheus_platform.domain.protocol import HOLDOUT_END, HOLDOUT_START
from prometheus_platform.research import carry_evaluation as ce

from .conftest import make_market

START = HOLDOUT_START - timedelta(days=30)  # historia previa para las medias S_k
HOLDOUT_DAYS = (ce.HOLDOUT_STOP - HOLDOUT_START).days  # 822
HOURS = (HOLDOUT_DAYS + 30 + 3) * 24  # termina 3 días después del holdout


def _rate(h: int) -> float:
    # Régimen alto y bajo alternos; tras el fin del holdout, un funding absurdo que no debe contar.
    if START + timedelta(hours=h) >= ce.HOLDOUT_STOP:
        return 0.05
    return 0.0004 if (h // 240) % 2 == 0 else 0.00002


@pytest.fixture(scope="module")
def datos() -> list[ce.SymbolData]:
    out = []
    for symbol in ce.HYPOTHESES["H2"]:
        hourly, settlements = make_market(HOURS, rate=_rate, start=START)
        out.append(ce.SymbolData(symbol, hourly, settlements))
    return out


@pytest.fixture(scope="module")
def evaluacion(datos: list[ce.SymbolData]) -> ce.CarryHoldout:
    return ce.evaluate_holdout("H2", datos, "k9-theta20")


def test_cubre_exactamente_el_holdout_y_no_cobra_despues(evaluacion: ce.CarryHoldout) -> None:
    assert HOLDOUT_END + timedelta(seconds=1) == ce.HOLDOUT_STOP
    assert evaluacion.period == (HOLDOUT_START, ce.HOLDOUT_STOP)
    assert evaluacion.dates[0].startswith("2024-07-02")  # el 07-01 cierra el desarrollo
    assert evaluacion.dates[-1].startswith("2026-10-01")
    assert len(evaluacion.returns) == len(evaluacion.benchmark_returns) == HOLDOUT_DAYS
    # El funding del 5 % posterior al holdout habría disparado el CAGR si se cobrara.
    assert evaluacion.performance.cagr < 1.0


def test_criterios_de_exito_del_pre_registro(evaluacion: ce.CarryHoldout) -> None:
    perf = evaluacion.performance
    assert [(c.name, c.value) for c in evaluacion.criteria] == [
        ("H1", perf.sharpe),
        ("H2", perf.cagr),
        ("H3", perf.max_drawdown),
    ]
    assert [c.passed for c in evaluacion.criteria] == [
        perf.sharpe > 0.5,
        perf.cagr > 0.04,
        perf.max_drawdown > -0.15,  # el carry exige menos del 15 % (la tendencia, 30 %)
    ]
    assert evaluacion.passed is all(c.passed for c in evaluacion.criteria)
    assert evaluacion.selected == "k9-theta20"


def test_solo_configuraciones_pre_registradas() -> None:
    assert ce.selected_config("k21-theta30").k == 21
    with pytest.raises(ValueError, match="pre-registradas"):
        ce.selected_config("k5-theta20")


# --- CLI: protecciones de un solo uso ----------------------------------------------------------


@pytest.fixture
def entorno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, datos: list[ce.SymbolData]
) -> Iterator[Path]:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PQ_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.setenv("PQ_RESEARCH_LANE", "david")
    by_symbol = {d.symbol: d for d in datos}
    monkeypatch.setattr(ce, "load_symbol", lambda _root, symbol: by_symbol[symbol])
    yield tmp_path
    structlog.reset_defaults()


def _desarrollo(root: Path, *, passed: bool = True) -> None:
    path = root / "lake/research/carry/H2/summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"selected": "k9-theta20", "passed": passed}))


def _filas(root: Path) -> list[str]:
    return [r.nombre for r in read_rows(root / "docs/estrategias/ensayos")]


def test_sin_confirmacion_no_abre_nada(entorno: Path) -> None:
    _desarrollo(entorno)
    assert cli.main(["research", "carry-holdout"]) == 2
    assert _filas(entorno) == []
    assert not (entorno / "lake/research/carry/holdout").exists()


@pytest.mark.parametrize("passed", [None, False])
def test_sin_desarrollo_aprobado_no_abre_nada(entorno: Path, passed: bool | None) -> None:
    if passed is not None:
        _desarrollo(entorno, passed=passed)
    assert cli.main(["research", "carry-holdout", "--confirmo-un-solo-uso"]) == 2
    assert _filas(entorno) == []


def test_abre_una_vez_registra_sin_sumar_a_n_y_no_se_repite(
    entorno: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _desarrollo(entorno)
    args = ["research", "carry-holdout", "--confirmo-un-solo-uso", "--figures", str(entorno)]
    assert cli.main(args) == 0
    assert "Holdout H2 k9-theta20:" in capsys.readouterr().out
    summary = json.loads((entorno / "lake/research/carry/holdout/summary.json").read_text())
    assert summary["seleccionada"] == "k9-theta20"
    assert summary["dias"] == HOLDOUT_DAYS
    assert [c["name"] for c in summary["criterios"]] == ["H1", "H2", "H3"]
    assert (entorno / "holdout-curva.png").stat().st_size > 10_000

    [fila] = list(read_rows(entorno / "docs/estrategias/ensayos"))
    assert (fila.nombre, fila.familia, fila.carril) == ("holdout", "carry", "david")
    assert fila.cuenta_en_n is False
    assert fila.params == {"hipotesis": "H2", "configuracion": "k9-theta20"}
    ledger = TrialLedger(
        entorno / "docs/estrategias/ensayos",
        familia="carry",
        carril="david",
        autor="x",
        comando="x",
        commit="x",
    )
    assert ledger.trials() == []  # evaluar la configuración elegida no es un ensayo nuevo

    assert cli.main(args) == 2
    assert "ya se abrió" in capsys.readouterr().err
    assert _filas(entorno) == ["holdout"]
