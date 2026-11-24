"""Elección del bróker del paper (PQ-52): simulado o Binance Demo, cada uno en su carpeta."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import structlog

from prometheus_platform.adapters.exchange_broker import ExchangeBroker
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.simulated_broker import SimulatedBroker
from prometheus_platform.api.paper.compose import PaperPaths, build, paper_dir
from prometheus_platform.api.paper.runner import RunnerConfig
from prometheus_platform.domain.carry_rules import CarryParams
from prometheus_platform.domain.model import InstrumentId
from prometheus_platform.ops.settings import Settings
from prometheus_platform.strategies.carry import perp_instrument

from ..adapters.test_exchange_broker import FakeGateway

T0 = datetime(2026, 11, 24, 12, tzinfo=UTC)
CONFIG = RunnerConfig(symbols=("SOLUSDT",), params=CarryParams(3, 0.0001))


def compose(tmp_path: Path, broker: str, gateway: FakeGateway | None = None) -> object:
    runner = build(
        settings=Settings(),
        config=CONFIG,
        client=None,  # type: ignore[arg-type]
        clock=FixedClock(T0),
        paths=PaperPaths(tmp_path),
        capital=Decimal(1000),
        broker=broker,
        execution=gateway,
    )
    return runner._broker


def test_each_broker_has_its_own_folder(tmp_path: Path) -> None:
    assert paper_dir(tmp_path) == tmp_path / "paper"
    assert paper_dir(tmp_path, "binance-demo") == tmp_path / "paper-binance-demo"
    with pytest.raises(ValueError, match="desconocido"):
        paper_dir(tmp_path, "binance-live")


def test_simulated_stays_the_default(tmp_path: Path) -> None:
    assert isinstance(compose(tmp_path, "simulado"), SimulatedBroker)


def test_binance_demo_wraps_the_gateway_and_reconciles_on_start(tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.remote = {perp_instrument("SOLUSDT"): Decimal(-1)}  # el exchange tiene un corto
    with structlog.testing.capture_logs() as logs:
        broker = compose(tmp_path, "binance-demo", gateway)
    assert isinstance(broker, ExchangeBroker)
    assert broker.name == "binance-demo"
    (gap,) = [e for e in logs if e["event"] == "paper_reconcile_gaps"]
    assert gap["gaps"] == {
        str(InstrumentId("SOLUSDT-PERP", perp_instrument("SOLUSDT").venue)): {
            "libro": "0",
            "exchange": "-1",
        }
    }


def test_binance_demo_needs_the_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PQ_BINANCE_API_KEY"):
        compose(tmp_path, "binance-demo")


def test_unknown_broker_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="desconocido"):
        compose(tmp_path, "otro")
