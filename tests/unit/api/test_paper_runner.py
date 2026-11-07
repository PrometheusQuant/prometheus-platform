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
from prometheus_platform.api.cli import main
from prometheus_platform.api.paper.compose import (
    PaperPaths,
    RunnerAlreadyRunningError,
    build,
    single_instance,
)
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
from prometheus_platform.domain.model import FundingRate, Side
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
        self.funding_down = False

    def add(self, at: datetime, rate: Decimal, symbol: str = SYMBOL) -> None:
        self.funding.setdefault(symbol, []).append(
            FundingRate(instrument=perp_instrument(symbol), funding_time=at, rate=rate)
        )

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        if self.down:
            raise ConnectionError("api caída")
        return self.price[symbol]

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        if self.funding_down:
            raise ConnectionError("fundingRate caído")
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


def settlements(n: int, start: datetime = T0) -> list[datetime]:
    return [start + timedelta(hours=8 * i) for i in range(n)]


AFTER_LATENCY = T0 + timedelta(hours=17, minutes=1)  # la última liquidación (16:00) + 1 h


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    return Rig(tmp_path, clock, market)


def entered(rig: Rig) -> None:
    report = rig.runner.tick()
    assert report.orders == 2


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
    assert "execution_delay=1:00:00" in rig.events(RunnerStarted)[0].params
    assert [e.client_order_id for e in rig.events(OrderSubmitted)] == [
        "20261101T1600-entrada-20261101T170100-SOLUSDT",
        "20261101T1600-entrada-20261101T170100-SOLUSDT-PERP",
    ]
    assert len(rig.events(OrderFilled)) == 2
    assert len(rig.events(SignalGenerated)) == 2
    (settled,) = rig.events(FundingSettled)
    assert settled.action == "entrada"
    assert settled.target_open
    assert settled.amount == 0
    assert len(rig.events(PortfolioValued)) == 1


def test_orders_wait_one_hour_after_the_decision(tmp_path: Path) -> None:
    """Enmienda 1.1: la decisión de las 16:00 se ejecuta en la vela que abre a las 17:00."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(T0 + timedelta(hours=16, minutes=1))
    rig = Rig(tmp_path, clock, market)

    first = rig.runner.tick()
    rig.at(T0 + timedelta(hours=16, minutes=59))
    second = rig.runner.tick()
    rig.at(T0 + timedelta(hours=17))
    third = rig.runner.tick()

    assert (first.settlements, first.orders) == (1, 0)
    assert second.orders == 0
    assert third.orders == 2


def test_cold_start_rebuilds_the_hysteresis_from_history(tmp_path: Path) -> None:
    """Entró con S_k ≥ θ y la señal bajó a [θ/2, θ): el backtest sigue dentro; el runner también."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t, rate in zip(settlements(6), ["0.0003"] * 3 + ["0.00015"] * 3, strict=True):
        market.add(t, Decimal(rate))  # 0,00015 · 1095 = 16,4 %: entre θ/2 y θ
    clock.advance_to(T0 + timedelta(hours=41, minutes=1))
    rig = Rig(tmp_path, clock, market)

    rig.runner.tick()

    assert rig.broker.positions()[PERP] < 0
    (settled,) = rig.events(FundingSettled)
    assert settled.action == "mantener"
    assert settled.target_open


def test_does_not_enter_below_threshold(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(6):
        market.add(t, Decimal("0.00015"))
    clock.advance_to(T0 + timedelta(hours=41, minutes=1))
    rig = Rig(tmp_path, clock, market)

    report = rig.runner.tick()

    assert report.orders == 0
    assert rig.broker.positions() == {}


def test_collects_funding_on_the_next_settlement(rig: Rig) -> None:
    entered(rig)
    short = -rig.broker.positions()[PERP]
    cash_before = rig.broker.cash()

    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    report = rig.runner.tick()

    expected = short * Decimal(100) * HIGH
    assert report.settlements == 1
    assert report.orders == 0  # se mantiene sin rebalancear
    assert rig.events(FundingSettled)[-1].amount == expected
    assert rig.broker.cash() == cash_before + expected


def test_restart_does_not_settle_or_trade_twice(rig: Rig) -> None:
    entered(rig)
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=25, minutes=1))
    rig.runner.tick()
    cash, positions = rig.broker.cash(), rig.broker.positions()
    before = list(rig.journal.replay())

    restarted = rig.new_runner()
    rig.at(T0 + timedelta(hours=25, minutes=2))
    report = restarted.tick()

    assert report.settlements == 0
    assert report.orders == 0
    assert rig.broker.cash() == cash
    assert rig.broker.positions() == positions
    assert len(rig.events(FundingSettled)) == 2
    new = list(rig.journal.replay())[len(before) :]
    assert [type(e) for e in new] == [PortfolioValued]  # un proceso nuevo valora al arrancar


