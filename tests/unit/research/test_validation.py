import math

import numpy as np
import pytest

from prometheus_platform.research.validation import (
    cpcv_splits,
    cpcv_test_sharpes,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    performance,
    probability_of_backtest_overfitting,
    sharpe_daily,
)

RNG = np.random.default_rng(7)


def test_performance_metrics_on_a_known_series() -> None:
    returns = np.array([0.01, -0.005, 0.02, -0.01, 0.0])
    perf = performance(returns)
    expected_sr = returns.mean() / returns.std(ddof=1)
    assert perf.sharpe_daily == pytest.approx(expected_sr)
    assert perf.sharpe == pytest.approx(expected_sr * math.sqrt(365))
    assert perf.t_stat == pytest.approx(expected_sr * math.sqrt(5))
    assert perf.max_drawdown == pytest.approx(
        (1.01 * 0.995 * 1.02 * 0.99) / (1.01 * 0.995 * 1.02) - 1
    )
    assert perf.days == 5
    with pytest.raises(ValueError, match="al menos 2"):
        performance(np.array([0.01]))


def test_sharpe_of_a_flat_series_is_zero() -> None:
    assert sharpe_daily(np.zeros(10)) == 0.0
    assert performance(np.full(10, 0.001)).kurtosis == 3.0


def test_cpcv_has_15_splits_and_purges_around_test_blocks() -> None:
    splits = cpcv_splits(600, n_groups=6, n_test_groups=2, purge=8, embargo=0.01)
    assert len(splits) == 15
    for split in splits:
        assert not set(split.train) & set(split.test)
        for t in split.test:
            # Ninguna observación de entrenamiento a menos de `purge` de una de prueba.
            assert np.min(np.abs(split.train - t)) > 8 or t in (0, 599)
    # Cada grupo aparece en 5 particiones como prueba (5 caminos).
    counts = np.bincount([g for s in splits for g in s.test_groups])
    assert counts.tolist() == [5] * 6


def test_cpcv_test_sharpes_shape() -> None:
    returns = RNG.normal(0, 0.01, size=(300, 3))
    out = cpcv_test_sharpes(returns, cpcv_splits(300))
    assert out.shape == (15, 3)


def test_pbo_is_low_when_one_config_truly_dominates() -> None:
    noise = RNG.normal(0, 0.01, size=(800, 5))
    noise[:, 2] += 0.004  # una configuración con ventaja real
    assert probability_of_backtest_overfitting(noise, n_blocks=8) < 0.1


def test_pbo_is_high_when_everything_is_noise() -> None:
    pbo = probability_of_backtest_overfitting(RNG.normal(0, 0.01, size=(800, 9)), n_blocks=8)
    assert 0.2 < pbo < 0.9
    with pytest.raises(ValueError, match="par"):
        probability_of_backtest_overfitting(np.zeros((10, 2)), n_blocks=5)


def test_expected_max_sharpe_grows_with_the_number_of_trials() -> None:
    assert expected_max_sharpe(1, 0.01) == 0.0
    assert expected_max_sharpe(10, 0.01) < expected_max_sharpe(100, 0.01)


def test_deflated_sharpe_matches_the_formula() -> None:
    sr, n, skew, kurt, trials, var = 0.08, 1000, -0.5, 6.0, 20, 0.0004
    sr0 = expected_max_sharpe(trials, var)
    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
    expected = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    got = deflated_sharpe_ratio(
        sr, n_obs=n, skew=skew, kurtosis=kurt, n_trials=trials, var_sharpe=var
    )
    assert got == pytest.approx(expected)


def test_more_trials_deflate_the_sharpe() -> None:
    def dsr(n_trials: int) -> float:
        return deflated_sharpe_ratio(
            0.06, n_obs=1000, skew=0.0, kurtosis=3.0, n_trials=n_trials, var_sharpe=0.001
        )

    assert dsr(2) > dsr(200)
