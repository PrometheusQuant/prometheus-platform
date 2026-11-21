"""Presupuesto de capital con tope de CVaR (PQ-83): reglas puras con escenarios controlados."""

from __future__ import annotations

import numpy as np
import pytest

from prometheus_platform.portfolio_risk import budget as b


def test_cvar95_is_the_mean_loss_of_the_worst_5_percent() -> None:
    returns = np.arange(-50, 50, dtype=np.float64) / 100  # -0,50 … 0,49
    assert b.cvar95(returns) == pytest.approx(-np.mean(returns[:5]), abs=0.006)
    with pytest.raises(ValueError, match="vacía"):
        b.cvar95(np.array([]))


def test_joint_scenarios_share_the_blocks_so_correlation_survives() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.0005, 0.01, 1500)
    annual = b.joint_annual_scenarios({"a": x, "b": x, "c": -x}, n_paths=500, seed=1)
    assert annual["a"].shape == (500,)
    np.testing.assert_array_equal(annual["a"], annual["b"])  # mismos bloques
    assert np.corrcoef(annual["a"], annual["c"])[0, 1] < -0.9
    again = b.joint_annual_scenarios({"a": x}, n_paths=500, seed=1)
    np.testing.assert_array_equal(again["a"], annual["a"])  # determinista con semilla


def test_joint_scenarios_compound_a_full_year() -> None:
    annual = b.joint_annual_scenarios({"a": np.full(100, 0.001)}, n_paths=3)
    np.testing.assert_allclose(annual["a"], 1.001**365 - 1)


@pytest.mark.parametrize(
    ("daily", "message"),
    [
        ({}, "al menos una"),
        ({"a": np.zeros(30), "b": np.zeros(31)}, "alineados"),
        ({"a": np.zeros(10)}, "al menos 21"),
    ],
)
def test_joint_scenarios_reject_bad_inputs(daily: dict[str, np.ndarray], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        b.joint_annual_scenarios(daily)


def test_an_exchange_failure_hits_every_strategy_on_it_at_once() -> None:
    annual = {n: np.full(20_000, 0.1) for n in ("a", "b", "c")}
    out = b.apply_exchange_failures(
        annual, {"a": "binance", "b": "binance", "c": "bybit"}, {"binance": 0.3}
    )
    np.testing.assert_array_equal(out["a"] == -1, out["b"] == -1)
    assert (out["a"] == -1).mean() == pytest.approx(0.3, abs=0.02)
    assert not (out["c"] == -1).any()  # bybit no tiene probabilidad: no quiebra


def test_exchange_cap_follows_the_failure_tail() -> None:
    # p = 2 % < 5 %: la quiebra ocupa 2/5 de la cola, x · 0,4 ≤ 5 % → x ≤ 12,5 %.
    assert b.exchange_cap(
        cvar_limit=0.05, assumed_probability=0.02, break_even_probability=0.004
    ) == pytest.approx(0.125)
    # Manda la mayor: si la de equilibrio es más alta, el tope baja.
    assert b.exchange_cap(
        cvar_limit=0.05, assumed_probability=0.01, break_even_probability=0.02
    ) == pytest.approx(0.125)
    assert (
        b.exchange_cap(cvar_limit=0.05, assumed_probability=0.1, break_even_probability=0) == 0.05
    )
    assert b.exchange_cap(cvar_limit=0.05, assumed_probability=0, break_even_probability=0) == 1
    assert (
        b.exchange_cap(cvar_limit=0.05, assumed_probability=0.001, break_even_probability=0) == 1
    )  # tope 2,5 → se acota a todo el capital
    with pytest.raises(ValueError, match="cvar_limit"):
        b.exchange_cap(cvar_limit=0, assumed_probability=0.02, break_even_probability=0)


SAFE = np.full(1000, 0.10)  # rinde un 10 % siempre
RISKY = np.where(np.arange(1000) < 100, -1.0, 0.30)  # 10 % de quiebras, 30 % si no


def test_a_safe_strategy_takes_everything_its_exchange_allows() -> None:
    free = b.optimize_budget({"s": SAFE}, {"s": "x"}, caps={}, cvar_limit=0.05)
    assert free.weights == {"s": 1.0}
    assert free.cash == 0
    capped = b.optimize_budget({"s": SAFE}, {"s": "x"}, caps={"x": 0.3}, cvar_limit=0.05)
    assert capped.weights["s"] == pytest.approx(0.3)
    assert capped.by_exchange == {"x": pytest.approx(0.3)}
    assert capped.expected_return == pytest.approx(0.3 * 0.10 + 0.7 * 0.04)


def test_the_cvar_limit_keeps_a_tail_heavy_strategy_small() -> None:
    result = b.optimize_budget({"r": RISKY}, {"r": "x"}, caps={}, cvar_limit=0.05)
    assert result.cvar95 <= 0.05
    assert 0 < result.weights["r"] < 0.1
    loose = b.optimize_budget({"r": RISKY}, {"r": "x"}, caps={}, cvar_limit=0.5)
    assert loose.weights["r"] > result.weights["r"]


def test_a_strategy_worse_than_the_stablecoin_gets_nothing() -> None:
    poor = np.full(1000, 0.02)
    result = b.optimize_budget({"p": poor}, {"p": "x"}, caps={}, cvar_limit=0.05)
    assert result.weights == {"p": 0.0}
    assert result.cash == 1
    assert result.expected_return == pytest.approx(0.04)
    assert result.cvar95 == pytest.approx(-0.04)


def test_ties_go_to_more_cash() -> None:
    same = np.full(1000, 0.04)  # igual que la stablecoin: cualquier peso empata
    assert b.optimize_budget({"e": same}, {"e": "x"}, caps={}, cvar_limit=0.05).cash == 1


def test_two_strategies_share_the_exchange_cap() -> None:
    result = b.optimize_budget(
        {"a": SAFE, "b": SAFE * 0.9}, {"a": "x", "b": "x"}, caps={"x": 0.5}, cvar_limit=0.05
    )
    assert result.weights == {"a": pytest.approx(0.5), "b": 0.0}  # el mejor llena el tope
    assert sum(result.by_exchange.values()) == pytest.approx(0.5)


def test_optimize_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="exchange"):
        b.optimize_budget({"a": SAFE}, {}, caps={}, cvar_limit=0.05)
    with pytest.raises(ValueError, match="paso"):
        b.optimize_budget({"a": SAFE}, {"a": "x"}, caps={}, cvar_limit=0.05, step=0.3)
    with pytest.raises(ValueError, match="cvar_limit"):
        b.optimize_budget({"a": SAFE}, {"a": "x"}, caps={}, cvar_limit=0)


def test_frontier_goes_from_all_cash_to_all_in() -> None:
    rows = b.frontier({"s": SAFE}, steps=3)
    assert [r["w_estrategias"] for r in rows] == [0, 0.5, 1]
    assert rows[0]["retorno_esperado"] == pytest.approx(0.04)
    assert rows[-1]["retorno_esperado"] == pytest.approx(0.10)
