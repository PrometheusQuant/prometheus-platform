"""Funding de otros exchanges en silver y su comparación con Binance (PQ-79)."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
import structlog

from prometheus_platform.adapters.exchange_funding import _MonthlyFundingSource
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.parquet_bronze import ParquetBronzeStore
from prometheus_platform.api import cli
from prometheus_platform.data_platform.ingest import ingest, monthly_funding
from prometheus_platform.data_platform.silver import build_exchange_funding, silver_path
from prometheus_platform.domain.datasets import DatasetKind
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.exchanges import compare, compare_symbol

H = timedelta(hours=8)


class FakeSource(_MonthlyFundingSource):
    """Un mes de liquidaciones cada 8 h, sin red, con el mismo empaquetado que Bybit y OKX."""

    name = "falsa"

    def __init__(self, rate: str) -> None:
        super().__init__(client=None)  # type: ignore[arg-type]
        self.rate = rate

    def _points(self, symbol: str, start: int, end: int) -> list[tuple[int, str]]:
        return [(t, self.rate) for t in range(start, end, 8 * 3_600_000)]


def test_other_exchanges_share_the_bronze_and_silver_schema(tmp_path: Path) -> None:
    store = ParquetBronzeStore(
        tmp_path / "bronze",
        source="bybit_api",
        clock=FixedClock(datetime(2026, 11, 22, tzinfo=UTC)),
    )
    report = ingest(
        monthly_funding("SOLUSDT", date(2022, 1, 1), date(2022, 2, 1)), FakeSource("0.0001"), store
    )
    assert report.ok
    quality = build_exchange_funding(tmp_path, "bybit", "SOLUSDT")
    assert quality.table == "funding/bybit/SOLUSDT"
    assert quality.gaps == 0
    path = silver_path(tmp_path / "silver", DatasetKind.FUNDING_RATE, "SOLUSDT", exchange="bybit")
    assert path == tmp_path / "silver/funding/exchange=bybit/SOLUSDT.parquet"
    frame = pl.read_parquet(path)
    assert frame["funding_rate_annualized"][0] == pytest.approx(0.0001 * 8760 / 8)
    # Binance conserva su ruta de siempre.
    assert silver_path(tmp_path / "silver", DatasetKind.FUNDING_RATE, "SOLUSDT") == (
        tmp_path / "silver/funding/SOLUSDT.parquet"
    )


def silver(
    root: Path, symbol: str, rates: list[float], start: datetime, exchange: str | None = None
) -> None:
    path = silver_path(root, DatasetKind.FUNDING_RATE, symbol, exchange=exchange)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "funding_time": [start + i * H for i in range(len(rates))],
            "funding_rate_annualized": rates,
        },
        schema={"funding_time": pl.Datetime("ms", "UTC"), "funding_rate_annualized": pl.Float64},
    ).write_parquet(path)


def test_compare_uses_only_common_development_settlements(tmp_path: Path) -> None:
    start = HOLDOUT_START - 5 * H
    silver(tmp_path, "SOLUSDT", [0.1, 0.2, 0.1, 0.3, 0.2, 9.0], start)  # el último ya es holdout
    silver(tmp_path, "SOLUSDT", [0.2, 0.2, 0.0, 0.4, 0.3, 9.0], start, exchange="bybit")
    row = compare_symbol(tmp_path, "SOLUSDT", "bybit")
    assert row["liquidaciones_comunes"] == 5  # sin la del holdout
    assert row["media_binance"] == pytest.approx(0.18)
    assert row["media_otro"] == pytest.approx(0.22)
    assert row["mediana_binance"] == pytest.approx(0.2)
    assert row["mediana_otro"] == pytest.approx(0.2)
    assert row["otro_paga_mas"] == pytest.approx(3 / 5)
    assert -1 <= row["correlacion"] <= 1
    assert compare_symbol(tmp_path, "SOLUSDT", "okx")["nota"] == "sin datos del desarrollo"
    assert len(compare(tmp_path, ["SOLUSDT"])) == 2


def test_cli_research_exchanges_and_ingest_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    start = HOLDOUT_START - 5 * H
    silver(tmp_path / "lake/silver", "SOLUSDT", [0.1, 0.2, 0.1, 0.3, 0.2], start)
    silver(tmp_path / "lake/silver", "SOLUSDT", [0.2, 0.2, 0.0, 0.4, 0.3], start, exchange="bybit")
    assert cli.main(["research", "exchanges"]) == 0
    out = capsys.readouterr().out
    assert "SOLUSDT bybit: n=5" in out
    assert "SOLUSDT okx: sin datos del desarrollo" in out
    rows = json.loads((tmp_path / "lake/research/exchanges/summary.json").read_text())
    assert {r["exchange"] for r in rows} == {"bybit", "okx"}
    # Con Bybit u OKX solo hay funding, y --start es obligatorio.
    assert (
        cli.main(["ingest", "--source", "okx", "klines", "--symbol", "SOLUSDT", "--interval", "1h"])
        == 2
    )
    assert cli.main(["ingest", "--source", "bybit", "funding", "--symbol", "SOLUSDT"]) == 2
    structlog.reset_defaults()
