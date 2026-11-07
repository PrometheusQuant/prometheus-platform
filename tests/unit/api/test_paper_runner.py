"""Runner de paper trading (PQ-54): ciclo, reinicio, riesgo, kill-switch y paridad."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypeVar

import pytest
from tests.unit.research.conftest import make_market

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.compose import PaperPaths, build
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.events import (
    DomainEvent,
    FundingSettled,
    OrderFilled,
    OrderSubmitted,
    PortfolioValued,
    RiskLimitBreached,
    RunnerStarted,
    SignalGenerated,
)
from prometheus_platform.domain.model import FundingRate
from prometheus_platform.ops.settings import Settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskLimits, RiskManager
from prometheus_platform.research.backtest import CarryConfig, CostModel, simulate_symbol
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 1, tzinfo=UTC)
E = TypeVar("E", bound=DomainEvent)
SYMBOL = "SOLUSDT"
SPOT, PERP = spot_instrument(SYMBOL), perp_instrument(SYMBOL)
HIGH = Decimal("0.0003")  # 0,0003 · 1095 = 32,9 % anualizado > θ = 20 %
PARAMS = CarryParams(k=3, theta=0.20)
COSTS = CostModel(slippage=0.0005)
LIMITS = RiskLimits(
    max_notional_symbol=Decimal(10_000),
    max_notional_total=Decimal(10_000),
    max_leverage=Decimal(1),
    hard_leverage=Decimal("1.5"),
    max_daily_loss=Decimal("0.5"),
    max_hedge_imbalance=Decimal("0.15"),
    imbalance_grace_seconds=300,
)


class FakeMarket:
    """Mercado en vivo controlable: solo publica liquidaciones ya ocurridas."""

    def __init__(self, clock: FixedClock, price: Decimal = Decimal(100)) -> None:
        self._clock = clock
        self.price = {SYMBOL: (price, price)}
        self.funding: dict[str, list[FundingRate]] = {SYMBOL: []}
        self.down = False

    def add(self, at: datetime, rate: Decimal, symbol: str = SYMBOL) -> None:
        self.funding.setdefault(symbol, []).append(
            FundingRate(instrument=perp_instrument(symbol), funding_time=at, rate=rate)
        )

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        if self.down:
            raise ConnectionError("api caída")
        return self.price[symbol]

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        rows = [r for r in self.funding[symbol] if r.funding_time <= self._clock.now()]
        return rows[-limit:]


class Rig:
    """Runner con piezas reales (bróker simulado, diario JSONL, kill-switch) sobre ``tmp_path``."""

    def __init__(
        self, root: Path, clock: FixedClock, market: FakeMarket, limits: RiskLimits = LIMITS
    ) -> None:
        self.root, self.clock, self.market, self.limits = root, clock, market, limits
        self.journal = JsonlEventJournal(root / "diario.jsonl")
        self.runner = self.new_runner()

    def new_runner(self) -> PaperRunner:
        """Un proceso nuevo sobre los mismos archivos: así se simula un reinicio."""
        self.broker = SimulatedBroker(
            self.market, lambda _: COSTS, self.clock, self.root / "broker.json", Decimal(1000)
        )
        self.kill = KillSwitch(self.root / "KILL_SWITCH", self.clock, self.journal, self.broker)
        return PaperRunner(
            config=RunnerConfig(symbols=(SYMBOL,), params=PARAMS, history_limit=30),
            market=self.market,
            broker=self.broker,
            journal=self.journal,
            kill_switch=self.kill,
            risk=RiskManager(self.limits),
            clock=self.clock,
            heartbeat_path=self.root / "heartbeat.json",
        )

    def events(self, kind: type[E]) -> list[E]:
        return [e for e in self.journal.replay() if isinstance(e, kind)]

    def at(self, instant: datetime) -> None:
        self.clock.advance_to(instant)


def settlements(n: int, rate: Decimal = HIGH, start: datetime = T0) -> list[datetime]:
    return [start + timedelta(hours=8 * i) for i in range(n)]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(T0 + timedelta(hours=16, minutes=1))
    return Rig(tmp_path, clock, market)


def test_cold_start_enters_both_legs_at_one_times_leverage(rig: Rig) -> None:
    rig.runner.start()
    report = rig.runner.tick()

    assert report.ok
    assert report.orders == 2
    assert report.settlements == 1
    positions = rig.broker.positions()
    assert positions[SPOT] > 0 > positions[PERP]
    assert positions[SPOT] == -positions[PERP]  # spot = perp en el FakeMarket: cobertura exacta
    assert report.equity is not None
    gross = (positions[SPOT] - positions[PERP]) * Decimal(100)
    assert Decimal("0.97") < gross / report.equity < Decimal(1)  # 1x menos el margen del 2 %
    assert len(rig.events(RunnerStarted)) == 1
    assert [e.client_order_id for e in rig.events(OrderSubmitted)] == [
        "20261101T1600-entrada-SOLUSDT",
        "20261101T1600-entrada-SOLUSDT-PERP",
    ]
    assert len(rig.events(OrderFilled)) == 2
    assert len(rig.events(SignalGenerated)) == 2
    (settled,) = rig.events(FundingSettled)
    assert settled.action == "entrada"
    assert settled.amount == 0
    assert len(rig.events(PortfolioValued)) == 1


def test_cold_start_rebuilds_the_hysteresis_from_history(tmp_path: Path) -> None:
    """Entró con S_k ≥ θ y la señal bajó a [θ/2, θ): el backtest sigue dentro; el runner también."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t, rate in zip(settlements(6), ["0.0003"] * 3 + ["0.00015"] * 3, strict=True):
        market.add(t, Decimal(rate))  # 0,00015 · 1095 = 16,4 %: entre θ/2 y θ
    clock.advance_to(T0 + timedelta(hours=40, minutes=1))
    rig = Rig(tmp_path, clock, market)

    rig.runner.tick()

    assert rig.broker.positions()[PERP] < 0
    (settled,) = rig.events(FundingSettled)
    assert settled.action == "mantener"


