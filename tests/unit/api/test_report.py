import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api import cli, report
from prometheus_platform.api.report import (
    FIGURES,
    NA,
    build_public_page,
    build_report_inputs,
    num,
    pct,
    to_markdown,
)
from prometheus_platform.domain.events import OrderFilled, OrderSubmitted, PortfolioValued
from prometheus_platform.domain.model import InstrumentId, Side, Venue


def test_spanish_number_formatting() -> None:
    assert pct(0.0503) == "5,0 %"
    assert pct(-0.0095, 2) == "-0,95 %"
    assert num(614731, 0) == "614.731"
    assert num(1234.5678) == "1.234,57"
    assert pct(None) == NA
    assert num(None) == NA


def test_markdown_tables_apply_formats_and_handle_empties() -> None:
    frame = pl.DataFrame({"m": ["a"], "r": [0.05], "v": [None]})
    assert to_markdown(frame, {"r": "pct"}).splitlines() == [
        "| m | r | v |",
        "|---|---|---|",
        f"| a | 5,0 % | {NA} |",
    ]
    assert to_markdown(pl.DataFrame()) == "*Sin datos.*\n"


def test_inputs_without_artifacts_still_build_a_report(tmp_path: Path) -> None:
    out = tmp_path / "out"
    missing = build_report_inputs(tmp_path / "lake", tmp_path / "repo", out)

    assert len(missing) == 6  # incluye el presupuesto de capital (PQ-83)
    values = json.loads((out / "_resultados.yml").read_text(encoding="utf-8"))["r"]
    assert values["h2"]["cagr"] == NA
    assert values["sim"]["quiebra_equilibrio"] == NA
    assert "no disponible" in (out / "_tablas/gates-h2.md").read_text(encoding="utf-8")
    assert {p.stem for p in (out / "_figuras").glob("*.md")} == set(FIGURES)
    assert "no disponible" in (out / "_figuras/h2-curvas.md").read_text(encoding="utf-8")


def test_inputs_come_from_the_json_results(tmp_path: Path) -> None:
    lake, repo, out = tmp_path / "lake", tmp_path / "repo", tmp_path / "out"
    carry = lake / "research/carry/H2"
    carry.mkdir(parents=True)
    perf = {"cagr": 0.0503, "sharpe": 5.57, "max_drawdown": -0.0039}
    (carry / "summary.json").write_text(
        json.dumps(
            {
                "symbols": ["SOLUSDT"],
                "selected": "k9-theta20",
                "pbo": 0.045,
                "dsr": 1.0,
                "selected_performance": perf,
                "benchmark_B1": {**perf, "cagr": 0.025},
                "gates": [{"name": "G4", "criterion": "c", "value": 5.57, "passed": False}],
            }
        ),
        encoding="utf-8",
    )
    sim = lake / "research/simulation"
    sim.mkdir(parents=True)
    (sim / "summary.json").write_text(
        json.dumps(
            {
                "escenarios": {"base": {"media": 0.0441}, "p2": {"media": 0.0215}},
                "probabilidad_quiebra_equilibrio": 0.00397,
                "frontera": [
                    {"w_carry": 0.0, "cumple": True},
                    {"w_carry": 0.15, "cumple": True},
                    {"w_carry": 0.2, "cumple": False},
                ],
                "validacion": [
                    {"model": "historia", "cycles": 5.39},
                    {"model": "v3", "cycles": 7.07},
                ],
            }
        ),
        encoding="utf-8",
    )
    figure = repo / FIGURES["h2-curvas"][0]
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")

    build_report_inputs(lake, repo, out)
    values = json.loads((out / "_resultados.yml").read_text(encoding="utf-8"))["r"]
    assert values["h2"]["cagr"] == "5,0 %"
    assert values["h2"]["b1_cagr"] == "2,5 %"
    assert values["h2"]["veredicto"] == "no pasa G4"
    assert values["sim"]["media_p2"] == "2,15 %"
    assert values["sim"]["media_p5"] == NA
    assert values["sim"]["quiebra_equilibrio"] == "0,40 %"
    assert values["sim"]["max_carry_cvar"] == "15 %"
    assert values["sim"]["ciclos_sim"] == "7,1"
    assert (out / "_img/h2-curvas.png").read_bytes() == b"png"
    assert "_img/h2-curvas.png" in (out / "_figuras/h2-curvas.md").read_text(encoding="utf-8")


@pytest.fixture
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


@pytest.mark.usefixtures("reset_structlog")
def test_cli_report_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    assert cli.main(["report", "inputs", "--out", str(tmp_path / "r")]) == 0
    out = capsys.readouterr().out
    assert "falta el artefacto «simulación»" in out
    assert (tmp_path / "r/_resultados.yml").exists()


