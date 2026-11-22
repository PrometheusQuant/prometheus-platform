"""El runner y el riesgo de contraparte (PQ-96): alerta a la mitad, crítico cierra todo."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.counterparty import CounterpartyReading
from prometheus_platform.domain.events import OrderSubmitted, RiskLimitBreached
from prometheus_platform.domain.model import FundingRate
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskManager
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

from .test_strategy_executor import CARRY, COSTS, LIMITS, T0, FeedMarket, at

SPOT, PERP = spot_instrument(CARRY), perp_instrument(CARRY)


class Signals:
    """Señales controlables; cuenta cuántas veces se leen."""

    def __init__(self) -> None:
        self.usdt = -0.001
        self.reads = 0

    def read(self) -> CounterpartyReading:
        self.reads += 1
        return CounterpartyReading(
            at=T0, system_normal=True, usdt_premium=self.usdt, perp_spread=0.0
        )


class Rig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.clock = FixedClock(at(0))
        self.market = FeedMarket(self.clock)
        self.market.funding[CARRY] = [
            FundingRate(instrument=PERP, funding_time=t, rate=Decimal("0.0003"))
            for t in (T0 - timedelta(hours=16), T0 - timedelta(hours=8), T0)
        ]
        self.journal = JsonlEventJournal(root / "diario.jsonl")
        self.broker = SimulatedBroker(
            self.market, lambda _: COSTS, self.clock, root / "broker.json", Decimal(1000)
        )
        self.kill = KillSwitch(root / "KILL_SWITCH", self.clock, self.journal, self.broker)
        self.signals = Signals()
        self.runner = PaperRunner(
            config=RunnerConfig(symbols=(CARRY,), params=CarryParams(k=3, theta=0.20)),
            market=self.market,
            broker=self.broker,
            journal=self.journal,
            kill_switch=self.kill,
            risk=RiskManager(LIMITS),
            clock=self.clock,
            heartbeat_path=root / "heartbeat.json",
            counterparty=self.signals,
        )

    def tick_at(self, instant: datetime) -> None:
        self.clock.advance_to(instant)
        self.runner.tick()

    def heartbeat(self) -> dict[str, object]:
        data: dict[str, object] = json.loads((self.root / "heartbeat.json").read_text("utf-8"))
        return data


def test_an_alert_halves_the_carry_and_is_reported_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(1))
    assert rig.broker.positions()[SPOT] == Decimal("4.9")  # 1000 / 2 · 0,98 / 100
    assert "contraparte" not in rig.heartbeat()

    rig.signals.usdt = -0.008  # USDT con un 0,8 % de descuento: alerta
    rig.tick_at(at(1, 20))
    held = rig.broker.positions()
    # A la mitad (la equity ya pagó las comisiones de la entrada, de ahí la tolerancia).
    assert held[SPOT] == pytest.approx(Decimal("2.45"), rel=Decimal("0.01"))
    assert held[PERP] == pytest.approx(Decimal("-2.45"), rel=Decimal("0.01"))
    assert not rig.kill.active  # una alerta no cierra todo
    assert rig.heartbeat()["contraparte"] == "alerta"
    assert [b.rule for b in _breaches(rig)] == ["contraparte_alerta"]
    assert any("reduccion" in o.client_order_id for o in _orders(rig))

    rig.tick_at(at(1, 30))  # sigue en alerta: no repite el aviso
    assert [b.rule for b in _breaches(rig)] == ["contraparte_alerta"]

    rig.signals.usdt = -0.001  # vuelve a la normalidad
    rig.tick_at(at(1, 40))
    assert "contraparte" not in rig.heartbeat()
    assert rig.broker.positions()[SPOT] == held[SPOT]  # no vuelve a crecer por sí solo


def test_a_critical_reading_trips_the_kill_switch(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.tick_at(at(1))
    rig.signals.usdt = -0.03  # descuento del 3 %: crítico
    rig.tick_at(at(1, 20))
    assert rig.kill.active
    rig.tick_at(at(1, 21))
    assert rig.broker.positions() == {}
    assert "contraparte" in rig.kill.state()["reason"]  # type: ignore[index]


def test_signals_are_read_at_the_configured_pace(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    for minutes in (5, 6, 7, 8, 9):
        rig.tick_at(at(0, minutes))
    assert rig.signals.reads == 1
    rig.tick_at(at(0, 10))  # 5 minutos después de la primera lectura
    assert rig.signals.reads == 2


def _breaches(rig: Rig) -> list[RiskLimitBreached]:
    return [e for e in rig.journal.replay() if isinstance(e, RiskLimitBreached)]


def _orders(rig: Rig) -> list[OrderSubmitted]:
    return [e for e in rig.journal.replay() if isinstance(e, OrderSubmitted)]


def test_other_strategies_size_with_half_their_budget_on_alert() -> None:
    from tests.contract.example_strategies import SmaTrend  # noqa: PLC0415

    from prometheus_platform.api.paper.executor import Account  # noqa: PLC0415
    from prometheus_platform.execution.allocation import StrategyAllocation  # noqa: PLC0415

    allocation = StrategyAllocation(SmaTrend(), Decimal("0.4"))
    common = {"equity": Decimal(1000), "held": {}, "marks": {}, "limits": LIMITS}
    normal = Account(**common, sizing_buffer=Decimal(0))  # type: ignore[arg-type]
    alert = Account(**common, sizing_buffer=Decimal(0), exposure_scale=Decimal("0.5"))  # type: ignore[arg-type]
    assert normal.budget(allocation) == Decimal(400)
    assert alert.budget(allocation) == Decimal(200)
