"""Prueba de caos de PQ-80: 5 minutos sin stream y el runner no pierde estado."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from prometheus_platform.adapters.binance_ws_market import (
    StreamCache,
    StreamingMarket,
    apply_message,
)
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.events import FundingSettled
from prometheus_platform.domain.model import FundingRate
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskManager
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

from .test_strategy_executor import CARRY, COSTS, LIMITS, T0, FeedMarket, at

SPOT, PERP = spot_instrument(CARRY), perp_instrument(CARRY)


def feed_stream(cache: StreamCache, clock: FixedClock) -> None:
    now = clock.now()
    apply_message(
        cache, json.dumps({"data": {"e": "markPriceUpdate", "s": CARRY, "p": "100", "r": "0"}}), now
    )
    apply_message(cache, json.dumps({"data": {"e": "24hrMiniTicker", "s": CARRY, "c": "100"}}), now)


def test_a_five_minute_outage_falls_back_to_rest_without_losing_state(tmp_path: Path) -> None:
    clock = FixedClock(at(1))
    rest = FeedMarket(clock)
    rest.funding[CARRY] = [
        FundingRate(instrument=PERP, funding_time=t, rate=Decimal("0.0003"))
        for t in (T0 - timedelta(hours=16), T0 - timedelta(hours=8), T0)
    ]
    cache = StreamCache()
    market = StreamingMarket(rest, cache, clock)  # type: ignore[arg-type]
    journal = JsonlEventJournal(tmp_path / "diario.jsonl")
    broker = SimulatedBroker(
        market, lambda _: COSTS, clock, tmp_path / "broker.json", Decimal(1000)
    )
    runner = PaperRunner(
        config=RunnerConfig(symbols=(CARRY,), params=CarryParams(k=3, theta=0.20)),
        market=market,
        broker=broker,
        journal=journal,
        kill_switch=KillSwitch(tmp_path / "KILL_SWITCH", clock, journal, broker),
        risk=RiskManager(LIMITS),
        clock=clock,
        heartbeat_path=tmp_path / "heartbeat.json",
    )
    feed_stream(cache, clock)
    assert runner.tick().ok
    held = broker.positions()
    assert held[SPOT] > 0  # el carry entró con precios del stream
    assert market.degraded() == frozenset()

    for minute in range(1, 6):  # 5 minutos sin mensajes del stream
        clock.advance_to(at(1, 5 + minute))
        report = runner.tick()
        assert report.ok, report.detail
    assert market.degraded() == {CARRY}  # cayó a REST y lo registró
    assert broker.positions() == held  # sin pérdida ni duplicación de estado

    clock.advance_to(at(1, 12))
    feed_stream(cache, clock)  # vuelve el stream
    assert runner.tick().ok
    assert market.degraded() == frozenset()
    settled = [e.funding_time for e in journal.replay() if isinstance(e, FundingSettled)]
    assert len(settled) == len(set(settled))  # ninguna liquidación procesada dos veces
    hb = json.loads((tmp_path / "heartbeat.json").read_text("utf-8"))
    assert hb["ok"] is True