def test_conclusion_inputs_come_from_stats_finance_and_the_trial_ledger(tmp_path: Path) -> None:
    """PQ-59: las cifras de las conclusiones (7.4, 8.3 a 8.4 y N) también salen de artefactos."""
    lake, repo, out = tmp_path / "lake", tmp_path / "repo", tmp_path / "out"
    stats = lake / "research/stats"
    stats.mkdir(parents=True)
    (stats / "summary.json").write_text(
        json.dumps(
            {
                "he1": {"mean_annualized": 0.0236, "p_hac": 0.0441, "reject_h0": True},
                "he2": {"mean_annualized": 0.0491, "p_hac": 0.1458, "reject_h0": False},
                "he3": {"friedman_p": 1.5e-35, "kendall_w": 0.0127, "reject_h0": True},
            }
        ),
        encoding="utf-8",
    )
    finance = lake / "research/finance"
    finance.mkdir(parents=True)
    oracle = "Oracle Cloud Always Free (Ampere A1)"
    rows = [
        {"escenario": "sin quiebra", "infraestructura": oracle, "capital": 1000.0, "anios": 3,
         "van": -315.07, "capital_equilibrio": 28368.0},
        {"escenario": "sin quiebra", "infraestructura": "Laptop", "capital": 1000.0, "anios": 3,
         "van": -200.0, "capital_equilibrio": 25000.0},
        {"escenario": "p = 2%", "infraestructura": oracle, "capital": 1000.0, "anios": 3,
         "van": -377.92, "capital_equilibrio": None},
    ]  # fmt: skip
    (finance / "summary.json").write_text(
        json.dumps({"escenarios": {"sin quiebra": {}, "p = 2%": {}}, "evaluaciones": rows}),
        encoding="utf-8",
    )
    ledger = repo / "docs/estrategias/ensayos"
    ledger.mkdir(parents=True)
    row = {
        "fecha": "2026-11-01T00:00:00+00:00",
        "autor": "a",
        "carril": "david",
        "familia": "carry",
        "hipotesis": "H2",
        "nombre": "n",
        "commit": "c",
        "cuenta_en_n": True,
        "comando": "pq",
    }
    lines = [
        json.dumps(row),
        json.dumps({**row, "familia": "modelo-funding"}),
        json.dumps({**row, "familia": "descriptivo", "cuenta_en_n": False}),
    ]
    (ledger / "david.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    build_report_inputs(lake, repo, out)
    values = json.loads((out / "_resultados.yml").read_text(encoding="utf-8"))["r"]
    assert values["stats"]["he1_exceso"] == "2,36 %"
    assert values["stats"]["he1_p"] == "0,044"
    assert values["stats"]["he2_veredicto"] == "no se rechaza"
    assert values["stats"]["he3_w"] == "0,013"
    assert values["finanzas"]["van_1000_3a"] == "-315 USD"
    assert values["finanzas"]["equilibrio"] == "28.368 USD"
    assert values["finanzas"]["van_negativo"] == "en todos los casos evaluados"
    assert values["ensayos"] == {
        "total": "2",
        "carry": "1",
        "modelo": "1",
        "tendencia": "0",
        "otras": "0",
    }
    # Sin artefactos de la prueba final, sus valores quedan como «n/d» (PQ-77).
    assert values["final_carry"]["veredicto"] == "n/d"


def test_conclusion_inputs_are_na_without_artifacts(tmp_path: Path) -> None:
    build_report_inputs(tmp_path / "lake", tmp_path / "repo", tmp_path / "out")
    values = json.loads((tmp_path / "out/_resultados.yml").read_text(encoding="utf-8"))["r"]
    assert values["stats"]["he1_p"] == NA
    assert values["finanzas"]["equilibrio"] == NA
    assert values["ensayos"]["total"] == NA


def test_public_page_aggregates_paper_trading_without_identifiers(tmp_path: Path) -> None:
    """PQ-89: la página del jurado sale de los artefactos y no expone órdenes ni cuentas."""
    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    lake = tmp_path / "lake"
    journal = JsonlEventJournal(lake / "paper" / "diario.jsonl")
    for days, equity in ((2, "1000"), (1, "990"), (0, "1005")):
        journal.append(
            PortfolioValued(
                occurred_at=now - timedelta(days=days),
                equity=Decimal(equity),
                cash=Decimal(0),
                gross_notional=Decimal(0),
            )
        )
    order = "entrada-20261121T120000-SOLUSDT"
    journal.append(
        OrderSubmitted(
            occurred_at=now,
            client_order_id=order,
            instrument=InstrumentId("SOLUSDT", Venue.BINANCE),
            side=Side.BUY,
            quantity=Decimal(1),
        )
    )
    journal.append(
        OrderFilled(
            occurred_at=now,
            client_order_id=order,
            fill_price=Decimal(100),
            fill_quantity=Decimal(1),
            fee=Decimal("0.1"),
        )
    )

    page = build_public_page(lake, tmp_path / "repo", now)
    assert "No es asesoramiento financiero" in page
    assert "| Capital actual (simulado) | 1.005,00 USD |" in page
    assert "| Variación | 0,500 % |" in page
    assert "| Caída máxima | 1,000 % |" in page
    assert "| Órdenes ejecutadas | 1 |" in page
    assert "Todavía no hubo operaciones" not in page
    assert order not in page  # ni ids de órdenes ni de cuenta
    assert "Actualizado: 2026-11-21 12:00 UTC" in page


def test_public_page_without_artifacts_still_builds(tmp_path: Path) -> None:
    page = build_public_page(
        tmp_path / "lake", tmp_path / "repo", datetime(2026, 11, 21, tzinfo=UTC)
    )
    assert "Todavía no hay historial de paper trading" in page
    assert "Artefacto no disponible" in page
    assert "| H2 (" in page


@pytest.mark.usefixtures("reset_structlog")
def test_cli_report_public(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    out = tmp_path / "resultados.md"
    assert cli.main(["report", "public", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Resultados")
    assert "página pública" in capsys.readouterr().out


def test_the_final_test_values_say_when_a_strategy_was_discarded() -> None:
    """PQ-77: el póster y la página pública muestran la prueba final, no «sigue cerrado»."""
    summary = {
        "seleccionada": "k9-theta20",
        "rendimiento": {"cagr": 0.0021578, "sharpe": 1.7327, "max_drawdown": -0.00107},
        "pasa": False,
    }
    values = report._holdout_values(summary)
    assert values == {
        "cagr": "0,22 %",
        "sharpe": "1,73",
        "max_dd": "-0,1 %",
        "veredicto": "descartada",
        "config": "k9-theta20",
    }
    assert report._holdout_values({**summary, "pasa": True})["veredicto"] == "pasa"
