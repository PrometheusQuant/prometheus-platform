from pathlib import Path

import numpy as np
import polars as pl
import pytest

from prometheus_platform.research.eda import (
    FEATURES,
    correlation_matrix,
    describe_table,
    plot_correlation,
)


def panel() -> pl.DataFrame:
    rng = np.random.default_rng(1)
    base = rng.normal(0.1, 0.05, 200)
    data = {name: base + rng.normal(0, 0.01 * (i + 1), 200) for i, name in enumerate(FEATURES)}
    return pl.DataFrame(data)


def test_describe_has_one_row_per_feature() -> None:
    table = describe_table(panel())
    assert table["variable"].to_list() == list(FEATURES)
    assert (table["n"] == 200).all()
    assert (table["min"] <= table["mediana"]).all()


def test_correlation_is_symmetric_with_unit_diagonal(tmp_path: Path) -> None:
    corr = correlation_matrix(panel()).to_numpy()
    assert corr.shape == (len(FEATURES), len(FEATURES))
    assert np.diag(corr) == pytest.approx(1.0)
    assert corr == pytest.approx(corr.T)
    assert plot_correlation(correlation_matrix(panel()), tmp_path / "c.png").stat().st_size > 10_000
