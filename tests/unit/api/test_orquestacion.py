from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

dagster = pytest.importorskip(
    "dagster", reason="instala el grupo orquestacion: uv sync --group orquestacion"
)

from dagster import (  # noqa: E402
    AssetCheckResult,
    AssetCheckSeverity,
    AssetKey,
    DefaultScheduleStatus,
    Definitions,
    MultiPartitionKey,
    build_schedule_context,
    materialize,
)

from prometheus_platform.api.orquestacion import definitions as d  # noqa: E402
from prometheus_platform.data_platform.gold import TABLES, write_gold  # noqa: E402
from prometheus_platform.data_platform.ingest import IngestReport  # noqa: E402
from prometheus_platform.data_platform.silver import QualityReport, SilverValidationError  # noqa: E402


def test_definitions_load_and_research_cannot_be_materialized(tmp_path: Path) -> None:
    defs = d.build_definitions(tmp_path)
    Definitions.validate_loadable(defs)
    graph = defs.resolve_asset_graph()
    for name in ("carry_H1", "carry_H2", "modelo_funding", "simulacion"):
        node = graph.get(AssetKey(["research", name]))
        assert not node.is_materializable  # cada ejecución suma ensayos a N: solo a mano
    job = defs.resolve_job_def("silver_y_gold")
    # Los assets de research aparecen como dependencias (linaje), pero el job no los ejecuta.
    assert {k.to_user_string() for k in job.asset_layer.selected_asset_keys} == {"silver", "gold"}


def test_schedules_start_stopped_and_cover_every_symbol() -> None:
    assert d.bronze_diario.default_status is DefaultScheduleStatus.STOPPED
    assert d.silver_y_gold_diario.default_status is DefaultScheduleStatus.STOPPED
    context = build_schedule_context(scheduled_execution_time=datetime(2026, 11, 6, 6, tzinfo=UTC))
    requests = d.bronze_diario(context)
    assert isinstance(requests, list)
    keys = {r.partition_key for r in requests}
    assert keys == {MultiPartitionKey({"mes": "2026-10-01", "simbolo": s}) for s in d.SYMBOLS}


class FakeClient:
    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_bronze_ingests_spot_perp_and_funding_of_its_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    def fake_ingest(refs: list[Any], *_: object) -> IngestReport:
        seen.extend(refs)
        return IngestReport(skipped=list(refs))

    monkeypatch.setattr(d, "http_client", FakeClient)
    monkeypatch.setattr(d, "ingest", fake_ingest)
    result = materialize(
        [d.bronze],
        resources={"lakehouse": d.Lakehouse(data_dir=str(tmp_path))},
        partition_key=MultiPartitionKey({"mes": "2024-06-01", "simbolo": "SOLUSDT"}),
    )
    assert result.success
    assert len(seen) == 3  # velas spot, velas del perpetuo y funding
    assert all(ref.symbol == "SOLUSDT" and ref.period == date(2024, 6, 1) for ref in seen)


def test_bronze_fails_when_an_archive_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(d, "http_client", FakeClient)
    monkeypatch.setattr(d, "ingest", lambda refs, *_: IngestReport(rejected=list(refs)[:1]))
    result = materialize(
        [d.bronze],
        resources={"lakehouse": d.Lakehouse(data_dir=str(tmp_path))},
        partition_key=MultiPartitionKey({"mes": "2024-06-01", "simbolo": "BTCUSDT"}),
        raise_on_error=False,
    )
    assert not result.success


def test_silver_rebuilds_every_symbol_and_stops_on_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[str] = []

    def fake_build(_root: Path, symbol: str, _interval: str) -> list[QualityReport]:
        built.append(symbol)
        return [QualityReport(table=f"funding/{symbol}", rows=1)]

    monkeypatch.setattr(d, "build_symbol", fake_build)
    lake = {"lakehouse": d.Lakehouse(data_dir=str(tmp_path))}
    assert materialize([d.silver], resources=lake).success
    assert built == list(d.SYMBOLS)

    def failing(_root: Path, symbol: str, _interval: str) -> list[QualityReport]:
        raise SilverValidationError(f"funding/{symbol}", "esquema", "columna faltante")

    monkeypatch.setattr(d, "build_symbol", failing)
    assert not materialize([d.silver], resources=lake, raise_on_error=False).success


def check(fn: Any, root: Path) -> AssetCheckResult:
    """Ejecuta un asset check directamente y devuelve su resultado tipado."""
    result = fn(lakehouse=d.Lakehouse(data_dir=str(root)))
    assert isinstance(result, AssetCheckResult)
    return result


def write_silver_tables(root: Path, *, duplicate: bool = False) -> None:
    for _name, path, key in d._silver_tables(root):
        path.parent.mkdir(parents=True, exist_ok=True)
        times = [datetime(2024, 1, 1, h, tzinfo=UTC) for h in (0, 1, 1 if duplicate else 2)]
        pl.DataFrame({key: times}).write_parquet(path)


def test_silver_key_check_detects_missing_tables_and_duplicates(tmp_path: Path) -> None:
    assert not check(d.silver_tablas_y_claves, tmp_path).passed  # sin tablas
    write_silver_tables(tmp_path)
    assert check(d.silver_tablas_y_claves, tmp_path).passed
    write_silver_tables(tmp_path, duplicate=True)
    assert not check(d.silver_tablas_y_claves, tmp_path).passed


def test_gap_check_warns_without_blocking(tmp_path: Path) -> None:
    quality = tmp_path / "silver" / "_quality"
    quality.mkdir(parents=True)
    (quality / "funding-SOLUSDT.json").write_text('{"table": "funding/SOLUSDT", "gaps": 1}')
    result = check(d.silver_huecos, tmp_path)
    assert not result.passed
    assert result.severity is AssetCheckSeverity.WARN


def test_gold_checks_catch_holdout_rows_and_broken_integrity(tmp_path: Path) -> None:
    gold_dir = tmp_path / "gold"
    write_gold({t.name: t.empty() for t in TABLES}, gold_dir)
    assert check(d.gold_holdout_cerrado, tmp_path).passed
    assert check(d.gold_integridad, tmp_path).passed

    funding = next(t for t in TABLES if t.name == "fact_funding_diario")
    row = {c: None for c in funding.schema.names()} | {"fecha": date(2024, 7, 1), "simbolo": "X"}
    pl.DataFrame([row], schema=funding.schema).write_parquet(gold_dir / f"{funding.name}.parquet")
    assert not check(d.gold_holdout_cerrado, tmp_path).passed
    assert not check(d.gold_integridad, tmp_path).passed
