import json
from pathlib import Path

import pytest

from prometheus_platform.api import cli
from prometheus_platform.research import finance as fin


def test_npv_and_irr_match_known_values() -> None:
    flows = [-100.0, 60.0, 60.0]
    # VAN al 10 %: -100 + 60/1,1 + 60/1,21
    assert fin.npv(0.10, flows) == pytest.approx(-100 + 60 / 1.1 + 60 / 1.21)
    rate = fin.irr(flows)
    assert rate is not None
    assert fin.npv(rate, flows) == pytest.approx(0.0, abs=1e-9)
    assert rate == pytest.approx(0.130662, abs=1e-6)  # raíz de 100(1+r)^2 = 60(1+r) + 60
    assert fin.irr([-100.0, 110.0]) == pytest.approx(0.10)


def test_irr_is_none_without_a_sign_change() -> None:
    assert fin.irr([-100.0, -10.0, -10.0]) is None  # nunca se recupera
    assert fin.irr([0.0, 10.0]) is None


def test_break_even_capital_gives_zero_npv() -> None:
    excess, cost, initial, years = 0.01, 120.0, 20.0, 3
    capital = fin.break_even_capital(excess, cost, initial, 0.04, years)
    assert capital is not None
    flows = [-initial] + [capital * excess - cost] * years
    assert fin.npv(0.04, flows) == pytest.approx(0.0, abs=1e-6)
    assert fin.break_even_capital(0.0, cost, initial, 0.04, years) is None
    assert fin.break_even_capital(-0.02, cost, initial, 0.04, years) is None


def test_evaluate_builds_the_incremental_flow() -> None:
    labor = fin.Labor(tarifa_usd_hora=2.0, horas_operacion_mes=5.0, horas_puesta_en_marcha=10.0)
    infra = fin.Quote("VPS", 6.0, "https://ejemplo", "2026-11-06", True)
    result = fin.evaluate(
        escenario="x", retorno_anual=0.06, infra=infra, labor=labor, capital=10_000.0, years=3
    )
    annual_cost = 12 * (6.0 + 5.0 * 2.0)  # 192 USD
    assert result.inversion_inicial == pytest.approx(20.0)
    assert result.flujo_anual == pytest.approx(10_000 * 0.02 - annual_cost)
    assert result.van == pytest.approx(fin.npv(0.04, [-20.0] + [result.flujo_anual] * 3))


def test_min_wage_rate_is_derived_from_the_declared_sources() -> None:
    expected = 3_300 / 240 / 11.89
    assert pytest.approx(expected) == fin.MIN_WAGE_USD_HOUR
    assert all(q.verificado for q in fin.INFRA_OPTIONS)
    assert not fin.DOMAIN.verificado  # no se pudo leer en la fuente oficial


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "research" / "simulation" / "summary.json"
    path.parent.mkdir(parents=True)
    escenarios = {
        "sin quiebra": {"media": 0.06, "p5": -0.01, "p95": 0.15, "cvar95": 0.02},
        "quiebra": {"media": 0.02, "p5": -1.0, "p95": 0.14, "cvar95": 1.0},
    }
    path.write_text(json.dumps({"escenarios": escenarios}), encoding="utf-8")
    return tmp_path


def test_run_finance_covers_every_scenario_infra_capital_and_horizon(data_dir: Path) -> None:
    summary = fin.run_finance(data_dir)
    expected = 2 * len(fin.INFRA_OPTIONS) * len(fin.CAPITALS) * len(fin.HORIZONS)
    assert len(summary.evaluaciones) == expected
    losing = [e for e in summary.evaluaciones if e["escenario"] == "quiebra"]
    assert all(e["capital_equilibrio"] is None for e in losing)  # r_P < 4 %: nunca compensa
    assert summary.sensibilidad_tarifa[0]["usd_hora"] == 0.0
    assert summary.sensibilidad_tarifa[0]["capital_equilibrio"] == pytest.approx(0.0)


def test_markdown_block_is_generated_and_replaced_in_place(data_dir: Path, tmp_path: Path) -> None:
    summary = fin.run_finance(data_dir)
    block = fin.render_markdown(summary)
    assert block.startswith(fin.DOC_START)
    assert block.endswith(fin.DOC_END)
    assert "**por verificar**" in block
    assert "<https://www.hetzner.com/cloud/>" in block

    doc = tmp_path / "modelo.md"
    doc.write_text("# Modelo\n\nTexto de Boris.\n", encoding="utf-8")
    fin.update_document(doc, block)
    fin.update_document(doc, block)  # idempotente: reemplaza, no duplica
    text = doc.read_text(encoding="utf-8")
    assert text.count(fin.DOC_START) == 1
    assert text.startswith("# Modelo\n\nTexto de Boris.")


def test_cli_writes_summary_and_updates_the_document(
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(data_dir))
    doc = tmp_path / "doc.md"
    doc.write_text("# Doc\n", encoding="utf-8")
    assert cli.main(["research", "finance", "--update-doc", str(doc)]) == 0
    out = capsys.readouterr().out
    assert "capital de equilibrio" in out
    assert (data_dir / "research" / "finance" / "summary.json").is_file()
    assert fin.DOC_START in doc.read_text(encoding="utf-8")
