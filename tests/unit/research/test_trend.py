"""Motor de tendencia (PQ-67): reglas del pre-registro de la Estrategia 2, con datos sintéticos.

Ninguna prueba toca datos reales: cada ejecución real sería un ensayo y sumaría a N.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from tests.unit.research.conftest import make_market

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.research.carry_evaluation import TrialRecord
from prometheus_platform.research.trend import (
    EXECUTION_DELAY,
    Hypothesis,
    SymbolMarket,
    TrendConfig,
    run_and_register,
    simulate_trend,
    target_weight,
)

T0 = datetime(2023, 1, 1, tzinfo=UTC)
FREE = CostModel(spot_fee=0.0, perp_fee=0.0, slippage=0.0)
COSTS = CostModel()  # VIP0 + 2 pb (escenario principal, §6)
L5 = TrendConfig(lookback=5, sigma_target=0.40)


def wave(i: int) -> float:
    """Sube 60 días y baja otros 60, con ruido diario determinista."""
    day = i // 24
    trend = 100 * (1.004 ** min(day, 60)) * (0.996 ** max(day - 60, 0))
    return trend * (1 + 0.01 * math.sin(i / 7))


def market(
    hours: int = 24 * 120,
    price: Callable[[int], float] = wave,
    rate: Callable[[int], float] = lambda _: 0.0001,
    start: datetime = T0,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    return make_market(hours, price=price, rate=rate, start=start)


def test_weight_uses_only_the_past() -> None:
    """FR-002: el peso de t no cambia si se alteran los precios posteriores a t."""
    hourly, _ = market()
    cutoff = T0 + timedelta(days=70)

    def crash(i: int) -> float:
        at = T0 + timedelta(hours=i)
        return wave(i) * (0.2 if at > cutoff else 1.0)

    altered, _ = market(price=crash)
    a = simulate_trend("BTC", hourly, None, config=L5, costs=COSTS, capital=1.0, start=T0)
    b = simulate_trend("BTC", altered, None, config=L5, costs=COSTS, capital=1.0, start=T0)

    before = [w for w in a.weights if w[0] < cutoff]
    assert before
    assert before == [w for w in b.weights if w[0] < cutoff]


def test_target_weight_follows_the_formula() -> None:
    rng = np.random.default_rng(1)
    closes = list(100 * np.cumprod(1 + rng.normal(0.002, 0.03, 200)))
    w = target_weight(closes, TrendConfig(20, 0.20))
    returns = np.diff(closes[-31:]) / np.array(closes[-31:-1])
    sigma = float(np.std(returns, ddof=1)) * math.sqrt(365)
    signal = 1.0 if closes[-1] > closes[-21] else 0.0
    assert w == pytest.approx(signal * min(1.0, 0.20 / sigma))
    assert target_weight(closes[:20], TrendConfig(20, 0.20)) is None  # falta historia


def test_execution_waits_for_the_bar_that_opens_one_hour_after_the_decision() -> None:
    """FR-003: la orden de las 00:00 se ejecuta al open de la vela de las 01:00 (no KE-016)."""
    hourly, _ = market()
    result = simulate_trend("BTC", hourly, None, config=L5, costs=FREE, capital=1.0, start=T0)

    assert result.trades
    decided = {at for at, _ in result.weights}
    for executed, _ in result.trades:
        assert executed.hour == 1
        assert executed - EXECUTION_DELAY in decided


def test_t1_is_long_or_cash_and_t2_can_short_and_collects_funding() -> None:
    def down(i: int) -> float:
        return 100 * 0.997 ** (i // 24) * (1 + 0.01 * math.sin(i / 7))

    hourly, settlements = market(price=down, rate=lambda _: 0.0003)
    t1 = simulate_trend("BTC", hourly, settlements, config=L5, costs=FREE, capital=1.0, start=T0)
    t2_config = TrendConfig(5, 0.40, hypothesis=Hypothesis.T2)
    t2 = simulate_trend(
        "BTC", hourly, settlements, config=t2_config, costs=FREE, capital=1.0, start=T0
    )

    assert all(w >= 0 for _, w in t1.weights)
    assert t1.funding_pnl == 0  # el spot no paga funding
    assert any(w < 0 for _, w in t2.weights)
    assert t2.funding_pnl > 0  # el corto cobra con funding positivo


def test_no_trade_band_limits_turnover() -> None:
    hourly, _ = market()
    result = simulate_trend("BTC", hourly, None, config=L5, costs=FREE, capital=1.0, start=T0)
    weights = [w for _, w in result.weights]
    assert all(abs(b - a) > 0.10 for a, b in itertools.pairwise(weights))
    assert len(result.trades) < 120 / 3  # mucho menos que un ajuste diario


def test_costs_are_charged_on_traded_notional() -> None:
    hourly, _ = market(price=lambda i: 100.0)
    b1 = TrendConfig(1, 0.2, buy_and_hold=True)
    result = simulate_trend("BTC", hourly, None, config=b1, costs=COSTS, capital=1.0, start=T0)

    assert len(result.trades) == 1  # comprar y mantener: una sola compra
    assert result.costs == pytest.approx(result.traded_notional * COSTS.spot)
    assert result.traded_notional == pytest.approx(1.0, rel=1e-6)
    final = result.daily_equity["equity"][-1]
    assert final == pytest.approx(1.0 - result.costs, rel=1e-9)  # precio plano: solo costes


def test_development_never_decides_or_collects_at_the_holdout_boundary() -> None:
    """KE-014: ni decisiones ni funding en eventos >= HOLDOUT_START."""
    start = HOLDOUT_START - timedelta(days=40)
    hourly, settlements = market(hours=24 * 50, start=start, rate=lambda _: 0.0003)
    config = TrendConfig(5, 0.40, hypothesis=Hypothesis.T2)
    result = simulate_trend(
        "BTC", hourly, settlements, config=config, costs=FREE, capital=1.0, start=start
    )

    assert all(at < HOLDOUT_START for at, _ in result.weights)
    assert all(at < HOLDOUT_START + EXECUTION_DELAY for at, _ in result.trades)
    assert result.daily_equity["date"][-1] == HOLDOUT_START  # se valora el cierre del desarrollo


def test_run_and_register_counts_every_execution() -> None:
    class Registry:
        def __init__(self) -> None:
            self.items: list[TrialRecord] = []

        def log_trial(self, trial: TrialRecord) -> None:
            self.items.append(trial)

        def trials(self) -> list[TrialRecord]:
            return self.items

    hourly, _ = market()
    data = [SymbolMarket("BTCUSDT", hourly), SymbolMarket("ETHUSDT", hourly)]
    registry = Registry()
    frame = run_and_register(data, L5, COSTS, registry)

    (trial,) = registry.items
    assert trial.name == "T1-L5-vol40"
    assert trial.tags["family"] == "tendencia"
    assert {"sharpe", "sharpe_daily", "cagr", "max_drawdown", "turnover_anual"} <= set(
        trial.metrics
    )
    assert frame.height > 0


def test_config_names_and_validation() -> None:
    assert TrendConfig(60, 0.20).name == "T1-L60-vol20"
    assert TrendConfig(60, 0.20, hypothesis=Hypothesis.T2).name == "T2-L60-vol20"
    assert TrendConfig(60, 0.20, vol_targeting=False).name == "T1-L60-sin-vol"
    assert TrendConfig(1, 0.2, buy_and_hold=True).name == "B1-comprar-y-mantener"
    with pytest.raises(ValueError, match="B1"):
        TrendConfig(1, 0.2, hypothesis=Hypothesis.T2, buy_and_hold=True)
    with pytest.raises(ValueError, match="L"):
        TrendConfig(0, 0.2)
