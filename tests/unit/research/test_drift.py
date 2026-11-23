"""Estadísticos de drift (PQ-86): PSI, KS y calibración del clasificador."""

from __future__ import annotations

import numpy as np
import pytest

from prometheus_platform.research.drift import (
    PSI_ALERT,
    calibration,
    data_drift,
    population_stability,
)

RNG = np.random.default_rng(7)


def test_psi_is_zero_for_the_same_distribution() -> None:
    sample = RNG.normal(size=5_000)
    assert population_stability(sample, sample) == pytest.approx(0.0, abs=1e-9)


def test_psi_grows_with_the_shift_and_crosses_the_alert_threshold() -> None:
    reference = RNG.normal(size=5_000)
    small = population_stability(reference, RNG.normal(0.1, 1, size=2_000))
    large = population_stability(reference, RNG.normal(1.5, 1, size=2_000))

    assert small < 0.1 < PSI_ALERT < large


def test_psi_survives_empty_bins_in_the_live_sample() -> None:
    reference = np.arange(1_000, dtype=float)
    live = np.full(50, 10.0)  # todo en el primer decil
    assert np.isfinite(population_stability(reference, live))


def test_data_drift_reports_psi_ks_and_the_verdict() -> None:
    reference = RNG.normal(size=3_000)
    same = data_drift("SOLUSDT", reference, RNG.normal(size=300))
    moved = data_drift("SOLUSDT", reference, RNG.normal(2, 1, size=300))

    assert not same.alert
    assert moved.alert
    assert moved.ks_pvalue < 0.01
    assert moved.live_median > moved.reference_median
    assert (moved.n_reference, moved.n_live) == (3_000, 300)


def test_data_drift_needs_a_minimum_live_sample() -> None:
    with pytest.raises(ValueError, match="al menos"):
        data_drift("SOLUSDT", RNG.normal(size=100), RNG.normal(size=5))


def test_a_calibrated_model_has_low_ece() -> None:
    probs = RNG.uniform(size=20_000)
    labels = RNG.uniform(size=20_000) < probs  # ocurre con la probabilidad dicha

    result = calibration(labels, probs)

    assert result.ece < 0.02
    assert result.brier == pytest.approx(1 / 6, abs=0.01)  # E[p(1-p)] con p uniforme
    assert not result.alert


def test_an_overconfident_model_crosses_the_ece_threshold() -> None:
    labels = RNG.uniform(size=5_000) < 0.5
    probs = np.where(RNG.uniform(size=5_000) < 0.5, 0.95, 0.05)  # sin relación con el resultado

    result = calibration(labels, probs)

    assert result.ece > 0.4
    assert result.alert
    assert result.positive_rate == pytest.approx(0.5, abs=0.03)
    assert len(result.bins) == 2  # solo los tramos con predicciones


def test_calibration_with_a_single_class_has_no_auc() -> None:
    result = calibration(np.zeros(50, dtype=bool), np.full(50, 0.1))
    assert result.auc is None
    assert result.ece == pytest.approx(0.1)
