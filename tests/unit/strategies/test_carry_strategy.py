"""Regla del carry compartida (domain/carry_rules) y estrategia del paper trading (PQ-54)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prometheus_platform.domain.carry_rules import (
    CarryAction,
    CarryParams,
    annualize,
    decide,
    needs_rebalance,
    signal,
)
from prometheus_platform.domain.model import FundingRate
from prometheus_platform.strategies.carry import (
    CarryStrategy,
    is_perp,
    perp_instrument,
    spot_instrument,
    symbol_of,
)

P = CarryParams(k=2, theta=0.20)
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def rates(*values: str, hours: int = 8) -> list[FundingRate]:
    return [
        FundingRate(
            instrument=perp_instrument("SOLUSDT"),
            funding_time=T0 + timedelta(hours=hours * i),
            rate=Decimal(v),
            interval_hours=hours,
        )
        for i, v in enumerate(values)
    ]


@pytest.mark.parametrize(
    ("is_open", "s_k", "last", "expected"),
    [
        (False, None, 0.1, CarryAction.MANTENER),
        (False, 0.25, 0.1, CarryAction.ENTRAR),
        (False, 0.15, 0.1, CarryAction.MANTENER),
        (True, 0.15, 0.1, CarryAction.MANTENER),  # histéresis: sale bajo θ/2
        (True, 0.05, 0.1, CarryAction.SALIR),
        (True, 0.30, -0.0001, CarryAction.SALIR),  # tasa negativa: sale aunque S_k sea alto
    ],
)
def test_decide(is_open: bool, s_k: float | None, last: float, expected: CarryAction) -> None:
    assert decide(is_open=is_open, s_k=s_k, last_rate=last, params=P) is expected


def test_always_on_enters_and_never_exits() -> None:
    b1 = CarryParams(k=2, theta=0.20, always_on=True)
    assert decide(is_open=False, s_k=-1.0, last_rate=-0.1, params=b1) is CarryAction.ENTRAR
    assert decide(is_open=True, s_k=-1.0, last_rate=-0.1, params=b1) is CarryAction.MANTENER


def test_helpers() -> None:
    assert annualize(0.0001, 8) == pytest.approx(0.1095)
    assert annualize(0.0001, 4) == pytest.approx(0.219)
    assert signal([0.1], 2) is None
    assert signal([0.1, 0.3, 0.5], 2) == pytest.approx(0.4)
    assert needs_rebalance(111.0, 100.0, 100.0)
    assert not needs_rebalance(109.0, 100.0, 100.0)
    with pytest.raises(ValueError, match="k"):
        CarryParams(k=0, theta=0.2)


def test_instrument_helpers() -> None:
    assert (
        symbol_of(perp_instrument("BNBUSDT")) == "BNBUSDT" == symbol_of(spot_instrument("BNBUSDT"))
    )
    assert is_perp(perp_instrument("BNBUSDT"))
    assert not is_perp(spot_instrument("BNBUSDT"))


def test_evaluate_annualizes_with_each_settlement_interval() -> None:
    strategy = CarryStrategy(["SOLUSDT"], P, "carry-h2")
    # 0,0001 cada 4 h = 21,9 % anualizado: entra; con 8 h serían 10,95 % y no entraría.
    assert strategy.evaluate(rates("0.0001", "0.0001", hours=4), is_open=False).action is (
        CarryAction.ENTRAR
    )
    assert strategy.evaluate(rates("0.0001", "0.0001"), is_open=False).action is (
        CarryAction.MANTENER
    )
    with pytest.raises(ValueError, match="liquidaciones"):
        strategy.evaluate([], is_open=False)
    with pytest.raises(ValueError, match="símbolo"):
        CarryStrategy([], P, "x")


def test_walk_carries_the_state_between_settlements() -> None:
    strategy = CarryStrategy(["SOLUSDT"], P, "carry-h2")
    history = rates("0.0003", "0.0003", "0.00015", "-0.0001")

    walked = strategy.walk(history, since=None, is_open=False)
    assert [d.action for d in walked] == [
        CarryAction.MANTENER,  # aún no hay k = 2 tasas
        CarryAction.ENTRAR,
        CarryAction.MANTENER,
        CarryAction.SALIR,
    ]
    tail = strategy.walk(history, since=history[1].funding_time, is_open=True)
    assert [d.funding_time for d in tail] == [h.funding_time for h in history[2:]]
