from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from prometheus_platform.domain.protocol import HOLDOUT_END
from prometheus_platform.research import nowcast, what_if
from prometheus_platform.research.funding_model import FEATURES, TARGET
from prometheus_platform.research.simulation import WeeklyRegimeModel

RNG = np.random.default_rng(3)


def regime_sequences() -> list[np.ndarray]:
    """Tasas anualizadas con rachas de régimen alto, base y negativo, como en el desarrollo."""
    blocks = [np.full(63, 0.1095), RNG.normal(0.35, 0.05, 63), RNG.normal(-0.05, 0.02, 63)]
    return [np.concatenate([blocks[i % 3] for i in range(40)]) for _ in range(3)]


@pytest.fixture(scope="module")
def model() -> WeeklyRegimeModel:
    return what_if.fit_model(regime_sequences())


def test_scenario_validation_keeps_theta_on_the_pre_registered_grid() -> None:
    with pytest.raises(ValueError, match="pre-registrados"):
        what_if.WhatIf(1000, 1, 0.0, theta=0.25)
    with pytest.raises(ValueError, match="Horizonte"):
        what_if.WhatIf(1000, 2, 0.0)
    with pytest.raises(ValueError, match="positivo"):
        what_if.WhatIf(0, 1, 0.0)
    with pytest.raises(ValueError, match="quiebra"):
        what_if.WhatIf(1000, 1, 1.0)


def test_simulation_is_reproducible_and_scales_with_capital(
    model: WeeklyRegimeModel,
) -> None:
    small = what_if.simulate(model, what_if.WhatIf(1000, 1, 0.0), paths=300)
    again = what_if.simulate(model, what_if.WhatIf(1000, 1, 0.0), paths=300)
    big = what_if.simulate(model, what_if.WhatIf(10_000, 1, 0.0), paths=300)
    np.testing.assert_allclose(small.final_capital, again.final_capital)  # semilla fija
    assert big.median == pytest.approx(10 * small.median)
    assert small.stablecoin_capital == pytest.approx(1040.0)
    assert 0 <= small.prob_loss <= 1
    assert small.p5 <= small.median <= small.p95


def test_exchange_failure_wipes_out_the_capital_with_its_probability(
    model: WeeklyRegimeModel,
) -> None:
    safe = what_if.simulate(model, what_if.WhatIf(1000, 3, 0.0), paths=2000)
    risky = what_if.simulate(model, what_if.WhatIf(1000, 3, 0.10), paths=2000)
    assert risky.horizon_failure_probability == pytest.approx(1 - 0.9**3)
    lost = (risky.final_capital == 0).mean()
    assert lost == pytest.approx(risky.horizon_failure_probability, abs=0.03)
    assert risky.prob_loss > safe.prob_loss
    assert risky.cvar95_loss == pytest.approx(1000.0)  # el peor 5 % lo pierde todo


def test_histogram_has_counts_for_every_path() -> None:
    counts, centers = what_if.histogram(np.arange(100.0), bins=10)
    assert counts.sum() == 100
    assert centers.size == 10


def panel(start: datetime, n: int, high_every: int = 4) -> pl.DataFrame:
    """Panel sintético con las variables del cap. 5; el régimen alto se predice con `annualized`."""
    base = np.where(np.arange(n) % high_every == 0, 0.40, 0.05)
    data = {name: base + RNG.normal(0, 0.01, n) for name in FEATURES}
    data["funding_interval_hours"] = np.full(n, 8.0)
    data[TARGET] = base + RNG.normal(0, 0.01, n)
    times = [start + timedelta(hours=8 * i) for i in range(n)]
    return pl.DataFrame(data).with_columns(pl.Series("funding_time", times))


def trained() -> nowcast.TrainedModel:
    return nowcast.train(panel(datetime(2021, 1, 1, tzinfo=UTC), 600), {"max_depth": 4})


def test_forecast_refuses_data_that_does_not_go_past_the_holdout() -> None:
    stale = panel(HOLDOUT_END - timedelta(days=3), 5).with_columns(
        pl.lit("SOLUSDT").alias("symbol")
    )
    with pytest.raises(nowcast.StaleDataError, match="holdout"):
        nowcast.forecast(trained(), stale)


def test_forecast_predicts_only_fresh_rows_with_explanations() -> None:
    fresh = pl.concat(
        [
            panel(datetime(2026, 11, 6, tzinfo=UTC), 1, high_every=1).with_columns(
                pl.lit("SOLUSDT").alias("symbol")
            ),
            panel(datetime(2026, 11, 6, tzinfo=UTC), 2, high_every=99)
            .tail(1)
            .with_columns(pl.lit("BTCUSDT").alias("symbol")),
            panel(HOLDOUT_END - timedelta(days=1), 1).with_columns(
                pl.lit("XRPUSDT").alias("symbol")
            ),
        ]
    )
    result = nowcast.forecast(trained(), fresh)
    by_symbol = {r.symbol: r for r in result.rows}
    assert set(by_symbol) == {"SOLUSDT", "BTCUSDT"}  # XRP tiene un dato viejo: no se predice
    assert by_symbol["SOLUSDT"].probability_high > 0.5
    assert by_symbol["SOLUSDT"].regime.startswith("alto")
    assert by_symbol["BTCUSDT"].probability_high < 0.5
    assert len(result.importance) == len(FEATURES)
    assert result.params == {"max_depth": 4}
    assert set(result.explanations) == {"SOLUSDT", "BTCUSDT"}  # PQ-74: una por predicción
    assert len(result.explanations["SOLUSDT"]) == len(FEATURES)


def test_tuned_params_come_from_the_study_artifact(tmp_path: Path) -> None:
    path = tmp_path / "research" / "funding_model" / "residual" / "summary.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"classification": [{"name": "random_forest", "tuned": true,'
        ' "best_params": {"max_depth": 4, "min_samples_leaf": 20}}]}',
        encoding="utf-8",
    )
    assert nowcast.tuned_params(tmp_path) == {"max_depth": 4, "min_samples_leaf": 20}
    path.write_text('{"classification": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="ajustado"):
        nowcast.tuned_params(tmp_path)
