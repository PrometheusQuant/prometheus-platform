"""Presupuestos y kill-switch por estrategia en el runner (PQ-83, ADR-0012)."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import structlog
from tests.contract.example_strategies import BTC, SmaTrend

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.cli import main
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.model import FundingRate, Venue
from prometheus_platform.execution.allocation import StrategyAllocation
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.portfolio_risk.risk import RiskManager
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

from .test_strategy_executor import CARRY, COSTS, LIMITS, T0, FeedMarket, at

SPOT, PERP = spot_instrument(CARRY), perp_instrument(CARRY)
HIGH = Decimal("0.0003")  # el carry entra


class Rig:
    def __init__(
        self,
        root: Path,
        *,
        carry_share: Decimal | None = None,
        strategies: tuple[StrategyAllocation, ...] = (),
        caps: dict[Venue, Decimal] | None = None,
    ) -> None:
        self.root = root
        self.clock = FixedClock(at(0))
        self.market = FeedMarket(self.clock)
        self.market.funding[CARRY] = [
            FundingRate(instrument=PERP, funding_time=t, rate=HIGH)
            for t in (T0 - timedelta(hours=16), T0 - timedelta(hours=8), T0)
        ]
        self.paths = PaperPaths(root)
        self.journal = JsonlEventJournal(self.paths.journal)
        self.broker = SimulatedBroker(
            self.market, lambda _: COSTS, self.clock, self.paths.broker_state, Decimal(1000)
        )
        ids = ["carry-h2", *(a.strategy_id for a in strategies)]
        self.kills = {
            i: KillSwitch(self.paths.strategy_kill_switch(i), self.clock, self.journal) for i in ids
        }
        self.global_kill = KillSwitch(self.paths.kill_switch, self.clock, self.journal, self.broker)
        self.runner = PaperRunner(
            config=RunnerConfig(
                symbols=(CARRY,), params=CarryParams(k=3, theta=0.20), carry_share=carry_share
            ),
            market=self.market,
            broker=self.broker,
            journal=self.journal,
            kill_switch=self.global_kill,
            risk=RiskManager(LIMITS),
            clock=self.clock,
            heartbeat_path=self.paths.heartbeat,
            strategies=strategies,
            feed=self.market,
            strategy_kills=self.kills,
            exchange_caps=caps,
        )

    def tick_at(self, hours: int, minutes: int = 5) -> None:
        self.clock.advance_to(at(hours, minutes))
        self.runner.tick()

    def heartbeat(self) -> dict[str, object]:
        data: dict[str, object] = json.loads(self.paths.heartbeat.read_text("utf-8"))
        return data


SMA = (StrategyAllocation(SmaTrend(), Decimal("0.3")),)


def test_carry_share_leaves_the_rest_in_cash(tmp_path: Path) -> None:
    rig = Rig(tmp_path, carry_share=Decimal("0.4"))
    rig.tick_at(1)
    # 1000 · 0,4 / 1 símbolo / 2 patas · 0,98 = 196 por pata, a 100.
    assert rig.broker.positions() == {SPOT: Decimal("1.96"), PERP: Decimal("-1.96")}


def test_without_carry_share_the_carry_takes_what_the_others_leave(tmp_path: Path) -> None:
    rig = Rig(tmp_path, strategies=SMA)
    rig.tick_at(1)
    # 1000 · (1 - 0,3) / 2 · 0,98 = 343 por pata.
    assert rig.broker.positions()[SPOT] == Decimal("3.43")


def test_shares_cannot_add_up_to_more_than_everything(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="suman más de 1"):
        Rig(tmp_path, carry_share=Decimal("0.8"), strategies=SMA)
    with pytest.raises(ValueError, match="carry_share"):
        RunnerConfig(symbols=(CARRY,), params=CarryParams(k=3, theta=0.2), carry_share=Decimal(0))


def test_the_exchange_cap_is_checked_before_starting(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"tope de 0\.125"):
        Rig(tmp_path, caps={Venue.BINANCE: Decimal("0.125")})  # el carry solo ya usa todo
    rig = Rig(
        tmp_path,
        carry_share=Decimal("0.05"),
        strategies=(StrategyAllocation(SmaTrend(), Decimal("0.05")),),
        caps={Venue.BINANCE: Decimal("0.125")},
    )
    rig.tick_at(1)
    assert rig.broker.positions()[SPOT] == Decimal("0.245")  # 1000 · 0,05 / 2 · 0,98 / 100


def test_a_strategy_kill_switch_closes_only_that_strategy(tmp_path: Path) -> None:
    rig = Rig(tmp_path, strategies=SMA)
    rig.tick_at(0)  # SmaTrend decide (rige a la 01:00); el carry decide con la liquidación de 00:00
    rig.tick_at(1)
    assert {SPOT, PERP, BTC} <= set(rig.broker.positions())

    rig.kills["carry-h2"].trip("prueba", source="cli")
    rig.tick_at(1, 10)
    held = rig.broker.positions()
    assert SPOT not in held
    assert PERP not in held
    assert BTC in held  # la tendencia sigue
    assert rig.heartbeat()["estrategias_detenidas"] == ["carry-h2"]
    assert rig.heartbeat()["kill_switch"] is False
    rig.tick_at(2)  # el carry no vuelve a entrar mientras siga detenido
    assert SPOT not in rig.broker.positions()

    rig.kills["carry-h2"].reset("David")
    rig.kills["sma-ejemplo"].trip("prueba", source="cli")
    rig.tick_at(2, 10)
    held = rig.broker.positions()
    assert BTC not in held
    assert SPOT in held  # el carry vuelve tras el rearme
    assert rig.heartbeat()["estrategias_detenidas"] == ["sma-ejemplo"]


def test_the_global_kill_switch_still_closes_everything(tmp_path: Path) -> None:
    rig = Rig(tmp_path, strategies=SMA)
    rig.tick_at(0)
    rig.tick_at(1)
    rig.global_kill.trip("prueba", source="cli")
    rig.tick_at(1, 10)
    assert rig.broker.positions() == {}
    assert rig.heartbeat()["kill_switch"] is True


def test_strategy_flags_live_next_to_the_global_one(tmp_path: Path) -> None:
    paths = PaperPaths(tmp_path)
    assert paths.strategy_kill_switch("carry-h2") == tmp_path / "KILL_SWITCH-carry-h2"
    with pytest.raises(ValueError, match="strategy_id"):
        paths.strategy_kill_switch("../fuera")
    (tmp_path / "KILL_SWITCH-carry-h2").write_text("{}")
    (tmp_path / "KILL_SWITCH-carry-h2.rearmando").write_text("{}")  # temporal del rearme
    assert list(paths.strategy_kill_switches()) == ["carry-h2"]


def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    code = main(list(argv))
    structlog.reset_defaults()
    return code


def test_cli_stops_and_rearms_a_single_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli(tmp_path, monkeypatch, "paper", "kill", "--strategy", "carry-h2") == 0
    assert "kill-switch de la estrategia carry-h2 ACTIVADO" in capsys.readouterr().out
    assert (tmp_path / "lake/paper/KILL_SWITCH-carry-h2").exists()
    assert not (tmp_path / "lake/paper/KILL_SWITCH").exists()  # el global sigue armado

    assert cli(tmp_path, monkeypatch, "paper", "status") == 0
    out = capsys.readouterr().out
    assert "kill-switch: ARMADO" in out
    assert "estrategia carry-h2: DETENIDA" in out

    rearm = ("paper", "kill", "--strategy", "carry-h2", "--reset", "--confirm", "--by", "David")
    assert cli(tmp_path, monkeypatch, *rearm) == 0
    assert "kill-switch de la estrategia carry-h2 rearmado" in capsys.readouterr().out
    assert not (tmp_path / "lake/paper/KILL_SWITCH-carry-h2").exists()

    assert cli(tmp_path, monkeypatch, "paper", "kill", "--strategy", "../x") == 2


@pytest.mark.parametrize("cap", ["BINANCE", "NOEXISTE=0.1", "BINANCE=0", "BINANCE=abc"])
def test_cli_rejects_bad_exchange_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: str
) -> None:
    args = ("paper", "run", "--once", "--exchange-cap", cap)
    assert cli(tmp_path, monkeypatch, *args) == 2
