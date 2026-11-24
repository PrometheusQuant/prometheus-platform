import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import polars as pl
import pytest

from prometheus_platform.data_platform.gold import TABLES

REPO = Path(__file__).parents[3]
SCRIPT = REPO / "scripts" / "powerbi.py"


@pytest.fixture(scope="module")
def powerbi() -> ModuleType:
    spec = importlib.util.spec_from_file_location("powerbi", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_committed_queries_match_the_gold_declarations(powerbi: ModuleType) -> None:
    committed = (REPO / "reports" / "powerbi" / "consultas.pq").read_text(encoding="utf-8")
    assert committed == powerbi.render_queries(), (
        "regenera con: uv run python scripts/powerbi.py consultas"
    )


def test_every_table_gets_a_typed_query_with_us_locale(powerbi: ModuleType) -> None:
    queries = powerbi.render_queries()
    for table in TABLES:
        assert f'Carpeta & "{table.name}.csv"' in queries
        for column in table.columns:
            assert f'{{"{column.name}", ' in queries
    assert queries.count('"en-US")') == len(TABLES)


@pytest.fixture
def gold(tmp_path: Path) -> Path:
    tables = {t.name: t.empty() for t in TABLES}
    tables["fact_retorno_estrategia"] = pl.DataFrame(
        {
            "fecha": [date(2024, 6, 27), date(2024, 6, 28), date(2024, 6, 29)],
            "configuracion_id": ["H2/k9-theta20"] * 3,
            "retorno": [0.01, -0.02, 0.0],
            "capital": [1.01, 1.01 * 0.98, 1.01 * 0.98],
        },
        schema=tables["fact_retorno_estrategia"].schema,
    )
    tables["fact_desempeno"] = pl.DataFrame(
        [
            {
                "configuracion_id": "H2/k9-theta20",
                "sharpe": 1.0,
                "cagr": 0.05,
                "max_drawdown": -0.02,
                "calmar": 2.5,
                "t_stat": 3.0,
                "dias": 4,
            }
        ],
        schema=tables["fact_desempeno"].schema,
    )
    tables["fact_gates"] = pl.DataFrame(
        [
            {
                "gate_id": "H2/G1",
                "hipotesis": "H2",
                "gate": "G1",
                "criterio": "x",
                "valor": 1.0,
                "pasa": True,
            },
            {
                "gate_id": "H2/G2",
                "hipotesis": "H2",
                "gate": "G2",
                "criterio": "x",
                "valor": 1.0,
                "pasa": False,
            },
        ],
        schema=tables["fact_gates"].schema,
    )
    for name, frame in tables.items():
        frame.write_parquet(tmp_path / f"{name}.parquet")
    return tmp_path


def test_control_values_use_the_research_formulas(powerbi: ModuleType, gold: Path) -> None:
    values = dict(powerbi.control_values(gold))
    assert values["Filas de fact_retorno_estrategia"] == "3"
    assert values["H2/k9-theta20: Retorno acumulado"] == f"{1.01 * 0.98 - 1:.4%}"
    assert values["H2/k9-theta20: Máximo drawdown"] == f"{0.98 - 1:.4%}"
    assert values["H2/k9-theta20: % días con exposición (retorno ≠ 0)"] == "66.67%"
    assert values["Gates aprobados H2"] == "1 de 2"
    assert "H1/k3-theta20: CAGR" not in values  # sin datos: se omite, no falla
    assert "Mejor AUC (fact_metricas_modelo)" not in values
