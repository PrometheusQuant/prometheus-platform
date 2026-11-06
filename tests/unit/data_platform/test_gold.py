import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest

from prometheus_platform.api import cli
from prometheus_platform.data_platform.gold import (
    DICTIONARY_FILE,
    TABLES,
    GoldReport,
    GoldValidationError,
    build_tables,
    render_docs_page,
    validate,
    write_gold,
)

REPO = Path(__file__).parents[3]
T0 = datetime(2024, 6, 29, tzinfo=UTC)  # dos días antes del holdout


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def hours(n: int, start: datetime = T0) -> list[datetime]:
    return [start + timedelta(hours=h) for h in range(n)]


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    """Lakehouse mínimo: 2 símbolos, datos que cruzan el inicio del holdout y artefactos de H2."""
    root = tmp_path / "data"
    silver = root / "silver"
    times = hours(24 * 4)  # 29-jun → 2-jul: los dos últimos días son holdout
    for symbol, price in (("SOLUSDT", 100.0), ("BTCUSDT", 60_000.0)):
        funding_times = times[::8]
        (silver / "funding").mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {
                "event_time": funding_times,
                "funding_rate": [0.0001] * len(funding_times),
                "funding_rate_annualized": [0.1095] * len(funding_times),
            }
        ).write_parquet(silver / "funding" / f"{symbol}.parquet")
        for market, bump in (("spot", 0.0), ("um", 0.1)):
            folder = silver / "klines" / f"market={market}" / "interval=1h"
            folder.mkdir(parents=True, exist_ok=True)
            pl.DataFrame(
                {
                    "open_time": times,
                    "close": [price + bump + i for i in range(len(times))],
                    "quote_volume": [10.0] * len(times),
                }
            ).write_parquet(folder / f"{symbol}.parquet")

    write_json(
        silver / "_quality" / "funding-SOLUSDT.json", {"table": "funding/SOLUSDT", "rows": 12}
    )
    (silver / "_quality" / "roto.json").write_text("{no es json", encoding="utf-8")

    carry = root / "research" / "carry" / "H2"
    perf = {"sharpe": 2.0, "cagr": 0.05, "max_drawdown": -0.01, "calmar": 5.0, "t_stat": 4.0}
    write_json(
        carry / "summary.json",
        {
            "symbols": ["SOLUSDT"],
            "selected": "k9-theta20",
            "cpcv_mean_test_sharpe": {"k9-theta20": 5.5, "k3-theta10": 1.1},
            "selected_performance": perf | {"days": 3},
            "benchmark_B1": perf | {"sharpe": 0.6, "days": 3},
            "gates": [{"name": "G1", "criterion": "DSR > 0.95", "value": 0.99, "passed": True}],
        },
    )
    # Como los artefactos reales: la fecha ISO como texto, valorada a las 00:00 del día siguiente.
    pl.DataFrame(
        {
            "date": [
                "2024-06-30 00:00:00+00:00",
                "2024-07-01 00:00:00+00:00",
                "2024-07-02 00:00:00+00:00",
            ],
            "k9-theta20": [0.01, 0.02, 0.5],
            "k3-theta10": [0.0, -0.01, 0.5],
        }
    ).write_parquet(carry / "daily_returns.parquet")

    write_json(
        root / "research" / "funding_model" / "residual" / "summary.json",
        {
            "regression": [{"name": "ridge", "tuned": True, "rmse": 1.0, "mae": 0.1, "r2": 0.7}],
            "classification": [{"name": "rf", "tuned": False, "auc": 0.97, "f1": float("nan")}],
        },
    )
    write_json(
        root / "research" / "simulation" / "summary.json",
        {
            "escenarios": {"sin quiebra": {"media": 0.044, "prob_perdida": 0.16}},
            "frontera": [
                {"w_carry": 0.1, "retorno_esperado": 0.04, "cvar95": 0.01, "cumple": True}
            ],
        },
    )
    return root


def test_builds_every_declared_table_with_its_schema(lake: Path) -> None:
    report = GoldReport()
    tables = build_tables(lake, report)
    assert list(tables) == [t.name for t in TABLES]
    for table in TABLES:
        assert tables[table.name].schema == table.schema
    assert report.rows["fact_funding_diario"] == 4  # 2 símbolos x 2 días de desarrollo
    assert report.missing == [str(lake / "silver" / "_quality" / "roto.json")]


def test_no_dated_fact_reaches_the_holdout(lake: Path) -> None:
    tables = build_tables(lake)
    for name in ("fact_funding_diario", "fact_mercado_diario", "fact_retorno_estrategia"):
        # El 30 de junio se devenga hasta la liquidación del 1 de julio 00:00 (holdout): fuera.
        assert tables[name]["fecha"].max() == date(2024, 6, 29)
    assert set(tables["dim_fecha"]["periodo"]) == {"desarrollo"}


