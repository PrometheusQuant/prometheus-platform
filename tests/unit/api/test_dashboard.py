import json
import os
from pathlib import Path

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

from prometheus_platform.api.dashboard.artifacts import (
    equity_curves,
    gates_table,
    load_artifacts,
    model_tables,
    performance_table,
    quality_table,
    scenario_table,
    transition_table,
    validation_table,
)

APP = Path(__file__).parents[3] / "src/prometheus_platform/api/dashboard/app.py"


def write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    root = tmp_path / "lake"
    write(
        root / "silver/_quality/funding-SOLUSDT.json",
        {
            "table": "funding/SOLUSDT",
            "rows": 10,
            "gaps": 1,
            "missing_periods": 3,
            "largest_gap_hours": 8.0,
            "outliers": 0,
            "first": "2020-09-13 16:00:00+00:00",
            "last": "2026-09-30 16:00:00+00:00",
        },
    )
    (root / "silver/_quality/roto.json").write_text("{no es json", encoding="utf-8")
    perf = {"sharpe": 2.0, "cagr": 0.05, "max_drawdown": -0.01, "calmar": 5.0, "t_stat": 4.0}
    write(
        root / "research/carry/H2/summary.json",
        {
            "hypothesis": "H2",
            "symbols": ["SOLUSDT"],
            "selected": "k9-theta20",
            "pbo": 0.04,
            "dsr": 0.99,
            "passed": True,
            "selected_performance": perf,
            "benchmark_B1": {**perf, "sharpe": 0.6},
            "gates": [{"name": "G1", "criterion": "DSR > 0.95", "value": 0.99, "passed": True}],
        },
    )
    pl.DataFrame(
        {
            "date": ["2020-01-03 00:00:00+00:00", "2020-01-04 00:00:00+00:00"],
            "k9-theta20": [0.01, 0.02],
        }
    ).write_parquet(root / "research/carry/H2/daily_returns.parquet")
    write(
        root / "research/funding_model/residual/summary.json",
        {
            "regression": [{"name": "ridge", "tuned": True, "rmse": 1.0, "mae": 0.1, "r2": 0.7}],
            "classification": [{"name": "rf", "tuned": False, "auc": 0.97, "f1": float("nan")}],
            "diebold_mariano": {"dm": 2.3, "p_value": 0.02, "best_model": "ridge"},
        },
    )
    write(
        root / "research/simulation/summary.json",
        {
            "markov_1er_orden": {"estados": ["negativo", "base", "alto"]},
            "markov_bloques": {"transicion": [[0.8, 0.2, 0.0], [0.1, 0.8, 0.1], [0.0, 0.3, 0.7]]},
            "validacion": [
                {"model": "historia real", "cycles": 5.4, "mean_return": 0.05, "invested": 0.27}
            ],
            "escenarios": {
                "sin quiebra": {
                    "media": 0.044,
                    "mediana": 0.034,
                    "prob_bajo_hurdle": 0.55,
                    "prob_perdida": 0.16,
                    "cvar95": 0.01,
                }
            },
            "probabilidad_quiebra_equilibrio": 0.004,
        },
    )
    return root


def test_empty_lake_reports_every_missing_artifact_with_its_command(tmp_path: Path) -> None:
    art = load_artifacts(tmp_path)
    assert [m.artifact for m in art.missing] == [
        "calidad de silver",
        "carry H1",
        "carry H2",
        "modelo de funding",
        "simulación",
    ]
    assert all(m.command.startswith("uv run pq ") for m in art.missing)
    assert quality_table(art.quality).is_empty()


def test_tables_are_built_from_the_artifacts(lake: Path) -> None:
    art = load_artifacts(lake)
    assert [m.artifact for m in art.missing] == ["carry H1"]  # el JSON roto se ignora

    assert quality_table(art.quality).row(0, named=True)["desde"] == "2020-09-13"
    h2 = art.carry["H2"]
    assert gates_table(h2)["pasa"].to_list() == ["sí"]
    assert performance_table(h2)["B1 siempre activo"][0] == 0.6
    curve = equity_curves(art.carry_returns["H2"], "k9-theta20")
    assert curve["k9-theta20"].to_list() == pytest.approx([1.01, 1.01 * 1.02])
    assert equity_curves(art.carry_returns["H2"], "no-existe").is_empty()

    assert art.model is not None
    assert art.model_mode == "residual"
    regression, classification = model_tables(art.model)
    assert regression["modelo"].to_list() == ["ridge (ajustado)"]
    assert classification["F1"].to_list() == [None]  # NaN se muestra vacío

    assert art.simulation is not None
    assert transition_table(art.simulation).columns == [
        "desde \\ hacia",
        "negativo",
        "base",
        "alto",
    ]
    assert validation_table(art.simulation).height == 1
    assert scenario_table(art.simulation)["P(pérdida)"].to_list() == [0.16]


