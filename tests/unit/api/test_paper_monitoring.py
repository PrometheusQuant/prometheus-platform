"""Monitoreo del paper trading (PQ-55): lectura del diario, vigilante y alertas del runner."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.api.test_paper_runner import (
    AFTER_LATENCY,
    HIGH,
    PERP,
    SYMBOL,
    T0,
    FakeMarket,
    Rig,
    settlements,
)

from prometheus_platform.adapters.in_memory import FixedClock, RecordingNotifier
from prometheus_platform.api.cli import main
from prometheus_platform.api.paper.report import build_view, daily_summary, read_heartbeat
from prometheus_platform.api.paper.runner import PaperRunner, RunnerConfig
from prometheus_platform.api.paper.watchdog import RunnerHealth, Watchdog
from prometheus_platform.domain.alerts import AlertSeverity
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.events import OrderFilled
from prometheus_platform.domain.model import Side
from prometheus_platform.portfolio_risk.risk import RiskManager
from prometheus_platform.strategies.carry import spot_instrument


def runner_with(rig: Rig, notifier: RecordingNotifier, **config: object) -> PaperRunner:
    return PaperRunner(
        config=RunnerConfig(
            symbols=(SYMBOL,),
            params=CarryParams(k=3, theta=0.20),
            history_limit=30,
            **config,  # type: ignore[arg-type]
        ),
        market=rig.market,
        broker=rig.broker,
        journal=rig.journal,
        kill_switch=rig.kill,
        risk=RiskManager(rig.limits),
        clock=rig.clock,
        heartbeat_path=rig.root / "heartbeat.json",
        notifier=notifier,
    )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    clock = FixedClock(T0)
    market = FakeMarket(clock)
    for t in settlements(3):
        market.add(t, HIGH)
    clock.advance_to(AFTER_LATENCY)
    return Rig(tmp_path, clock, market)


# --- lectura del diario ---------------------------------------------------------------------


def test_view_rebuilds_positions_costs_and_funding_from_the_journal(rig: Rig) -> None:
    rig.runner.start()
    rig.runner.tick()
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()

    view = build_view(rig.journal.replay())

    assert view.broker == "simulado"
    assert view.positions == rig.broker.positions()  # el diario cuadra con el bróker
    assert view.fees == sum((e.fee for e in rig.events(OrderFilled)), Decimal(0))
    assert view.funding > 0
    assert [f.label for f in view.fills] == ["entrada", "entrada"]
    assert view.equity is not None
    assert view.drawdown == 0


def test_daily_summary_counts_only_that_day(rig: Rig) -> None:
    rig.runner.tick()
    rig.market.add(T0 + timedelta(hours=24), HIGH)
    rig.at(T0 + timedelta(hours=24, minutes=1))
    rig.runner.tick()
    view = build_view(rig.journal.replay())

    first, second = (
        daily_summary(view, T0.date()),
        daily_summary(view, (T0 + timedelta(days=1)).date()),
    )

    assert first.orders == 2
    assert first.funding == 0  # la primera liquidación no tenía posición
    assert second.orders == 0
    assert second.funding > 0
    assert second.details()["órdenes ejecutadas"] == "0"


def test_unreadable_heartbeat_is_none(tmp_path: Path) -> None:
    assert read_heartbeat(tmp_path / "no-existe.json") is None
    (tmp_path / "roto.json").write_text("[1, 2]", encoding="utf-8")
    assert read_heartbeat(tmp_path / "roto.json") is None


# --- alertas del runner ---------------------------------------------------------------------


def test_daily_summary_is_sent_when_the_utc_day_changes(rig: Rig) -> None:
    notifier = RecordingNotifier()
    runner = runner_with(rig, notifier)
    runner.tick()
    assert notifier.alerts == []

    rig.at(T0 + timedelta(days=1, minutes=1))
    runner.tick()

    (summary,) = notifier.alerts
    assert summary.severity is AlertSeverity.INFO
    assert summary.details["día (UTC)"] == T0.date().isoformat()
    assert summary.details["órdenes ejecutadas"] == "2"


def test_drawdown_alert_fires_once_per_crossing(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    from prometheus_platform.api.paper import runner as runner_module  # noqa: PLC0415

    seen: list[str] = []
    monkeypatch.setattr(runner_module.log, "error", lambda event, **_: seen.append(event))
    runner = runner_with(rig, RecordingNotifier(), drawdown_alert=Decimal("0.01"))
    runner.tick()  # entra
    rig.market.price[SYMBOL] = (Decimal(90), Decimal(100))  # el spot cae y el perp no: base
    for minute in (2, 3, 4):
        rig.at(AFTER_LATENCY + timedelta(minutes=minute))
        runner.tick()

    assert seen.count("paper_drawdown") == 1


def test_unhedged_leg_is_a_critical_log(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    from prometheus_platform.api.paper import runner as runner_module  # noqa: PLC0415

    seen: list[str] = []
    monkeypatch.setattr(runner_module.log, "critical", lambda event, **_: seen.append(event))
    rig.runner.tick()
    perp_qty = rig.broker.positions()[PERP]
    rig.broker.submit("fallo", PERP, Side.BUY, -perp_qty)
    monkeypatch.setattr(rig.runner, "_reconcile", lambda *_: 0)  # sin reparación: se ve el aviso

    rig.at(AFTER_LATENCY + timedelta(minutes=1))
    rig.runner.tick()

    assert "paper_unhedged_leg" in seen
    assert spot_instrument(SYMBOL) in rig.broker.positions()


# --- vigilante ------------------------------------------------------------------------------

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


def beat(path: Path, at: datetime, *, ok: bool = True, detail: str = "") -> None:
    path.write_text(
        json.dumps({"at": at.isoformat(), "ok": ok, "detail": detail}), encoding="utf-8"
    )


def make_dog(tmp_path: Path, clock: FixedClock, notifier: RecordingNotifier) -> Watchdog:
    return Watchdog(
        heartbeat_path=tmp_path / "heartbeat.json",
        state_path=tmp_path / "watchdog.json",
        notifier=notifier,
        clock=clock,
        max_age=timedelta(minutes=10),
        environment="paper",
    )


def test_watchdog_alerts_on_changes_not_on_every_check(tmp_path: Path) -> None:
    clock, notifier = FixedClock(NOW), RecordingNotifier()
    beat(tmp_path / "heartbeat.json", NOW)
    assert make_dog(tmp_path, clock, notifier).check() is RunnerHealth.OK
    assert notifier.alerts == []

    clock.advance_to(NOW + timedelta(minutes=11))  # el runner dejó de reportar
    assert make_dog(tmp_path, clock, notifier).check() is RunnerHealth.DOWN
    clock.advance_to(NOW + timedelta(minutes=12))
    make_dog(tmp_path, clock, notifier).check()  # sigue caído: no repite
    beat(tmp_path / "heartbeat.json", NOW + timedelta(minutes=13))
    clock.advance_to(NOW + timedelta(minutes=13))
    assert make_dog(tmp_path, clock, notifier).check() is RunnerHealth.OK

    assert [a.severity for a in notifier.alerts] == [AlertSeverity.CRITICAL, AlertSeverity.INFO]


def test_watchdog_reports_failing_cycles_and_missing_heartbeats(tmp_path: Path) -> None:
    clock, notifier = FixedClock(NOW), RecordingNotifier()
    assert make_dog(tmp_path, clock, notifier).check() is RunnerHealth.MISSING
    beat(tmp_path / "heartbeat.json", NOW, ok=False, detail="SOLUSDT (liquidar): ConnectionError")
    assert make_dog(tmp_path, clock, notifier).check() is RunnerHealth.FAILING

    assert [a.severity for a in notifier.alerts] == [AlertSeverity.CRITICAL, AlertSeverity.ERROR]
    assert "ConnectionError" in notifier.alerts[-1].details["detalle"]


def test_watchdog_repeats_a_long_outage_every_hour(tmp_path: Path) -> None:
    clock, notifier = FixedClock(NOW), RecordingNotifier()
    beat(tmp_path / "heartbeat.json", NOW - timedelta(hours=1))
    make_dog(tmp_path, clock, notifier).check()
    clock.advance_to(NOW + timedelta(minutes=30))
    make_dog(tmp_path, clock, notifier).check()
    clock.advance_to(NOW + timedelta(hours=1))
    make_dog(tmp_path, clock, notifier).check()

    assert len(notifier.alerts) == 2


def test_cli_watchdog_once_returns_the_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    assert main(["paper", "watchdog", "--once"]) == 1  # sin heartbeat
    (tmp_path / "paper").mkdir(exist_ok=True)
    beat(tmp_path / "paper/heartbeat.json", datetime.now(UTC))
    assert main(["paper", "watchdog", "--once"]) == 0
    assert main(["paper", "watchdog", "--interval", "0"]) == 2


# --- revisión de Boris en #63 ---------------------------------------------------------------


def test_costs_include_commissions_and_slippage_exactly(rig: Rig) -> None:
    """A precio constante, lo que se pierde al entrar es exactamente comisiones + slippage."""
    rig.runner.tick()
    view = build_view(rig.journal.replay())

    assert view.slippage > 0  # el CostModel del rig tiene 5 pb de slippage
    assert view.costs == view.fees + view.slippage
    assert (
        Decimal(1000)
        - rig.broker.cash()
        - sum(
            q * Decimal(100)
            for i, q in rig.broker.positions().items()
            if i == spot_instrument(SYMBOL)
        )
        == view.costs
    )
    summary = daily_summary(view, T0.date())
    assert summary.details()["slippage"] == f"{view.slippage:.4f} USD"


def test_watchdog_retries_until_the_alert_is_delivered(tmp_path: Path) -> None:
    clock = FixedClock(NOW)
    failing = RecordingNotifier(deliver=False)
    beat(tmp_path / "heartbeat.json", NOW - timedelta(hours=1))  # caído

    assert make_dog(tmp_path, clock, failing).check() is RunnerHealth.DOWN
    clock.advance_to(NOW + timedelta(minutes=1))
    make_dog(tmp_path, clock, failing).check()
    assert len(failing.alerts) == 2  # no se entregó: se reintenta en la revisión siguiente

    working = RecordingNotifier()
    clock.advance_to(NOW + timedelta(minutes=2))
    make_dog(tmp_path, clock, working).check()
    clock.advance_to(NOW + timedelta(minutes=3))
    make_dog(tmp_path, clock, working).check()
    assert len(working.alerts) == 1  # entregada: ya no se repite hasta repeat_after