def test_does_not_enter_below_threshold(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(6):
        market.add(t, Decimal("0.00015"))
    clock.advance_to(T0 + timedelta(hours=40, minutes=1))
    rig = Rig(tmp_path, clock, market)

    report = rig.runner.tick()

    assert report.orders == 0
    assert rig.broker.positions() == {}


def test_collects_funding_on_the_next_settlement(rig: Rig) -> None:
    rig.runner.tick()
    short = -rig.broker.positions()[PERP]
    cash_before = rig.broker.cash()

    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    report = rig.runner.tick()

    expected = short * Decimal(100) * HIGH
    assert report.settlements == 1
    assert report.orders == 0
    assert rig.events(FundingSettled)[-1].amount == expected
    assert rig.broker.cash() == cash_before + expected


def test_restart_does_not_settle_or_trade_twice(rig: Rig) -> None:
    rig.runner.tick()
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()
    cash, positions = rig.broker.cash(), rig.broker.positions()
    before = list(rig.journal.replay())

    restarted = rig.new_runner()
    rig.at(T0 + timedelta(hours=24, minutes=2))
    report = restarted.tick()

    assert report.settlements == 0
    assert report.orders == 0
    assert rig.broker.cash() == cash
    assert rig.broker.positions() == positions
    assert len(rig.events(FundingSettled)) == 2
    new = list(rig.journal.replay())[len(before) :]
    assert [type(e) for e in new] == [PortfolioValued]  # un proceso nuevo valora al arrancar


def test_catches_up_on_missed_settlements_and_exits(rig: Rig) -> None:
    rig.runner.tick()
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.market.add(T0 + timedelta(hours=32), Decimal("-0.0001"))  # tasa negativa: salida
    rig.at(T0 + timedelta(hours=32, minutes=1))

    report = rig.runner.tick()

    assert report.settlements == 2
    assert [e.action for e in rig.events(FundingSettled)] == ["entrada", "mantener", "salida"]
    assert rig.broker.positions() == {}
    assert rig.events(OrderSubmitted)[-1].client_order_id == "20261102T0800-salida-SOLUSDT-PERP"


def test_kill_switch_flattens_and_blocks_new_entries(rig: Rig) -> None:
    rig.runner.tick()
    rig.kill.trip("prueba", source="cli")

    rig.at(T0 + timedelta(hours=16, minutes=2))
    report = rig.runner.tick()

    assert report.kill_switch
    assert rig.broker.positions() == {}
    rig.market.add(T0 + timedelta(hours=24), HIGH)  # señal alta, pero el kill-switch manda
    rig.at(T0 + timedelta(hours=24, minutes=1))
    report = rig.runner.tick()
    assert report.settlements == 1
    assert report.orders == 0
    assert rig.broker.positions() == {}
    heartbeat = json.loads((rig.root / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["kill_switch"] is True


def test_risk_rejection_sends_no_leg_at_all(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(T0 + timedelta(hours=16, minutes=1))
    tight = replace(LIMITS, max_notional_symbol=Decimal(600))
    rig = Rig(tmp_path, clock, market, tight)

    report = rig.runner.tick()

    assert report.orders == 0
    assert rig.broker.positions() == {}
    (rejected,) = rig.events(RiskLimitBreached)
    assert rejected.rule == "nocional_simbolo"


def test_market_outage_skips_the_cycle_and_flags_the_heartbeat(rig: Rig) -> None:
    rig.market.down = True

    report = rig.runner.tick()

    assert not report.ok
    assert list(rig.journal.replay()) == []
    heartbeat = json.loads((rig.root / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["ok"] is False
    assert "SOLUSDT" in heartbeat["detail"]


def test_soft_leverage_warning_is_recorded_once_not_every_cycle(rig: Rig) -> None:
    rig.runner.tick()
    rig.market.price[SYMBOL] = (Decimal(110), Decimal(110))  # el nocional bruto sube un 10 %

    for minute in (2, 3, 4):
        rig.at(T0 + timedelta(hours=16, minutes=minute))
        rig.runner.tick()

    assert [e.rule for e in rig.events(RiskLimitBreached)] == ["apalancamiento"]
    assert not rig.kill.active


def test_run_loop_survives_a_failing_tick(rig: Rig) -> None:
    calls: list[float] = []
    rig.market.down = True

    ticks = rig.runner.run(interval_seconds=5, max_ticks=3, sleep=calls.append)

    assert ticks == 3
    assert calls == [5, 5]


def test_compose_refuses_the_live_environment(tmp_path: Path) -> None:
    settings = Settings(
        environment="live", binance_api_key="k", binance_api_secret="s", binance_testnet=False
    )
    with pytest.raises(ValueError, match="live"):
        build(
            settings=settings,
            config=RunnerConfig(symbols=(SYMBOL,), params=PARAMS),
            client=None,  # type: ignore[arg-type]
            clock=FixedClock(T0),
            paths=PaperPaths(tmp_path),
            capital=Decimal(1000),
        )


def test_backtest_and_runner_take_the_same_decisions(tmp_path: Path) -> None:
    """Historia 3 de la spec: mismas entradas y salidas en las mismas liquidaciones."""
    hours = 24 * 60

    def rate(h: int) -> float:  # cruza θ, θ/2 y cero varias veces
        return 0.00005 + 0.0003 * math.sin(h / 90)

    hourly, table = make_market(hours, rate=rate, start=T0)
    expected = simulate_symbol(
        SYMBOL, hourly, table, config=CarryConfig(9, 0.20), costs=COSTS, capital=1.0
    ).trades
    assert {label for _, label in expected} >= {"entrada", "salida"}

    clock = FixedClock(T0)
    market = FakeMarket(clock)
    rig = Rig(tmp_path, clock, market)
    rig.runner = PaperRunner(
        config=RunnerConfig(symbols=(SYMBOL,), params=CarryParams(9, 0.20), history_limit=30),
        market=market,
        broker=rig.broker,
        journal=rig.journal,
        kill_switch=rig.kill,
        risk=RiskManager(LIMITS),
        clock=clock,
        heartbeat_path=tmp_path / "heartbeat.json",
    )
    for at, value in table.select("funding_time", "funding_rate").iter_rows():
        market.add(at, Decimal(repr(value)))
        clock.advance_to(at + timedelta(minutes=1))
        rig.runner.tick()

    decided = [
        (e.funding_time, e.action) for e in rig.events(FundingSettled) if e.action != "mantener"
    ]
    assert decided == [(at, label) for at, label in expected if label != "rebalanceo"]
