from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from prometheus_platform.research.funding_model import (
    FEATURES,
    TARGET,
    ModelSpec,
    classification_specs,
    diebold_mariano,
    prepare,
    regression_specs,
    run_study,
)


def ar_panel(n: int = 900) -> pl.DataFrame:
    """Funding AR(1) sintético: la persistencia es buena pero mejorable con la basis."""
    rng = np.random.default_rng(0)
    rate = np.zeros(n)
    basis = rng.normal(0, 0.1, n)
    for t in range(1, n):
        rate[t] = 0.8 * rate[t - 1] + 0.5 * basis[t - 1] + rng.normal(0, 0.05)
    data: dict[str, object] = {name: rng.normal(0, 1, n) for name in FEATURES}
    data["annualized"] = rate
    data["basis"] = basis
    data["s_9"] = pl.Series(rate).rolling_mean(9).fill_null(0.0).to_numpy()
    data["funding_interval_hours"] = np.full(n, 8.0)
    data[TARGET] = np.append(rate[1:], np.nan)
    data["funding_time"] = [
        datetime(2022, 1, 1, tzinfo=UTC) + timedelta(hours=8 * i) for i in range(n)
    ]
    return pl.DataFrame(data).with_columns(pl.col(TARGET).fill_nan(None))


def small(specs: list[ModelSpec]) -> list[ModelSpec]:
    """Una rejilla mínima para que el test sea rápido."""
    return [
        ModelSpec(s.name, s.factory, {k: v[:1] for k, v in s.grid.items()}, s.justification)
        for s in specs[:2]
    ]


def test_prepare_drops_incomplete_rows_and_sorts_by_time() -> None:
    x, y, clean = prepare(ar_panel(50).reverse())
    assert x.shape == (49, len(FEATURES))
    assert y.size == 49
    assert clean["funding_time"].is_sorted()


@pytest.mark.parametrize("mode", ["level", "residual"])
def test_study_compares_models_against_baselines(mode: str) -> None:
    study = run_study(
        ar_panel(), n_folds=3, gap=2, regression=small(regression_specs()),
        classification=small(classification_specs()), target_mode=mode,
    )  # fmt: skip
    names = {r.name for r in study.regression}
    assert {"persistencia", "media_s9", "ridge", "random_forest"} <= names
    assert any(r.tuned for r in study.regression)
    assert {c.name for c in study.classification} >= {"regla_s9", "logistic"}
    assert study.diebold_mariano["target_mode"] == mode
    for c in study.classification:
        assert sum(map(sum, c.confusion)) == sum(map(sum, study.classification[0].confusion))
    assert study.roc_points


def test_residual_ridge_beats_persistence_when_basis_predicts() -> None:
    study = run_study(
        ar_panel(), n_folds=3, gap=2, regression=small(regression_specs())[:1],
        classification=small(classification_specs())[:1], target_mode="residual",
    )  # fmt: skip
    rmse = {(r.name, r.tuned): r.rmse for r in study.regression}
    assert rmse[("ridge", True)] < rmse[("persistencia", False)]


def test_default_and_tuned_ridge_are_close_in_residual_mode() -> None:
    # Regresión de un error real: los modelos por defecto no sumaban la tasa actual al residuo.
    study = run_study(
        ar_panel(), n_folds=3, gap=2, regression=small(regression_specs())[:1],
        classification=small(classification_specs())[:1], target_mode="residual",
    )  # fmt: skip
    r2 = {(r.name, r.tuned): r.r2 for r in study.regression}
    assert r2[("ridge", False)] == pytest.approx(r2[("ridge", True)], abs=0.05)


def test_invalid_target_mode() -> None:
    with pytest.raises(ValueError, match="target_mode"):
        run_study(ar_panel(60), target_mode="otro")


def test_diebold_mariano_sign() -> None:
    rng = np.random.default_rng(3)
    better, worse = rng.normal(0, 0.5, 500), rng.normal(0, 1.0, 500)
    result = diebold_mariano(better, worse)
    assert float(result["dm"]) < 0
    assert float(result["p_value"]) < 0.01
