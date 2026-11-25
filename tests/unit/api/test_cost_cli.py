"""Comandos de costes del paper (PQ-95): informe y salvaguardas del muestreo en Binance Demo."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper import cost_cli
from prometheus_platform.api.paper.compose import PaperPaths, paper_dir
from prometheus_platform.domain.events import OrderFilled, OrderSubmitted
from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.ops.settings import Environment, Settings

T0 = datetime(2026, 11, 25, 12, tzinfo=UTC)


def _no_exchange(*_args: object) -> None:
    raise AssertionError("no debió conectarse al exchange")


def sample_args(symbols: str, *, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        symbols=symbols, nocional=Decimal(100), rondas=1, incluir_simbolos_del_runner=force
    )


def test_sampling_refuses_the_symbols_the_demo_runner_trades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cost_cli, "binance_demo_execution", _no_exchange)
    code = cost_cli.sample_costs_command(
        sample_args("btcusdt, SOLUSDT"), Settings(data_dir=tmp_path)
    )
    assert code == 2
    assert "SOLUSDT" in capsys.readouterr().out
    assert not (paper_dir(tmp_path, "binance-demo") / cost_cli.SAMPLE_JOURNAL).exists()


def test_the_default_symbols_are_not_the_runner_ones() -> None:
    assert not cost_cli.RUNNER_SYMBOLS.intersection(cost_cli.SAMPLE_SYMBOLS)


def test_sampling_never_runs_in_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cost_cli, "binance_demo_execution", _no_exchange)
    live = Settings.model_construct(environment=Environment.LIVE, data_dir=tmp_path)
    assert cost_cli.sample_costs_command(sample_args("BTCUSDT"), live) == 2


def test_report_measures_each_journal_and_leaves_an_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = paper_dir(tmp_path, "binance-demo")
    root.mkdir(parents=True)
    journal = JsonlEventJournal(root / cost_cli.SAMPLE_JOURNAL)
    journal.append(
        OrderSubmitted(
            occurred_at=T0,
            client_order_id="x",
            instrument=InstrumentId("BTCUSDT-PERP", Venue.BINANCE),
            side=Side.SELL,
            quantity=Decimal(1),
        )
    )
    journal.append(
        OrderFilled(
            occurred_at=T0,
            client_order_id="x",
            fill_price=Decimal("99.97"),
            fill_quantity=Decimal(1),
            fee=Decimal("0.049985"),
            slippage=Decimal("0.03"),
        )
    )
    assert not PaperPaths(root).journal.exists()  # el runner aún no tiene diario
    code = cost_cli.costs_report(
        argparse.Namespace(broker="binance-demo"), Settings(data_dir=tmp_path)
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Sin diario" in out  # el del runner
    assert "| perp | 1 | 3.00 pb" in out
    artifact = json.loads(
        (tmp_path / "research/costes/binance-demo-muestreo.json").read_text(encoding="utf-8")
    )
    assert artifact["source"] == "binance-demo/muestreo"
    assert artifact["legs"][0]["assumed_slippage_bp"] == pytest.approx(2.0)  # BTC: 2 pb
    assert not (tmp_path / "research/costes/binance-demo-runner.json").exists()
