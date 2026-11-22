"""Riesgo de contraparte (PQ-96): de las señales públicas al nivel y la acción."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prometheus_platform.domain.counterparty import CounterpartyReading
from prometheus_platform.portfolio_risk.counterparty import (
    EXPOSURE_ON_ALERT,
    Level,
    Thresholds,
    assess,
)

T0 = datetime(2026, 11, 22, tzinfo=UTC)


def reading(**kwargs: object) -> CounterpartyReading:
    base: dict[str, object] = {"system_normal": True, "usdt_premium": -0.001, "perp_spread": 0.0001}
    return CounterpartyReading(at=T0, **{**base, **kwargs})  # type: ignore[arg-type]


def test_quiet_markets_are_normal_and_keep_full_exposure() -> None:
    result = assess(reading())
    assert result.level is Level.NORMAL
    assert result.reasons == []
    assert result.exposure_scale == 1.0


@pytest.mark.parametrize(
    ("kwargs", "level"),
    [
        ({"usdt_premium": -0.006}, Level.ALERTA),
        ({"usdt_premium": 0.006}, Level.ALERTA),  # una prima también delata tensión
        ({"usdt_premium": -0.025}, Level.CRITICO),
        ({"perp_spread": -0.007}, Level.ALERTA),
        ({"perp_spread": 0.03}, Level.CRITICO),
        ({"system_normal": False}, Level.ALERTA),
    ],
)
def test_each_signal_escalates_on_its_own(kwargs: dict[str, object], level: Level) -> None:
    result = assess(reading(**kwargs))
    assert result.level is level
    assert len(result.reasons) == 1


def test_the_worst_signal_wins_and_every_reason_is_listed() -> None:
    result = assess(reading(usdt_premium=-0.006, perp_spread=0.03, system_normal=False))
    assert result.level is Level.CRITICO
    assert len(result.reasons) == 3
    assert result.exposure_scale == EXPOSURE_ON_ALERT


def test_unknown_signals_do_not_change_the_level_but_are_reported() -> None:
    result = assess(reading(system_normal=None, usdt_premium=None, perp_spread=None))
    assert result.level is Level.NORMAL
    assert result.unknown == ["estado del sistema", "prima de USDT", "spread del perpetuo"]


def test_thresholds_are_validated_and_configurable() -> None:
    strict = Thresholds(
        usdt_alert=0.001, usdt_critical=0.002, spread_alert=0.001, spread_critical=0.002
    )
    assert assess(reading(usdt_premium=-0.0015), strict).level is Level.ALERTA
    with pytest.raises(ValueError, match="USDT"):
        Thresholds(usdt_alert=0.03, usdt_critical=0.02)
    with pytest.raises(ValueError, match="spread"):
        Thresholds(spread_alert=0)
