from datetime import UTC, datetime, timedelta

import pytest

from prometheus_platform.research.backtest import (
    CarryConfig,
    CostModel,
    portfolio_returns,
    simulate_symbol,
)

from .conftest import T0, HourlyFactory

FREE = CostModel(spot_fee=0.0, perp_fee=0.0, slippage=0.0)


def run(market: HourlyFactory, config: CarryConfig, costs: CostModel = FREE, **kwargs: object):  # type: ignore[no-untyped-def]
    hourly, settlements = market(**kwargs)
    return simulate_symbol("BTCUSDT", hourly, settlements, config=config, costs=costs, capital=1.0)


def test_enters_one_hour_after_the_signal_and_collects_funding_only_afterwards(
    market: HourlyFactory,
) -> None:
    # 0,01 %/8 h = 10,95 % anual ≥ θ = 10 %: entra en la 3.ª liquidación (cuando S_3 existe).
    result = run(market, CarryConfig(3, 0.10), hours=24 * 10)
    assert result.trades[0] == (T0 + timedelta(hours=24), "entrada")
    assert result.cycles == 1
    settlements_after_entry = (24 * 10 - 24) // 8
    assert result.funding_pnl == pytest.approx(0.5 * 0.0001 * settlements_after_entry)
    assert result.price_pnl == pytest.approx(0.0)
    assert result.daily_equity["equity"][-1] == pytest.approx(1 + result.funding_pnl)


def test_never_enters_below_threshold(market: HourlyFactory) -> None:
    result = run(market, CarryConfig(3, 0.20), hours=24 * 5)
    assert result.cycles == 0
    assert result.daily_equity["equity"].to_list() == pytest.approx([1.0] * 5)


def test_exits_on_negative_funding_and_pays_costs(market: HourlyFactory) -> None:
    costs = CostModel(spot_fee=0.001, perp_fee=0.0005, slippage=0.0002)
    result = run(
        market,
        CarryConfig(3, 0.10),
        costs,
        hours=24 * 6,
        rate=lambda h: 0.0001 if h < 72 else -0.0001,
    )
    assert [label for _, label in result.trades] == ["entrada", "salida"]
    # Ida y vuelta de las 4 patas sobre un nocional de 0,5 por pata.
    assert result.costs == pytest.approx(0.5 * 2 * (0.0012 + 0.0007), rel=1e-3)


def test_keeps_one_times_leverage_when_price_doubles(market: HourlyFactory) -> None:
    result = run(market, CarryConfig(3, 0.10), hours=24 * 20, price=lambda i: 100.0 * (1 + i / 240))
    rebalances = [label for _, label in result.trades if label == "rebalanceo"]
    assert rebalances  # la subida obliga a reducir nocional
    # Cubierto: el capital solo cambia por el funding, aunque el precio se multiplique.
    final = result.daily_equity["equity"][-1]
    assert final == pytest.approx(1 + result.funding_pnl, abs=1e-6)


def test_always_on_benchmark_ignores_the_threshold(market: HourlyFactory) -> None:
    result = run(market, CarryConfig(3, 0.0, always_on=True), hours=24 * 5, rate=lambda _: -0.0001)
    assert result.cycles == 1
    assert result.funding_pnl < 0  # B1 paga cuando el funding es negativo
    assert CarryConfig(3, 0.0, always_on=True).name == "B1-siempre-activo"
    assert CarryConfig(9, 0.2).name == "k9-theta20"


def test_missing_spot_bar_executes_on_the_next_one(market: HourlyFactory) -> None:
    result = run(market, CarryConfig(3, 0.10), hours=24 * 3, missing_spot=frozenset({25}))
    assert result.cycles == 1
    assert result.daily_equity["equity"][-1] == pytest.approx(1 + result.funding_pnl)


def test_end_cuts_the_simulation(market: HourlyFactory) -> None:
    hourly, settlements = market(hours=24 * 5)
    result = simulate_symbol(
        "X", hourly, settlements, config=CarryConfig(3, 0.1), costs=FREE, capital=1.0,
        end=T0 + timedelta(days=2),
    )  # fmt: skip
    assert result.daily_equity.height == 2


def test_portfolio_sums_symbols_and_keeps_late_starters_in_cash(market: HourlyFactory) -> None:
    hourly_a, settle_a = market(hours=24 * 6)
    hourly_b, settle_b = market(hours=24 * 3, start=T0 + timedelta(days=3))
    cfg = CarryConfig(3, 0.10)
    a = simulate_symbol("A", hourly_a, settle_a, config=cfg, costs=FREE, capital=0.5)
    b = simulate_symbol("B", hourly_b, settle_b, config=cfg, costs=FREE, capital=0.5)
    empty = simulate_symbol("C", hourly_a.head(0), settle_a, config=cfg, costs=FREE, capital=0.5)
    frame = portfolio_returns([a, b, empty], 0.5)
    # Antes de que B empiece, su parte y la de C (sin datos) cuentan como efectivo.
    assert frame["equity"][0] == pytest.approx(a.daily_equity["equity"][1] + 0.5 + 0.5)
    assert frame["date"][-1] == datetime(2023, 1, 7, tzinfo=UTC)
    assert frame["equity"][-1] == pytest.approx(
        a.daily_equity["equity"][-1] + b.daily_equity["equity"][-1] + 0.5
    )
    assert portfolio_returns([empty], 0.5).is_empty()