def test_decision_lost_in_a_crash_is_executed_after_restart(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revisión C2: el estado deseado queda en el diario antes de las órdenes."""

    def crash(*_: object) -> int:
        raise KeyboardInterrupt  # el proceso muere entre la decisión y las órdenes

    monkeypatch.setattr(rig.runner, "_reconcile", crash)
    with pytest.raises(KeyboardInterrupt):
        rig.runner.tick()
    assert rig.broker.positions() == {}
    assert rig.events(FundingSettled)[0].target_open

    report = rig.new_runner().tick()

    assert report.settlements == 0
    assert report.orders == 2
    assert rig.broker.positions()[PERP] < 0


def test_a_missing_leg_is_completed_on_the_next_cycle(rig: Rig) -> None:
    """Revisión C1: si una pata falla al enviarse, la reconciliación la completa."""
    entered(rig)
    perp_qty = rig.broker.positions()[PERP]
    rig.broker.submit("fallo-simulado", PERP, Side.BUY, -perp_qty)  # el perp desaparece

    rig.at(AFTER_LATENCY + timedelta(minutes=1))
    report = rig.runner.tick()

    assert report.orders >= 1  # el perp y, si se desvió por las comisiones, también el spot
    assert rig.events(OrderSubmitted)[-1].client_order_id == (
        "20261101T1600-reparacion-20261101T170200-SOLUSDT-PERP"
    )
    assert rig.broker.positions()[PERP] < 0
    assert not rig.kill.active


def test_catches_up_on_missed_settlements_and_exits(rig: Rig) -> None:
    entered(rig)
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.market.add(T0 + timedelta(hours=32), Decimal("-0.0001"))  # tasa negativa: salida
    rig.at(T0 + timedelta(hours=32, minutes=1))

    report = rig.runner.tick()
    assert report.settlements == 2
    assert report.orders == 0  # la salida espera a la vela de las 09:00
    assert [e.action for e in rig.events(FundingSettled)] == ["entrada", "mantener", "salida"]

    rig.at(T0 + timedelta(hours=33, minutes=1))
    rig.runner.tick()
    assert rig.broker.positions() == {}
    assert rig.events(OrderSubmitted)[-1].client_order_id == (
        "20261102T0800-salida-20261102T090100-SOLUSDT-PERP"
    )


def test_rebalances_once_when_a_leg_drifts(rig: Rig) -> None:
    entered(rig)
    rig.market.price[SYMBOL] = (Decimal(120), Decimal(120))  # cada pata vale un 20 % más
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()
    assert rig.events(FundingSettled)[-1].rebalance

    for minute in (1, 2):
        rig.at(T0 + timedelta(hours=25, minutes=minute))
        rig.runner.tick()
    rig.new_runner().tick()  # y tampoco tras un reinicio

    labels = [e.client_order_id.split("-")[1] for e in rig.events(OrderSubmitted)]
    assert labels == ["entrada", "entrada", "rebalanceo", "rebalanceo"]


def test_kill_switch_flattens_and_blocks_new_entries(rig: Rig) -> None:
    entered(rig)
    rig.kill.trip("prueba", source="cli")

    rig.at(AFTER_LATENCY + timedelta(minutes=1))
    report = rig.runner.tick()

    assert report.kill_switch
    assert rig.broker.positions() == {}
    rig.market.add(T0 + timedelta(hours=24), HIGH)  # señal alta, pero el kill-switch manda
    rig.at(T0 + timedelta(hours=25, minutes=1))
    report = rig.runner.tick()
    assert report.settlements == 1
    assert report.orders == 0
    assert rig.broker.positions() == {}
    heartbeat = json.loads((rig.root / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["kill_switch"] is True


def test_risk_rejection_sends_no_leg_and_is_recorded_once(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    # El tamaño se acota por el nocional por símbolo; el apalancamiento máximo bajo rechaza.
    tight = replace(LIMITS, max_leverage=Decimal("0.5"), hard_leverage=Decimal("0.5"))
    rig = Rig(tmp_path, clock, market, tight)
    rig.runner._leg_target = lambda marks: Decimal(490)  # type: ignore[method-assign]

    for minute in (1, 2, 3):
        rig.at(AFTER_LATENCY + timedelta(minutes=minute))
        report = rig.runner.tick()
        assert report.orders == 0

    assert rig.broker.positions() == {}  # ni media cobertura
    (rejected,) = rig.events(RiskLimitBreached)
    assert rejected.rule == "apalancamiento"


def test_leg_size_is_capped_by_the_risk_limits(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    rig = Rig(tmp_path, clock, market, replace(LIMITS, max_notional_symbol=Decimal(600)))

    rig.runner.tick()

    spot_value = rig.broker.positions()[SPOT] * Decimal(100)
    assert spot_value == Decimal(300) * Decimal("0.98")  # 600 / 2 por pata, menos el margen


def test_market_outage_skips_the_cycle_and_flags_the_heartbeat(rig: Rig) -> None:
    rig.market.down = True

    report = rig.runner.tick()

    assert not report.ok
    assert list(rig.journal.replay()) == []
    heartbeat = json.loads((rig.root / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["ok"] is False
    assert "SOLUSDT" in heartbeat["detail"]


def test_funding_outage_also_flags_the_heartbeat(rig: Rig) -> None:
    """Revisión R3: un fallo de un símbolo no puede dejar el heartbeat en ok."""
    rig.market.funding_down = True

    report = rig.runner.tick()

    assert not report.ok
    heartbeat = json.loads((rig.root / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["ok"] is False
    assert "ConnectionError" in heartbeat["detail"]


def test_a_gap_longer_than_the_window_is_reported(rig: Rig) -> None:
    entered(rig)
    for i in range(1, 40):  # 13 días sin el runner: más que la ventana de 30 liquidaciones
        rig.market.add(T0 + timedelta(hours=16 + 8 * i), HIGH)
    rig.at(T0 + timedelta(days=14))

    report = rig.runner.tick()

    assert not report.ok
    assert "hueco" in report.detail


def test_soft_leverage_warning_is_recorded_once_not_every_cycle(rig: Rig) -> None:
    entered(rig)
    rig.market.price[SYMBOL] = (Decimal(110), Decimal(110))  # el nocional bruto sube un 10 %

    for minute in (2, 3, 4):
        rig.at(AFTER_LATENCY + timedelta(minutes=minute))
        rig.runner.tick()

    assert [e.rule for e in rig.events(RiskLimitBreached)] == ["apalancamiento"]
    assert not rig.kill.active


def test_positions_outside_the_symbols_refuse_to_start(rig: Rig) -> None:
    entered(rig)
    with pytest.raises(ValueError, match="SOLUSDT"):
        PaperRunner(
            config=RunnerConfig(symbols=("BNBUSDT",), params=PARAMS),
            market=rig.market,
            broker=rig.broker,
            journal=rig.journal,
            kill_switch=rig.kill,
            risk=RiskManager(LIMITS),
            clock=rig.clock,
            heartbeat_path=rig.root / "heartbeat.json",
        )


def test_run_loop_survives_a_failing_tick(rig: Rig) -> None:
    calls: list[float] = []
    rig.market.down = True

    healthy = rig.runner.run(interval_seconds=5, max_ticks=3, sleep=calls.append)

    assert healthy is False
    assert calls == [5, 5]
    with pytest.raises(ValueError, match="intervalo"):
        rig.runner.run(interval_seconds=0)


def test_config_rejects_repeated_symbols() -> None:
    with pytest.raises(ValueError, match="repetidos"):
        RunnerConfig(symbols=(SYMBOL, SYMBOL), params=PARAMS)


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


def test_compose_refuses_a_journal_without_broker_state(tmp_path: Path) -> None:
    paths = PaperPaths(tmp_path)
    paths.journal.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="estado del bróker"):
        build(
            settings=Settings(),
            config=RunnerConfig(symbols=(SYMBOL,), params=PARAMS),
            client=None,  # type: ignore[arg-type]
            clock=FixedClock(T0),
            paths=paths,
            capital=Decimal(1000),
        )


def test_only_one_runner_per_folder(tmp_path: Path) -> None:
    paths = PaperPaths(tmp_path)
    with single_instance(paths), pytest.raises(RunnerAlreadyRunningError), single_instance(paths):
        pass
    with single_instance(paths):  # liberado al salir
        pass


@pytest.mark.parametrize(
    "argv",
    [
        ["paper", "run", "--once", "--interval", "0"],
        ["paper", "run", "--once", "--symbols", ""],
    ],
)
def test_cli_rejects_invalid_arguments(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    assert main(argv) == 2


def test_cli_rejects_a_non_numeric_capital(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        main(["paper", "run", "--once", "--capital", "abc"])
    assert exc.value.code == 2


def test_backtest_and_runner_take_the_same_decisions(tmp_path: Path) -> None:
    """Historia 3 de la spec: mismas entradas y salidas en las mismas liquidaciones.

    Con precios que se mueven y arrancando a mitad del historial (arranque en frío). Los
    rebalanceos no se comparan: dependen del tamaño, que en paper lleva el margen del 2 %.
    """
    hours = 24 * 60

    def rate(h: int) -> float:  # cruza θ, θ/2 y cero varias veces
        return 0.00005 + 0.0003 * math.sin(h / 90)

    def price(h: int) -> float:
        return 100.0 + 15 * math.sin(h / 50)

    hourly, table = make_market(hours, rate=rate, price=price, start=T0)
    expected = simulate_symbol(
        SYMBOL, hourly, table, config=CarryConfig(9, 0.20), costs=COSTS, capital=1.0
    ).trades
    rows = list(table.select("funding_time", "funding_rate").iter_rows())
    warmup = 30  # el runner arranca con 30 liquidaciones ya publicadas
    after_warmup = [(at, label) for at, label in expected if at >= rows[warmup - 1][0]]
    assert {label for _, label in after_warmup} >= {"entrada", "salida"}

    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for at, value in rows[:warmup]:
        market.add(at, Decimal(repr(value)))
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
    for i, (at, value) in enumerate(rows[warmup - 1 :]):
        if i:
            market.add(at, Decimal(repr(value)))
        hour = int((at - T0).total_seconds() // 3600)
        market.price[SYMBOL] = (Decimal(repr(price(hour))), Decimal(repr(price(hour))))
        for offset in (timedelta(minutes=1), timedelta(hours=1, minutes=1)):
            clock.advance_to(at + offset)
            rig.runner.tick()

    decided = [
        (e.funding_time, e.action) for e in rig.events(FundingSettled) if e.action != "mantener"
    ]
    assert decided == [(at, label) for at, label in after_warmup if label != "rebalanceo"]
    executed = [
        e.client_order_id.split("-")[1]
        for e in rig.events(OrderSubmitted)
        if e.client_order_id.endswith("-PERP") and "rebalanceo" not in e.client_order_id
    ]
    labels = [label for _, label in after_warmup if label != "rebalanceo"]
    # El backtest ya estaba dentro al arrancar el runner: el arranque en frío entra primero.
    assert labels[0] == "salida"
    assert executed == ["entrada", *labels]


# --- segunda vuelta de la revisión adversarial ----------------------------------------------


def labels_of(rig: Rig) -> list[str]:
    return [e.client_order_id.split("-")[1] for e in rig.events(OrderSubmitted)]


def test_cold_start_inside_does_not_rebalance_right_after_entering(tmp_path: Path) -> None:
    """R2: sin posición no hay «desviación del 100 %»; el backtest no rebalancea ahí."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(5):
        market.add(t, HIGH)
    clock.advance_to(T0 + timedelta(hours=33, minutes=1))
    rig = Rig(tmp_path, clock, market)

    rig.runner.tick()
    rig.at(T0 + timedelta(hours=33, minutes=2))
    rig.runner.tick()

    assert not any(e.rebalance for e in rig.events(FundingSettled))
    assert labels_of(rig) == ["entrada", "entrada"]


def test_a_half_done_rebalance_is_repaired(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    """R1: si falla la segunda pata de un rebalanceo, el desbalance se repara."""
    entered(rig)
    rig.market.price[SYMBOL] = (Decimal(120), Decimal(120))
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()

    real_submit = rig.broker.submit

    def perp_fails(cid: str, instrument: object, side: Side, qty: Decimal) -> None:
        if str(cid).endswith("-PERP"):
            raise ConnectionError("fallo de red")
        real_submit(cid, instrument, side, qty)  # type: ignore[arg-type]

    monkeypatch.setattr(rig.broker, "submit", perp_fails)
    rig.at(T0 + timedelta(hours=25, minutes=1))
    rig.runner.tick()  # spot rebalanceado, perp no
    monkeypatch.setattr(rig.broker, "submit", real_submit)
    rig.at(T0 + timedelta(hours=25, minutes=2))
    rig.runner.tick()

    positions = rig.broker.positions()
    assert labels_of(rig)[-1] == "reparacion"
    assert abs(positions[SPOT] + positions[PERP]) / positions[SPOT] < Decimal("0.01")
    assert not rig.kill.active


def test_rebalance_survives_hourly_settlements(tmp_path: Path) -> None:
    """R4: con funding de 1 h, la liquidación siguiente no borra el rebalanceo pendiente."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    hourly = [T0 + timedelta(hours=h) for h in range(4)]
    for t in hourly:
        market.funding[SYMBOL].append(
            FundingRate(instrument=PERP, funding_time=t, rate=HIGH / 8, interval_hours=1)
        )
    clock.advance_to(T0 + timedelta(hours=4, minutes=1))
    rig = Rig(tmp_path, clock, market)
    rig.runner.tick()  # arranque en frío dentro: entra
    rig.market.price[SYMBOL] = (Decimal(130), Decimal(130))

    for h in range(4, 8):
        market.funding[SYMBOL].append(
            FundingRate(
                instrument=PERP,
                funding_time=T0 + timedelta(hours=h),
                rate=HIGH / 8,
                interval_hours=1,
            )
        )
        rig.at(T0 + timedelta(hours=h, minutes=1))
        rig.runner.tick()

    assert "rebalanceo" in labels_of(rig)


def test_exit_is_executed_even_if_the_funding_api_is_down(rig: Rig) -> None:
    """R5: el estado deseado ya está en el diario; sin API de funding se sigue reconciliando."""
    entered(rig)
    rig.market.add(T0 + timedelta(hours=24), Decimal("-0.0001"))
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()  # decide salir
    rig.market.funding_down = True

    rig.at(T0 + timedelta(hours=25, minutes=1))
    report = rig.runner.tick()

    assert not report.ok
    assert rig.broker.positions() == {}


def test_restart_inside_the_latency_still_waits(tmp_path: Path) -> None:
    """Revisión 2, considera 1: reiniciar antes de t + 1 h no adelanta las órdenes."""
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(T0 + timedelta(hours=16, minutes=1))
    rig = Rig(tmp_path, clock, market)
    rig.runner.tick()

    rig.at(T0 + timedelta(hours=16, minutes=5))
    report = rig.new_runner().tick()

    assert report.orders == 0


def test_reentry_after_a_kill_switch_reset_uses_new_order_ids(rig: Rig) -> None:
    entered(rig)
    rig.kill.trip("prueba", source="cli")
    rig.at(AFTER_LATENCY + timedelta(minutes=1))
    rig.runner.tick()
    rig.kill.reset(by="test")
    rig.at(AFTER_LATENCY + timedelta(minutes=2))
    rig.runner.tick()

    ids = [e.client_order_id for e in rig.events(OrderSubmitted)]
    assert len(ids) == len(set(ids)) == 6  # entrada, cierre del kill-switch y reentrada
    assert rig.broker.positions()[PERP] < 0


def test_rejected_orders_do_not_flood_the_journal_with_signals(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    tight = replace(LIMITS, max_leverage=Decimal("0.5"), hard_leverage=Decimal("0.5"))
    rig = Rig(tmp_path, clock, market, tight)
    rig.runner._leg_target = lambda marks: Decimal(490)  # type: ignore[method-assign]

    for minute in range(1, 6):
        rig.at(AFTER_LATENCY + timedelta(minutes=minute))
        rig.runner.tick()

    assert rig.events(SignalGenerated) == []


def test_sizing_stays_at_one_times_even_if_the_risk_allows_more(tmp_path: Path) -> None:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    loose = replace(LIMITS, max_leverage=Decimal("1.5"), hard_leverage=Decimal(2))
    rig = Rig(tmp_path, clock, market, loose)

    report = rig.runner.tick()

    positions = rig.broker.positions()
    assert report.equity is not None
    gross = (positions[SPOT] - positions[PERP]) * Decimal(100)
    assert gross / report.equity < Decimal(1)