def test_returns_are_dated_by_the_day_they_belong_to_and_compounded(lake: Path) -> None:
    ret = build_tables(lake)["fact_retorno_estrategia"].filter(
        pl.col("configuracion_id") == "H2/k9-theta20"
    )
    # 2024-06-30 00:00 → retorno del 29. La valoración del 2024-07-01 00:00 incluye la
    # liquidación de ese instante, que ya es holdout (KE-014): queda fuera, igual que la del 2.
    assert ret["fecha"].to_list() == [date(2024, 6, 29)]
    assert ret["capital"].to_list() == pytest.approx([1.01])


def test_funding_is_dated_by_accrual_day(lake: Path) -> None:
    funding = build_tables(lake)["fact_funding_diario"].filter(pl.col("simbolo") == "SOLUSDT")
    # La liquidación del 29 a las 00:00 se devengó el 28; el 29 suma 08:00, 16:00 y 30/06 00:00.
    assert funding["fecha"].to_list() == [date(2024, 6, 28), date(2024, 6, 29)]
    assert funding["liquidaciones"].to_list() == [1, 3]


def test_dimensions_and_derived_facts(lake: Path) -> None:
    tables = build_tables(lake)
    symbols = tables["dim_simbolo"].rows_by_key("simbolo", named=True, unique=True)
    assert symbols["SOLUSDT"]["hipotesis"] == "H2"
    assert symbols["BTCUSDT"]["hipotesis"] is None
    assert symbols["SOLUSDT"]["activo_base"] == "SOL"

    configs = tables["dim_configuracion"].rows_by_key("configuracion_id", named=True, unique=True)
    assert configs["H2/k9-theta20"]["es_seleccionada"]
    assert configs["H2/k9-theta20"]["ventana_k"] == 9
    assert configs["H2/k9-theta20"]["umbral_theta"] == pytest.approx(0.2)
    assert configs["H2/B1-siempre-activo"]["es_benchmark"]
    assert configs["H2/B1-siempre-activo"]["ventana_k"] is None

    market = tables["fact_mercado_diario"].filter(pl.col("simbolo") == "SOLUSDT").row(0, named=True)
    assert market["cierre_perp"] - market["cierre_spot"] == pytest.approx(0.1)
    assert market["volumen_spot_usd"] == pytest.approx(240.0)
    assert (market["horas_spot"], market["horas_perp"]) == (24, 24)

    metrics = tables["fact_metricas_modelo"].rows_by_key("modelo_id", named=True, unique=True)
    assert metrics["regresion/ridge/ajustado"]["auc"] is None  # no aplica: nulo, no cero
    assert metrics["clasificacion/rf/por-defecto"]["f1"] is None  # NaN → nulo
    assert tables["fact_desempeno"]["configuracion_id"].to_list() == [
        "H2/k9-theta20",
        "H2/B1-siempre-activo",
    ]
    assert tables["fact_gates"]["gate_id"].to_list() == ["H2/G1"]
    assert tables["fact_escenarios"]["mediana"].to_list() == [None]
    assert tables["fact_frontera"]["cumple"].to_list() == [True]


def test_empty_lake_builds_empty_tables_and_lists_what_is_missing(tmp_path: Path) -> None:
    report = GoldReport()
    tables = build_tables(tmp_path, report)
    assert all(frame.is_empty() for frame in tables.values())
    assert any("funding_model" in m for m in report.missing)
    assert any("simulation" in m for m in report.missing)


@pytest.mark.parametrize(
    ("table", "corrupt", "message"),
    [
        ("dim_simbolo", lambda f: pl.concat([f, f]), "duplicada"),
        (
            "fact_funding_diario",
            lambda f: f.head(1).with_columns(pl.lit("XYZUSDT").alias("simbolo")),
            "sin dim_simbolo",
        ),
        (
            "fact_retorno_estrategia",
            lambda f: f.head(1).with_columns(pl.lit(date(2024, 7, 1)).alias("fecha")),
            "sin dim_fecha",
        ),
        ("fact_gates", lambda f: f.drop("pasa"), "esquema"),
        (
            "dim_modelo",
            lambda f: f.with_columns(pl.lit(None, pl.String).alias("modelo_id")),
            "nulos",
        ),
    ],
)
def test_validation_rejects_broken_tables(
    lake: Path, table: str, corrupt: object, message: str
) -> None:
    tables = build_tables(lake)
    tables[table] = corrupt(tables[table])  # type: ignore[operator]
    with pytest.raises(GoldValidationError, match=message):
        validate(tables)


