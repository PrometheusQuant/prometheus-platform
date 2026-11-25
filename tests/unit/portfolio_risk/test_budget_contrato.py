"""Contrato del presupuesto (PQ-121): lo que los mutantes de ``budget.py`` dejaban sin probar.

``cvar_contributions`` y ``bootstrap_bands`` solo se probaban desde el dashboard y la CLI, que
mutmut no cuenta. Estos tests fijan su contrato con valores calculables a mano.
"""

from __future__ import annotations

import numpy as np
import pytest

from prometheus_platform.portfolio_risk import budget as b


def test_contributions_add_up_to_the_portfolio_cvar() -> None:
    rng = np.random.default_rng(7)
    scenarios = {"a": rng.normal(0.05, 0.20, 4000), "b": rng.normal(0.02, 0.05, 4000)}
    weights = {"a": 0.3, "b": 0.4}
    parts = b.cvar_contributions(scenarios, weights, hurdle=0.04)
    portfolio = 0.3 * scenarios["a"] + 0.4 * scenarios["b"] + 0.3 * 0.04
    assert sum(parts.values()) == pytest.approx(b.cvar95(portfolio), rel=1e-12)
    assert list(parts) == ["a", "b", "efectivo"]  # orden estable: nombres y luego el efectivo


def test_cash_contributes_minus_its_yield_in_every_scenario() -> None:
    scenarios = {"a": np.array([-0.5, 0.1, 0.2, 0.3] * 25)}
    parts = b.cvar_contributions(scenarios, {"a": 0.25}, hurdle=0.04)
    assert parts["efectivo"] == pytest.approx(-0.75 * 0.04)  # gana el 4 % aun en la cola
    assert parts["a"] == pytest.approx(0.25 * 0.5)  # la cola es el -50 %, ponderado
    default = b.cvar_contributions(scenarios, {"a": 0.25})
    assert default["efectivo"] == pytest.approx(-0.75 * b.HURDLE)


def test_a_zero_weight_contributes_nothing() -> None:
    scenarios = {"a": np.linspace(-1, 1, 100), "b": np.linspace(1, -1, 100)}
    parts = b.cvar_contributions(scenarios, {"a": 0.0, "b": 0.5}, hurdle=0.0)
    assert parts["a"] == pytest.approx(0.0)
    assert parts["efectivo"] == pytest.approx(0.0)


def test_the_tail_includes_the_quantile_itself() -> None:
    """Con 20 escenarios, el cuantil del 5 % es el peor: la cola es solo ese escenario."""
    values = np.arange(20, dtype=np.float64) / 100 - 0.05  # de -0,05 a 0,14
    parts = b.cvar_contributions({"a": values}, {"a": 1.0}, hurdle=0.0)
    assert parts["a"] == pytest.approx(0.05)


def test_bands_compound_a_constant_return_exactly() -> None:
    daily = np.full(b.BLOCK_DAYS, 0.01)
    bands = b.bootstrap_bands(daily, 30, n_paths=50)
    assert bands.shape == (3, 30)  # 5 %, mediana y 95 %, por día
    expected = 1.01 ** np.arange(1, 31)
    for row in bands:
        assert row == pytest.approx(expected)


def test_bands_are_ordered_deterministic_and_respect_the_quantiles() -> None:
    rng = np.random.default_rng(3)
    daily = rng.normal(0.0005, 0.02, 400)
    bands = b.bootstrap_bands(daily, 45, n_paths=300, seed=11)
    assert np.all(bands[0] <= bands[1])
    assert np.all(bands[1] <= bands[2])
    assert np.array_equal(bands, b.bootstrap_bands(daily, 45, n_paths=300, seed=11))
    assert not np.array_equal(bands, b.bootstrap_bands(daily, 45, n_paths=300, seed=12))
    two = b.bootstrap_bands(daily, 45, n_paths=300, seed=11, quantiles=(0.25, 0.75))
    assert two.shape == (2, 45)
    assert np.all(two[0] <= two[1])


def test_bands_cover_horizons_that_are_not_a_multiple_of_the_block() -> None:
    daily = np.full(30, 0.002)
    bands = b.bootstrap_bands(daily, b.BLOCK_DAYS + 1, n_paths=10, block=b.BLOCK_DAYS)
    assert bands.shape[1] == b.BLOCK_DAYS + 1
    assert bands[1, -1] == pytest.approx(1.002 ** (b.BLOCK_DAYS + 1))
    one = b.bootstrap_bands(daily, 1, n_paths=10, block=5)
    assert one[1, 0] == pytest.approx(1.002)


def test_bands_use_contiguous_blocks_of_history() -> None:
    """Con una historia de exactamente un bloque, todas las trayectorias son esa historia."""
    daily = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
    bands = b.bootstrap_bands(daily, 5, n_paths=20, block=5)
    expected = np.cumprod(1 + daily)
    for row in bands:
        assert row == pytest.approx(expected)


@pytest.mark.parametrize(
    ("daily", "horizon", "message"),
    [(np.full(30, 0.01), 0, "al menos un día"), (np.full(10, 0.01), 5, "días de historia")],
)
def test_bands_reject_bad_inputs(daily: np.ndarray, horizon: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        b.bootstrap_bands(daily, horizon, block=b.BLOCK_DAYS)


def test_optimizer_respects_the_cvar_limit_exactly_at_the_border() -> None:
    """Una asignación con CVaR justo en el límite es válida; un poco más, no."""
    scenarios = {"a": np.array([-0.40] * 5 + [0.30] * 95)}
    # Con w = 0,25 el CVaR es 0,25 · 0,40 - 0,75 · 0,04 = 0,07.
    at_border = b.optimize_budget(scenarios, {"a": "x"}, caps={"x": 1.0}, cvar_limit=0.07)
    assert at_border.weights["a"] == pytest.approx(0.25)
    below = b.optimize_budget(scenarios, {"a": "x"}, caps={"x": 1.0}, cvar_limit=0.0699)
    assert below.weights["a"] == pytest.approx(0.20)


def test_optimizer_reports_its_numbers() -> None:
    scenarios = {"a": np.array([0.10] * 100)}
    best = b.optimize_budget(scenarios, {"a": "x"}, caps={"x": 0.5}, cvar_limit=0.5)
    assert best.weights == {"a": pytest.approx(0.5)}
    assert best.cash == pytest.approx(0.5)
    assert best.expected_return == pytest.approx(0.5 * 0.10 + 0.5 * 0.04)
    assert best.cvar95 == pytest.approx(-(0.5 * 0.10 + 0.5 * 0.04))
    assert best.by_exchange == {"x": pytest.approx(0.5)}