def app_labels() -> list[str]:
    return [
        "¿Qué pasó? Datos y calidad",
        "¿Funciona? Carry y gates",
        "¿Qué predice? Modelo",
        "¿Qué riesgo hay? Simulación",
        "¿Y si invierto? Simula tu inversión",
        "¿Qué predice hoy? Funding en vivo",
        "¿Cómo va en vivo? Paper trading",
    ]


def run_app(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.chdir(data_dir.parent)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(data_dir))
    return AppTest.from_file(str(APP), default_timeout=60).run()


def test_app_renders_every_tab_with_artifacts(lake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at = run_app(lake, monkeypatch)
    assert not at.exception
    assert [t.label for t in at.tabs] == app_labels()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Configuración elegida (CPCV)"] == "k9-theta20"
    assert metrics["Probabilidad de quiebra anual de equilibrio"] == "0.40%"
    assert any("carry H1" in i.value for i in at.info)


def test_app_degrades_gracefully_without_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = run_app(tmp_path / "vacio", monkeypatch)
    assert not at.exception
    # 5 artefactos faltantes + simulador y predicción sin silver + paper trading sin diario
    assert len(at.info) == 8
    assert not at.dataframe


def test_model_falls_back_to_the_level_formulation(tmp_path: Path) -> None:
    write(tmp_path / "research/funding_model/level/summary.json", {"regression": []})
    write(tmp_path / "research/funding_model/summary.json", {"legado": True})  # se ignora
    art = load_artifacts(tmp_path)
    assert art.model_mode == "level"
    assert art.model == {"regression": []}


def test_live_tab_shows_the_paper_trading_journal(
    lake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PQ-55: la pestaña en vivo lee el diario y el heartbeat que deja el runner."""
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal  # noqa: PLC0415
    from prometheus_platform.domain.events import (  # noqa: PLC0415
        FundingSettled,
        OrderFilled,
        OrderSubmitted,
        PortfolioValued,
        RunnerStarted,
    )
    from prometheus_platform.domain.model import InstrumentId, Side, Venue  # noqa: PLC0415

    now = datetime.now(UTC)
    t0 = now - timedelta(days=1)
    perp = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
    journal = JsonlEventJournal(lake / "paper/diario.jsonl")
    for event in (
        RunnerStarted(
            occurred_at=t0,
            broker="simulado",
            strategy_id="carry-h2",
            symbols="SOLUSDT",
            params="k=9",
        ),
        PortfolioValued(
            occurred_at=t0, equity=Decimal(1000), cash=Decimal(1000), gross_notional=Decimal(0)
        ),
        OrderSubmitted(
            occurred_at=t0,
            client_order_id="20261101T1600-entrada-20261101T170100-SOLUSDT-PERP",
            instrument=perp,
            side=Side.SELL,
            quantity=Decimal(2),
        ),
        OrderFilled(
            occurred_at=t0,
            client_order_id="20261101T1600-entrada-20261101T170100-SOLUSDT-PERP",
            fill_price=Decimal(100),
            fill_quantity=Decimal(2),
            fee=Decimal("0.2"),
        ),
        FundingSettled(
            occurred_at=now,
            symbol="SOLUSDT",
            funding_time=now,
            rate=Decimal("0.0003"),
            interval_hours=8,
            amount=Decimal("0.06"),
            action="mantener",
            s_k="0.33",
            target_open=True,
            was_open=True,
            rebalance=False,
        ),
        PortfolioValued(
            occurred_at=now,
            equity=Decimal("1001.5"),
            cash=Decimal(800),
            gross_notional=Decimal(400),
        ),
    ):
        journal.append(event)
    write(
        lake / "paper/heartbeat.json",
        {
            "at": now.isoformat(),
            "ok": True,
            "detail": "",
            "broker": "simulado",
            "kill_switch": False,
        },
    )

    at = run_app(lake, monkeypatch)

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Equity"] == "1,001.50 USD"
    assert metrics["PnL acumulado"] == "+1.50 USD"
    assert metrics["Funding neto"] == "+0.0600 USD"
    assert any("Runner en marcha" in m.value for m in at.success)
    assert any("Kill-switch armado" in m.value for m in at.success)
