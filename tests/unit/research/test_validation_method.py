"""Método de validación para pre-registros nuevos (PQ-122), con series sintéticas."""

from __future__ import annotations

import math

import numpy as np
import pytest

from prometheus_platform.research import validation as v


def test_cpcv_selection_never_looks_at_the_test_block() -> None:
    """La columna 0 gana solo en la primera mitad y la 1 solo en la segunda: en cada partición se
    elige con el entrenamiento, así que la prueba de la elegida puede salir mala."""
    rng = np.random.default_rng(0)
    n = 600
    good = rng.normal(0.004, 0.01, n)
    bad = rng.normal(-0.004, 0.01, n)
    returns = np.column_stack(
        [
            np.concatenate([good[: n // 2], bad[n // 2 :]]),
            np.concatenate([bad[: n // 2], good[n // 2 :]]),
        ]
    )
    splits = v.cpcv_splits(n, n_groups=6, n_test_groups=2, purge=5, embargo=0.01)
    selection = v.cpcv_select_out_of_sample(returns, splits)

    for i, split in enumerate(splits):
        train_sr = [v.sharpe_daily(returns[split.train, j]) for j in range(2)]
        assert selection.chosen[i] == int(np.argmax(train_sr))
        expected = v.sharpe_daily(returns[split.test, selection.chosen[i]]) * math.sqrt(365)
        assert selection.oos_sharpe[i] == pytest.approx(expected)
    # Con un régimen que cambia, la elección en muestra falla fuera de muestra a veces.
    assert 0 < selection.share_oos_losing < 1
    assert selection.median_oos == pytest.approx(float(np.median(selection.oos_sharpe)))


def test_dsr_with_the_global_n_is_never_higher_than_with_the_family_n() -> None:
    rng = np.random.default_rng(1)
    perf = v.performance(rng.normal(0.002, 0.01, 1000))
    family, overall = v.deflated_sharpe_family_and_global(
        perf, n_family=18, n_global=107, var_sharpe=0.0013
    )
    assert overall <= family
    with pytest.raises(ValueError, match="N global"):
        v.deflated_sharpe_family_and_global(perf, n_family=20, n_global=6, var_sharpe=0.001)


def test_newey_west_matches_the_plain_t_without_autocorrelation_and_shrinks_with_it() -> None:
    rng = np.random.default_rng(2)
    iid = rng.normal(0.001, 0.01, 5000)
    plain = v.sharpe_daily(iid) * math.sqrt(iid.size)
    assert v.newey_west_t(iid) == pytest.approx(plain, rel=0.1)

    shocks = rng.normal(0.0005, 0.01, 5000)
    ar = np.empty_like(shocks)
    ar[0] = shocks[0]
    for i in range(1, ar.size):  # AR(1) con phi = 0,6: autocorrelación positiva
        ar[i] = 0.6 * ar[i - 1] + shocks[i]
    plain_ar = v.sharpe_daily(ar) * math.sqrt(ar.size)
    assert v.newey_west_t(ar, lags=20) < plain_ar
    assert v.newey_west_t(np.zeros(10)) == 0.0


def test_turnover_is_measured_against_the_capital_of_each_day() -> None:
    traded = np.full(365, 0.1)
    assert v.annual_turnover(traded, np.ones(365)) == pytest.approx(36.5)
    # Con el doble de capital, el mismo nocional es la mitad de rotación.
    assert v.annual_turnover(traded, np.full(365, 2.0)) == pytest.approx(18.25)
    with pytest.raises(ValueError, match="positivo"):
        v.annual_turnover(traded, np.zeros(365))


def test_idle_cash_uses_the_mean_invested_weight() -> None:
    returns = np.zeros(4)
    adjusted = v.idle_cash_returns(returns, mean_invested_weight=0.4, hurdle=0.04)
    assert adjusted == pytest.approx(np.full(4, 0.6 * 0.04 / 365))
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        v.idle_cash_returns(returns, mean_invested_weight=1.5, hurdle=0.04)


def test_sharpe_difference_follows_jobson_korkie_memmel() -> None:
    rng = np.random.default_rng(3)
    benchmark = rng.normal(0.0005, 0.01, 2000)
    same = v.sharpe_difference_test(benchmark, benchmark)
    assert same.z == pytest.approx(0.0)
    assert same.p_value == pytest.approx(0.5)

    strategy = benchmark + rng.normal(0.001, 0.005, 2000)
    result = v.sharpe_difference_test(strategy, benchmark)
    sr1, sr2 = v.sharpe_daily(strategy), v.sharpe_daily(benchmark)
    rho = float(np.corrcoef(strategy, benchmark)[0, 1])
    var = (2 * (1 - rho) + 0.5 * (sr1**2 + sr2**2 - 2 * sr1 * sr2 * rho**2)) / 2000
    assert result.z == pytest.approx((sr1 - sr2) / math.sqrt(var))
    assert result.z > 0
    assert 0 < result.p_value < 0.5
    with pytest.raises(ValueError, match="mismo largo"):
        v.sharpe_difference_test(strategy, benchmark[:10])
