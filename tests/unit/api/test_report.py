import json
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.api import cli
from prometheus_platform.api.report import (
    FIGURES,
    NA,
    build_report_inputs,
    num,
    pct,
    to_markdown,
)


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

    assert len(missing) == 5
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
