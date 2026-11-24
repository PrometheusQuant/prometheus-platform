"""Comandos ``pq polymarket`` (PQ-92): flujo completo contra un transporte simulado."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from prometheus_platform.api import polymarket_cli
from prometheus_platform.api.cli import build_parser

MARKET = {
    "id": "1",
    "conditionId": "0xc1",
    "question": "¿Pasa?",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["1", "0"]',
    "clobTokenIds": '["111", "222"]',
    "endDate": "2024-03-10T12:00:00Z",
    "closedTime": "2024-03-11 08:00:00+00",
    "volumeNum": 1500,
    "tags": [{"label": "Politics"}],
    "events": [{"id": 9}],
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/markets":
        in_march = request.url.params["end_date_min"].startswith("2024-03")
        return httpx.Response(200, json=[MARKET] if in_march else [])
    if path == "/prices-history":
        return httpx.Response(200, json={"history": [{"t": 1709251200, "p": 0.8}]})
    if path == "/v2/trades":
        return httpx.Response(200, json={"data": [{"price": 0.8}], "pagination": {}})
    return httpx.Response(404)


def client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def run(argv: list[str], data_dir: Path) -> int:
    args = build_parser().parse_args(["polymarket", *argv])
    return polymarket_cli.run(args, data_dir, client)


def test_full_flow_markets_silver_prices_trades(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(["mercados", "--desde", "2024-02", "--hasta", "2024-03"], tmp_path) == 0
    assert run(["silver"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "polymarket/markets: 1 filas" in out
    assert "al menos 5000 mercados: NO" in out

    assert run(["precios", "--desde", "2024-03", "--hasta", "2024-03"], tmp_path) == 0
    assert run(["silver"], tmp_path) == 0
    prices = pl.read_parquet(tmp_path / "silver" / "polymarket" / "prices_1440.parquet")
    assert sorted(prices["token_id"].to_list()) == ["111", "222"]

    assert run(["operaciones"], tmp_path) == 0
    trades = list((tmp_path / "bronze").rglob("dataset=trades/**/*.parquet"))
    assert len(trades) == 1
    assert json.loads(pl.read_parquet(trades[0])["raw"][0]) == {"price": 0.8}


def test_month_filter_leaves_markets_outside_the_range(tmp_path: Path) -> None:
    run(["mercados", "--desde", "2024-03", "--hasta", "2024-03"], tmp_path)
    run(["silver"], tmp_path)
    assert run(["precios", "--desde", "2024-04"], tmp_path) == 0
    assert not list((tmp_path / "bronze").rglob("dataset=prices/**/*.parquet"))


def test_prices_need_the_markets_silver(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="pq polymarket silver"):
        run(["precios"], tmp_path)


def test_silver_without_bronze_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(["silver"], tmp_path) == 1
    assert "silver no se construyó" in capsys.readouterr().out


def test_failed_months_return_an_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))

    args = build_parser().parse_args(
        ["polymarket", "mercados", "--desde", "2024-03", "--hasta", "2024-03"]
    )
    assert polymarket_cli.run(args, tmp_path, broken) == 1
    assert "FALLÓ markets/2024-03" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("today", "expected"),
    [(date(2026, 11, 24), date(2026, 8, 1)), (date(2026, 2, 3), date(2025, 11, 1))],
)
def test_recent_months_are_refreshed_by_default(today: date, expected: date) -> None:
    assert polymarket_cli._refresh_default(today) == expected


def test_bad_month_is_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["polymarket", "mercados", "--desde", "2024-13", "--hasta", "2024-12"]
        )