def test_validation_rejects_holdout_rows_even_with_a_matching_calendar(lake: Path) -> None:
    tables = build_tables(lake)
    late = date(2024, 7, 1)
    tables["dim_fecha"] = pl.concat(
        [
            tables["dim_fecha"],
            tables["dim_fecha"].tail(1).with_columns(pl.lit(late).alias("fecha")),
        ]
    )
    tables["fact_funding_diario"] = pl.concat(
        [
            tables["fact_funding_diario"],
            tables["fact_funding_diario"].tail(1).with_columns(pl.lit(late).alias("fecha")),
        ]
    )
    with pytest.raises(GoldValidationError, match="posteriores al 2024-06-29"):
        validate(tables)


def test_validation_rejects_a_calendar_with_gaps_and_non_finite_returns(lake: Path) -> None:
    tables = build_tables(lake)
    gapped = dict(
        tables, dim_fecha=tables["dim_fecha"].filter(pl.col("fecha") != date(2024, 6, 28))
    )
    gapped["fact_funding_diario"] = gapped["fact_funding_diario"].filter(
        pl.col("fecha") != date(2024, 6, 28)
    )
    gapped["dim_fecha"] = pl.concat(
        [
            gapped["dim_fecha"],
            tables["dim_fecha"].head(1).with_columns(pl.lit(date(2024, 6, 20)).alias("fecha")),
        ]
    )
    with pytest.raises(GoldValidationError, match="huecos"):
        validate(gapped)

    broken = dict(tables)
    broken["fact_retorno_estrategia"] = tables["fact_retorno_estrategia"].with_columns(
        pl.lit(float("nan")).alias("retorno")
    )
    with pytest.raises(GoldValidationError, match="NaN"):
        validate(broken)


def test_returns_valued_outside_midnight_stop_the_build(lake: Path) -> None:
    path = lake / "research" / "carry" / "H2" / "daily_returns.parquet"
    pl.DataFrame({"date": ["2024-06-30 08:00:00+00:00"], "k9-theta20": [0.01]}).write_parquet(path)
    with pytest.raises(GoldValidationError, match="00:00 UTC"):
        build_tables(lake)


def test_a_day_without_any_value_stays_null_not_zero(lake: Path) -> None:
    path = lake / "silver" / "funding" / "SOLUSDT.parquet"
    pl.read_parquet(path).with_columns(
        pl.lit(None, pl.Float64).alias("funding_rate")
    ).write_parquet(path)
    funding = build_tables(lake)["fact_funding_diario"].filter(pl.col("simbolo") == "SOLUSDT")
    assert funding["funding_total"].to_list() == [None, None]


def test_write_gold_produces_parquet_duckdb_csv_and_dictionary(lake: Path, tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    write_gold(build_tables(lake), gold)
    write_gold(build_tables(lake), gold)  # idempotente: se puede reconstruir encima
    assert {p.stem for p in gold.glob("*.parquet")} == {t.name for t in TABLES}
    assert (gold / "export" / "fact_gates.csv").read_text(encoding="utf-8").startswith("gate_id,")
    assert "## `fact_retorno_estrategia` (hecho)" in (gold / "export" / DICTIONARY_FILE).read_text(
        encoding="utf-8"
    )
    with duckdb.connect(str(gold / "gold.duckdb"), read_only=True) as db:
        joined = db.sql(
            "select count(*) from fact_retorno_estrategia r "
            "join dim_configuracion c using (configuracion_id) join dim_fecha f using (fecha)"
        ).fetchall()
    assert joined == [(2,)]  # 2 configuraciones x 1 día de desarrollo


def test_documentation_page_is_up_to_date() -> None:
    page = (REPO / "docs" / "arquitectura" / "modelo-gold.md").read_text(encoding="utf-8")
    assert page == render_docs_page(), "regenera la página con: uv run pq gold docs"


def test_cli_builds_gold_and_writes_docs(
    lake: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    assert cli.main(["gold", "build"]) == 0
    assert "fact_retorno_estrategia: filas=2" in capsys.readouterr().out
    assert (lake / "gold" / "gold.duckdb").is_file()

    out = tmp_path / "modelo-gold.md"
    assert cli.main(["gold", "docs", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == render_docs_page()


def test_cli_reports_validation_errors(
    lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    write_json(  # dos gates con el mismo nombre: clave duplicada
        lake / "research" / "carry" / "H2" / "summary.json",
        {"gates": [{"name": "G1", "passed": True}, {"name": "G1", "passed": False}]},
    )
    assert cli.main(["gold", "build"]) == 1
    assert "duplicada" in capsys.readouterr().err
