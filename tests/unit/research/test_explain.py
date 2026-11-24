"""Explicabilidad del clasificador del capítulo 5 (PQ-74)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
import pytest
from sklearn.model_selection import TimeSeriesSplit

from prometheus_platform.research import explain, nowcast
from prometheus_platform.research.funding_model import FEATURES, TARGET

RNG = np.random.default_rng(7)


def driven_panel(n: int = 900) -> pl.DataFrame:
    """Solo `annualized` decide el régimen; el resto de variables es ruido."""
    high = RNG.random(n) < 0.3
    data: dict[str, Any] = {name: RNG.normal(0.1, 0.05, n) for name in FEATURES}
    data["annualized"] = np.where(high, 0.45, 0.05) + RNG.normal(0, 0.02, n)
    data["funding_interval_hours"] = np.full(n, 8.0)
    data[TARGET] = np.where(high, 0.40, 0.05)
    times = [datetime(2021, 1, 1, tzinfo=UTC) + timedelta(hours=8 * i) for i in range(n)]
    return pl.DataFrame(data).with_columns(pl.Series("funding_time", times))


def test_validation_importance_finds_the_real_driver() -> None:
    ranked = explain.validation_importance(driven_panel(), {"max_depth": 4}, n_repeats=3)

    assert ranked[0].feature == "annualized"
    assert ranked[0].mean > 0.1  # barajarla hunde el AUC fuera de muestra
    assert all(abs(imp.mean) < 0.05 for imp in ranked[1:])  # el ruido no aporta
    assert ranked[0].label == "funding actual (anualizado)"


def test_importance_is_measured_only_on_validation_folds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Criterio de PQ-74: nunca sobre el entrenamiento."""
    seen: list[int] = []
    real = explain.permutation_importance  # type: ignore[attr-defined]

    def spy(model: Any, x: np.ndarray, y: np.ndarray, **kwargs: Any) -> Any:
        seen.append(len(x))
        return real(model, x, y, **kwargs)

    monkeypatch.setattr(explain, "permutation_importance", spy)
    panel = driven_panel(600)
    explain.validation_importance(panel, {"max_depth": 3}, n_repeats=2)

    expected = [len(test) for _, test in TimeSeriesSplit(n_splits=5, gap=15).split(np.arange(600))]
    assert seen == expected


def test_local_contributions_point_at_what_moves_todays_prediction() -> None:
    trained = nowcast.train(driven_panel(), {"max_depth": 4})
    row = trained.reference.copy()
    row[FEATURES.index("annualized")] = 0.45  # hoy, funding muy alto

    contributions = explain.local_contributions(trained.model, row, trained.reference)

    assert contributions[0].feature == "annualized"
    assert contributions[0].delta > 0.5  # con un valor típico, la probabilidad se desplomaría
    text = explain.explain_in_words("SOLUSDT", 0.9, contributions)
    assert text.startswith("SOLUSDT: probabilidad de funding alto del 90 %")
    assert "«funding actual (anualizado)»" in text
    assert "bajaría" in text


def test_typical_day_has_nothing_to_explain() -> None:
    trained = nowcast.train(driven_panel(), {"max_depth": 4})
    contributions = explain.local_contributions(trained.model, trained.reference, trained.reference)

    assert all(abs(c.delta) < 1e-9 for c in contributions)  # el bosque suma en paralelo: ruido
    assert "Ninguna variable" in explain.explain_in_words("BNBUSDT", 0.05, contributions)


def test_folds_without_both_classes_are_reported() -> None:
    flat = driven_panel(300).with_columns(pl.lit(0.05).alias(TARGET))
    with pytest.raises(ValueError, match="dos clases"):
        explain.validation_importance(flat, {"max_depth": 3}, n_repeats=1)
