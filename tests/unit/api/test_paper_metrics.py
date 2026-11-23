"""Métricas del runner para Prometheus (PQ-71): salen del diario y del heartbeat."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.metrics import PaperCollector, serve_metrics
from prometheus_platform.domain.events import (
    DomainEvent,
    FundingSettled,
    OrderFilled,
    OrderSubmitted,
    PortfolioValued,
    RiskLimitBreached,
    RunnerStarted,
)
from prometheus_platform.domain.model import InstrumentId, Side
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 20, tzinfo=UTC)
SPOT, PERP = spot_instrument("SOLUSDT"), perp_instrument("SOLUSDT")
D = Decimal


def order(  # noqa: PLR0913, PLR0917 - un fill de prueba completo
    at: datetime, oid: str, instrument: InstrumentId, side: Side, qty: str, price: str
) -> list[DomainEvent]:
    return [
        OrderSubmitted(
            occurred_at=at, client_order_id=oid, instrument=instrument, side=side, quantity=D(qty)
        ),
        OrderFilled(
            occurred_at=at + timedelta(seconds=2),
            client_order_id=oid,
            fill_price=D(price),
            fill_quantity=D(qty),
            fee=D("0.1"),
            slippage=D("0.05"),
        ),
    ]


@pytest.fixture
def paths(tmp_path: Path) -> PaperPaths:
    paths = PaperPaths(tmp_path)
    journal = JsonlEventJournal(paths.journal)
    events = [
        RunnerStarted(
            occurred_at=T0, broker="simulado", strategy_id="carry-h2", symbols="SOLUSDT", params=""
        ),
        *order(T0, "c-entrada-1", SPOT, Side.BUY, "2", "100"),
        *order(T0, "c-entrada-2", PERP, Side.SELL, "1.5", "100"),
        FundingSettled(
            occurred_at=T0 + timedelta(hours=8),
            symbol="SOLUSDT",
            funding_time=T0 + timedelta(hours=8),
            rate=D("0.0003"),
            interval_hours=8,
            amount=D("0.75"),
            action="mantener",
            s_k="",
            target_open=True,
            was_open=True,
            rebalance=False,
        ),
        RiskLimitBreached(occurred_at=T0, rule="max_gross_leverage", detail="x"),
        RiskLimitBreached(occurred_at=T0, rule="max_gross_leverage", detail="y"),
        PortfolioValued(
            occurred_at=T0,
            equity=D(1000),
            cash=D(0),
            gross_notional=D(0),
        ),
        PortfolioValued(
            occurred_at=T0 + timedelta(hours=9),
            equity=D(990),
            cash=D(0),
            gross_notional=D(350),
            marks=PortfolioValued.encode_marks({SPOT: D(100), PERP: D(100)}),
        ),
    ]
    for event in events:
        journal.append(event)
    paths.heartbeat.write_text(
        json.dumps({"at": (T0 + timedelta(hours=9)).isoformat(), "ok": True, "kill_switch": False}),
        encoding="utf-8",
    )
    return paths


def registry_for(paths: PaperPaths) -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register(PaperCollector(paths))
    return registry


def test_equity_pnl_drawdown_funding_and_costs(paths: PaperPaths) -> None:
    r = registry_for(paths)

    assert r.get_sample_value("pq_paper_equity_usd") == 990
    assert r.get_sample_value("pq_paper_pnl_usd") == -10
    assert r.get_sample_value("pq_paper_drawdown_ratio") == pytest.approx(0.01)
    assert r.get_sample_value("pq_paper_funding_usd") == 0.75  # gauge: el funding también se paga
    assert r.get_sample_value("pq_paper_costs_usd_total") == pytest.approx(0.3)


def test_exposure_by_leg_and_hedge_imbalance(paths: PaperPaths) -> None:
    r = registry_for(paths)

    spot = {"instrument": str(SPOT), "symbol": "SOLUSDT", "leg": "spot"}
    perp = {"instrument": str(PERP), "symbol": "SOLUSDT", "leg": "perp"}
    assert r.get_sample_value("pq_paper_exposure_usd", spot) == 200
    assert r.get_sample_value("pq_paper_exposure_usd", perp) == 150
    # |200 - 150| / 200: la pata perp cubre solo el 75 %
    assert r.get_sample_value("pq_paper_hedge_imbalance_ratio", {"symbol": "SOLUSDT"}) == 0.25


def test_order_latency_fills_and_rejections(paths: PaperPaths) -> None:
    r = registry_for(paths)

    assert r.get_sample_value("pq_paper_orders_filled_total") == 2
    assert r.get_sample_value("pq_paper_order_latency_seconds_count") == 2
    assert r.get_sample_value("pq_paper_order_latency_seconds_sum") == 4
    assert r.get_sample_value("pq_paper_order_latency_seconds_bucket", {"le": "5.0"}) == 2
    assert r.get_sample_value("pq_paper_order_latency_seconds_bucket", {"le": "1.0"}) == 0
    assert r.get_sample_value("pq_paper_risk_rejections_total", {"rule": "max_gross_leverage"}) == 2


def test_heartbeat_and_kill_switch(paths: PaperPaths) -> None:
    r = registry_for(paths)
    assert r.get_sample_value("pq_paper_heartbeat_timestamp_seconds") == (
        (T0 + timedelta(hours=9)).timestamp()
    )
    assert r.get_sample_value("pq_paper_heartbeat_ok") == 1
    assert r.get_sample_value("pq_paper_kill_switch_active") == 0

    paths.kill_switch.write_text("prueba", encoding="utf-8")
    assert r.get_sample_value("pq_paper_kill_switch_active") == 1


def test_without_a_journal_only_the_runner_state_is_reported(tmp_path: Path) -> None:
    r = registry_for(PaperPaths(tmp_path))

    assert r.get_sample_value("pq_paper_equity_usd") is None  # no se inventa un capital
    assert r.get_sample_value("pq_paper_heartbeat_ok") == 0
    assert r.get_sample_value("pq_paper_kill_switch_active") == 0
    assert r.get_sample_value("pq_paper_orders_filled_total") == 0


def test_the_view_is_rebuilt_only_when_the_journal_changes(
    paths: PaperPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = PaperCollector(paths)
    builds = []
    original = collector._rebuild

    def counting() -> None:
        builds.append(1)
        original()

    monkeypatch.setattr(collector, "_rebuild", counting)
    list(collector.collect())
    list(collector.collect())
    assert len(builds) == 1

    JsonlEventJournal(paths.journal).append(
        PortfolioValued(occurred_at=T0 + timedelta(hours=10), equity=D(995), cash=D(0),
                        gross_notional=D(0))
    )  # fmt: skip
    list(collector.collect())
    assert len(builds) == 2


def test_the_metrics_server_listens_only_on_loopback(paths: PaperPaths) -> None:
    server = serve_metrics(paths, port=0)
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
            body = resp.read().decode()
        assert "pq_paper_equity_usd 990.0" in body
    finally:
        server.shutdown()


class FakeRunner:
    def run(self, *, interval_seconds: float, max_ticks: int | None) -> bool:
        return True


def test_paper_run_serves_metrics_while_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from prometheus_platform.api import cli  # noqa: PLC0415

    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "build", lambda **kwargs: FakeRunner())
    servers: list[object] = []
    real = serve_metrics

    def recording(paths: PaperPaths, port: int) -> object:
        server = real(paths, 0)  # puerto libre: la prueba no choca con un runner real
        servers.append(server)
        return server

    monkeypatch.setattr("prometheus_platform.api.paper.metrics.serve_metrics", recording)

    assert cli.main(["paper", "run", "--once", "--metrics-port", "9108"]) == 0
    assert len(servers) == 1
    assert "métricas en http://127.0.0.1:" in capsys.readouterr().out

    assert cli.main(["paper", "run", "--once"]) == 0
    assert len(servers) == 1  # sin --metrics-port no se abre nada
