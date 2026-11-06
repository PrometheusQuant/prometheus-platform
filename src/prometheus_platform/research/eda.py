"""Análisis exploratorio de las features (PQ-31, cap. 4.3), solo con el periodo de desarrollo."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

FEATURES = (
    "annualized",
    "s_3",
    "s_9",
    "s_21",
    "annualized_lag1",
    "annualized_std_21",
    "basis",
    "basis_change_3",
    "spot_return_24h",
    "spot_vol_7d",
    "target_next_annualized",
)


def describe_table(panel: pl.DataFrame) -> pl.DataFrame:
    """Estadística descriptiva por variable: n, media, desviación y cuantiles."""
    rows = []
    for name in FEATURES:
        s = panel[name].drop_nulls().cast(pl.Float64)
        rows.append(
            {
                "variable": name,
                "n": s.len(),
                "media": s.mean(),
                "desv": s.std(),
                "min": s.min(),
                "p25": s.quantile(0.25),
                "mediana": s.median(),
                "p75": s.quantile(0.75),
                "max": s.max(),
            }
        )
    return pl.DataFrame(rows)


def correlation_matrix(panel: pl.DataFrame) -> pl.DataFrame:
    """Correlaciones de Spearman (robustas a colas pesadas) entre features y objetivo."""
    clean = panel.select(FEATURES).drop_nulls()
    ranks = clean.select([pl.col(c).rank() for c in FEATURES])
    return ranks.corr()


def plot_correlation(corr: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = corr.to_numpy()
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    image = ax.imshow(values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(FEATURES)), FEATURES, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(FEATURES)), FEATURES, fontsize=8)
    for i, j in np.ndindex(values.shape):
        ax.text(j, i, f"{values[i, j]:.2f}", ha="center", va="center", fontsize=6)
    fig.colorbar(image, shrink=0.8, label="Spearman")
    ax.set_title("Correlación de las features (desarrollo, 5 símbolos)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
