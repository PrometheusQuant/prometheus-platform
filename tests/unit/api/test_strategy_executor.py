"""Ejecutor genérico de señales en el runner (PQ-116): cualquier ``Strategy`` opera en paper."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypeVar

import pytest
from tests.contract.example_strategies import BTC, SmaTrend, hourly_bars

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.events import (
    DomainEvent,
    OrderSubmitted,
    RiskLimitBreached,
    RunnerStarted,
    SignalGenerated,
)
from prometheus_platform.domain.market import MarketSnapshot
from prometheus_platform.domain.model import Bar, FundingRate, InstrumentId, Side, Signal, Venue
from prometheus_platform.execution.allocation import StrategyAllocation
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskLimits, RiskManager
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 1, tzinfo=UTC)
E = TypeVar("E", bound=DomainEvent)
CARRY = "SOLUSDT"
COSTS = CostModel(slippage=0.0)
LIMITS = RiskLimits(
    max_notional_symbol=Decimal(10_000),
    max_notional_total=Decimal(10_000),
    max_leverage=Decimal(1),
    hard_leverage=Decimal("1.5"),
    max_daily_loss=Decimal("0.5"),
    max_hedge_imbalance=Decimal("0.15"),
    imbalance_grace_seconds=300,
)
SHARE = Decimal("0.5")
BTC_PRICE = Decimal(200)
# Capital asignado: 1000 · 0,5 · (1 - 0,02 de margen) = 490 → 2,45 BTC a 200.
BUDGET = Decimal(1000) * SHARE * Decimal("0.98")


def at(hours: int, minutes: int = 5) -> datetime:
    return T0 + timedelta(hours=hours, minutes=minutes)


class FeedMarket:
    """Mercado en vivo y feed de velas controlables: solo publica lo que ya se conoce."""

    def __init__(self, clock: FixedClock) -> None:
        self._clock = clock
        self.price = {CARRY: (Decimal(100), Decimal(100)), "BTCUSDT": (BTC_PRICE, BTC_PRICE)}
        self.funding = {
            CARRY: [
                FundingRate(instrument=perp_instrument(CARRY), funding_time=t, rate=Decimal(0))
                for t in (T0 - timedelta(hours=16), T0 - timedelta(hours=8), T0)
            ]
        }
        closes = [Decimal(100 + i) for i in range(72)]  # sube siempre: SmaTrend va larga
        self.series: dict[InstrumentId, list[Bar]] = {
            BTC: hourly_bars(BTC, T0 - timedelta(hours=24), closes)
        }
        self.bars_down = False

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        return self.price[symbol]

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        return [r for r in self.funding[symbol] if r.funding_time <= self._clock.now()][-limit:]

    def bars_for(self, instrument: InstrumentId, start: datetime, end: datetime) -> list[Bar]:
        if self.bars_down:
            raise ConnectionError("klines caído")
        now = self._clock.now()
        return [
            b
            for b in self.series.get(instrument, [])
            if start <= b.open_time < end and b.close_time <= now
        ]

    # MarketDataFeed
    def bars(self, instrument: InstrumentId, start: datetime, end: datetime) -> list[Bar]:
        return self.bars_for(instrument, start, end)

    def funding_rates(
        self, instrument: InstrumentId, start: datetime, end: datetime
    ) -> list[FundingRate]:
        return []


class Rig:
    def __init__(
        self,
        root: Path,
        *,
        strategies: tuple[StrategyAllocation, ...] | None = None,
        limits: RiskLimits = LIMITS,
        start: datetime | None = None,
    ) -> None:
        self.root, self.limits = root, limits
        self.clock = FixedClock(start or at(0))
        self.market = FeedMarket(self.clock)
        self.strategies = (
            (StrategyAllocation(SmaTrend(), SHARE),) if strategies is None else strategies
        )
        self.journal = JsonlEventJournal(root / "diario.jsonl")
        self.runner = self.new_runner()

    def new_runner(self) -> PaperRunner:
        self.broker = SimulatedBroker(
            self.market, lambda _: COSTS, self.clock, self.root / "broker.json", Decimal(1000)
        )
        self.kill = KillSwitch(self.root / "KILL_SWITCH", self.clock, self.journal, self.broker)
        return PaperRunner(
            config=RunnerConfig(symbols=(CARRY,), params=CarryParams(k=3, theta=0.20)),
            market=self.market,
            broker=self.broker,
            journal=self.journal,
            kill_switch=self.kill,
            risk=RiskManager(self.limits),
            clock=self.clock,
            heartbeat_path=self.root / "heartbeat.json",
            strategies=self.strategies,
            feed=self.market,
        )

    def events(self, kind: type[E]) -> list[E]:
        return [e for e in self.journal.replay() if isinstance(e, kind)]

    def signals(self) -> list[Signal]:
        return [
            e.signal for e in self.events(SignalGenerated) if e.signal.strategy_id != "carry-h2"
        ]

    def heartbeat(self) -> dict[str, object]:
        data: dict[str, object] = json.loads((self.root / "heartbeat.json").read_text("utf-8"))
        return data

    def tick_at(self, instant: datetime) -> int:
        self.clock.advance_to(instant)
        return self.runner.tick().orders


def test_signal_waits_for_the_latency_and_then_trades_its_share(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    assert rig.tick_at(at(0)) == 0  # decide con la vela que cierra a las 00:00; rige a la 01:00
    (signal,) = rig.signals()
    assert (signal.generated_at, signal.target_weight) == (T0, Decimal(1))

    assert rig.tick_at(at(0, 59)) == 0
    assert rig.tick_at(at(1)) == 1
    assert rig.broker.positions() == {BTC: BUDGET / BTC_PRICE}
    (order,) = rig.events(OrderSubmitted)
    assert order.side is Side.BUY
    assert order.client_order_id.startswith("sma-ejemplo-20261101T0000-")
    assert rig.runner.tick().ok


def test_decides_once_per_hourly_bar(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    for minutes in (5, 20, 40):
        rig.tick_at(at(0, minutes))
    rig.tick_at(at(1))
    assert [s.generated_at for s in rig.signals()] == [T0, T0 + timedelta(hours=1)]


def test_inside_the_band_it_does_not_trade_again(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    # +5 % de precio: la posición vale un 5 % más que el objetivo, dentro de la banda del 10 %.
    rig.market.price["BTCUSDT"] = (BTC_PRICE * Decimal("1.05"),) * 2
    assert rig.tick_at(at(2)) == 0
    # +30 %: fuera de la banda, vende hasta el objetivo.
    rig.market.price["BTCUSDT"] = (BTC_PRICE * Decimal("1.3"),) * 2
    assert rig.tick_at(at(3)) == 1
    assert rig.events(OrderSubmitted)[-1].side is Side.SELL


def test_exit_signal_closes_the_position(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    falling = [Decimal(200 - i) for i in range(8)]
    rig.market.series[BTC] = [b for b in rig.market.series[BTC] if b.close_time <= at(1, 0)] + (
        hourly_bars(BTC, at(1, 0), falling)
    )
    rig.tick_at(at(5))  # la media de 4 h ya está por encima del cierre: peso 0
    assert rig.signals()[-1].target_weight == 0
    rig.tick_at(at(6))
    assert rig.broker.positions() == {}


def test_restart_keeps_the_target_and_does_not_decide_the_same_bar_twice(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(0))
    rig.runner = rig.new_runner()  # reinicio dentro de la latencia
    rig.tick_at(at(0, 30))
    assert len(rig.signals()) == 1

    rig.runner = rig.new_runner()
    rig.market.bars_down = True  # sin velas no decide, pero el objetivo sigue en el diario
    assert rig.tick_at(at(1)) == 1
    assert rig.broker.positions() == {BTC: BUDGET / BTC_PRICE}
    assert "sma-ejemplo (decidir): ConnectionError" in str(rig.heartbeat()["detail"])


def test_missing_bar_is_not_decided_and_shows_in_the_heartbeat_after_the_grace(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)
    rig.market.series[BTC] = [b for b in rig.market.series[BTC] if b.close_time < T0]
    rig.tick_at(at(0))
    assert rig.signals() == []
    assert rig.heartbeat()["ok"] is True  # aún dentro del margen: la API puede ir con retraso
    rig.tick_at(at(0, 15))
    assert rig.signals() == []
    assert "sin la vela de 00:00" in str(rig.heartbeat()["detail"])


def test_single_leg_position_is_not_an_unhedged_carry_leg(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    rig.tick_at(at(2))  # más de la gracia de 300 s con una sola pata
    assert not [b for b in rig.events(RiskLimitBreached) if b.rule == "pata_sin_cubrir"]
    assert not rig.kill.active


def test_kill_switch_flattens_and_blocks_new_trades(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    rig.kill.trip("prueba", source="cli")
    rig.tick_at(at(1, 10))
    assert rig.broker.positions() == {}
    assert rig.tick_at(at(2)) == 0  # sigue decidiendo, pero no opera
    assert rig.broker.positions() == {}
    # Ni siquiera lo intenta: no llena el diario con rechazos del kill-switch en cada ciclo.
    assert not [b for b in rig.events(RiskLimitBreached) if b.rule == "kill_switch"]
    assert rig.signals()[-1].generated_at == T0 + timedelta(hours=2)


def test_orders_go_through_pre_trade(tmp_path: Path) -> None:
    tight = replace(LIMITS, max_leverage=Decimal("0.1"))
    rig = Rig(tmp_path, limits=tight)
    rig.tick_at(at(0))
    assert rig.tick_at(at(1)) == 0
    assert rig.tick_at(at(1, 10)) == 0
    assert rig.broker.positions() == {}
    assert [b.rule for b in rig.events(RiskLimitBreached)] == ["apalancamiento"]  # una sola vez


def test_the_carry_uses_the_rest_of_the_capital(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    high = Decimal("0.0003")
    rig.market.funding[CARRY] = [
        FundingRate(instrument=perp_instrument(CARRY), funding_time=t, rate=high)
        for t in (T0 - timedelta(hours=16), T0 - timedelta(hours=8), T0)
    ]
    rig.tick_at(at(1))
    held = rig.broker.positions()
    # Carry: 1000 · (1 - 0,5) / 1 símbolo / 2 patas · 0,98 = 245 por pata, a 100.
    assert held[spot_instrument(CARRY)] == Decimal("2.45")
    assert held[perp_instrument(CARRY)] == Decimal("-2.45")


def test_start_records_the_strategies(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.runner.start()
    (started,) = rig.events(RunnerStarted)
    assert started.symbols == "SOLUSDT,BTCUSDT"
    assert "sma-ejemplo[share=0.5" in started.params


class WrongInstrument(SmaTrend):
    def on_snapshot(self, snapshot: MarketSnapshot) -> list[Signal]:
        eth = InstrumentId("ETHUSDT", Venue.BINANCE)
        return [Signal(self.strategy_id, eth, snapshot.as_of, Decimal(1))]


def test_an_invalid_signal_is_neither_recorded_nor_traded(tmp_path: Path) -> None:
    rig = Rig(tmp_path, strategies=(StrategyAllocation(WrongInstrument(), SHARE),))
    rig.tick_at(at(0))
    rig.tick_at(at(1))
    assert rig.signals() == []
    assert rig.events(OrderSubmitted) == []
    assert "InvalidSignalError" in str(rig.heartbeat()["detail"])


@pytest.mark.parametrize(
    ("strategies", "message"),
    [
        ((StrategyAllocation(SmaTrend(spot_instrument(CARRY)), SHARE),), "del carry"),
        ((StrategyAllocation(SmaTrend(), Decimal(1)),), "no queda capital"),
        (
            (
                StrategyAllocation(SmaTrend(), Decimal("0.2")),
                StrategyAllocation(SmaTrend(strategy_id="otra"), Decimal("0.2")),
            ),
            "una sola estrategia",
        ),
        (
            (
                StrategyAllocation(SmaTrend(), Decimal("0.2")),
                StrategyAllocation(SmaTrend(InstrumentId("ETHUSDT", Venue.BINANCE)), SHARE),
            ),
            "repetido",
        ),
    ],
)
def test_refuses_conflicting_allocations(
    tmp_path: Path, strategies: tuple[StrategyAllocation, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Rig(tmp_path, strategies=strategies)


def test_strategies_need_a_feed(tmp_path: Path) -> None:
    rig = Rig(tmp_path, strategies=())
    with pytest.raises(ValueError, match="MarketDataFeed"):
        PaperRunner(
            config=RunnerConfig(symbols=(CARRY,), params=CarryParams(k=3, theta=0.20)),
            market=rig.market,
            broker=rig.broker,
            journal=rig.journal,
            kill_switch=rig.kill,
            risk=RiskManager(LIMITS),
            clock=rig.clock,
            heartbeat_path=tmp_path / "heartbeat.json",
            strategies=(StrategyAllocation(SmaTrend(), SHARE),),
        )
