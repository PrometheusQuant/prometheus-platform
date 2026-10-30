"""Capa gold: panel horario de precios y panel de features por liquidación de funding.

Todo es *point-in-time*: una feature en la liquidación ``t`` solo usa velas que cerraron en o
antes de ``t`` y liquidaciones con ``knowledge_time <= t``. Los joins se hacen con ``asof_join``
de silver sobre ``knowledge_time``.

- ``hourly_prices``: una fila por hora con apertura y cierre de spot y perpetuo (sin rellenar).
- ``settlement_features``: una fila por liquidación con el funding, las medias ``S_k`` de la
  señal del pre-registro, la basis, la volatilidad y los rezagos; y el objetivo del modelo
  predictivo (``target_next_annualized``), que es lo único que mira al futuro y no se usa como
  feature.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from prometheus_platform.data_platform.silver import asof_join, silver_path
from prometheus_platform.domain.datasets import DatasetKind, Market

SIGNAL_WINDOWS = (3, 9, 21)  # k pre-declarados (pre-registro, sección 5)
HOURS_PER_YEAR = 8760
DEV_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)  # fin del periodo de desarrollo
HOLDOUT_START = datetime(2024, 7, 1, tzinfo=UTC)


def load_silver(silver_root: Path, symbol: str) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    spot = pl.read_parquet(silver_path(silver_root, DatasetKind.KLINES, symbol, Market.SPOT, "1h"))
    perp = pl.read_parquet(silver_path(silver_root, DatasetKind.KLINES, symbol, Market.USDM, "1h"))
    funding = pl.read_parquet(silver_path(silver_root, DatasetKind.FUNDING_RATE, symbol))
    return spot, perp, funding


def hourly_prices(spot: pl.DataFrame, perp: pl.DataFrame) -> pl.DataFrame:
    """Une spot y perp por hora. Una hora sin vela en una pata queda nula (no se imputa)."""
    legs = [
        frame.select(
            "open_time",
            pl.col("open").alias(f"{name}_open"),
            pl.col("close").alias(f"{name}_close"),
        )
        for name, frame in (("spot", spot), ("perp", perp))
    ]
    return legs[0].join(legs[1], on="open_time", how="full", coalesce=True).sort("open_time")


def settlement_features(funding: pl.DataFrame, hourly: pl.DataFrame) -> pl.DataFrame:
    """Panel por liquidación con features point-in-time y el objetivo a un paso."""
    rates = funding.sort("funding_time").select(
        "funding_time",
        "knowledge_time",
        "funding_interval_hours",
        "funding_rate",
        pl.col("funding_rate_annualized").alias("annualized"),
    )
    rates = rates.with_columns(
        *[pl.col("annualized").rolling_mean(window_size=k).alias(f"s_{k}") for k in SIGNAL_WINDOWS],
        *[pl.col("annualized").shift(lag).alias(f"annualized_lag{lag}") for lag in (1, 2, 3)],
        pl.col("annualized").rolling_std(window_size=21).alias("annualized_std_21"),
        # Objetivo del modelo: el funding de la siguiente liquidación. Nunca es una feature.
        pl.col("annualized").shift(-1).alias("target_next_annualized"),
        pl.col("funding_time").shift(-1).alias("next_funding_time"),
    )

    # Precios de la vela que *cierra* en t: su knowledge_time es open_time + 1 h.
    bars = (
        hourly.with_columns(
            (pl.col("open_time") + pl.duration(hours=1))
            .dt.cast_time_unit("ms")
            .alias("knowledge_time"),
            (pl.col("spot_close") / pl.col("spot_close").shift(1)).log().alias("spot_log_return"),
        )
        .with_columns(
            (pl.col("perp_close") / pl.col("spot_close") - 1).alias("basis"),
            (pl.col("spot_close") / pl.col("spot_close").shift(24) - 1).alias("spot_return_24h"),
            (
                pl.col("spot_log_return").rolling_std(window_size=168, min_samples=48)
                * HOURS_PER_YEAR**0.5
            ).alias("spot_vol_7d"),
        )
        .select(
            "knowledge_time", "spot_close", "perp_close", "basis", "spot_return_24h", "spot_vol_7d"
        )
    )
    panel = asof_join(rates.drop("knowledge_time"), bars, on="funding_time", suffix="_bar")
    return panel.with_columns(
        (pl.col("basis") - pl.col("basis").shift(3)).alias("basis_change_3"),
        pl.col("funding_time").alias("knowledge_time"),
    )


def development_only(frame: pl.DataFrame, column: str = "funding_time") -> pl.DataFrame:
    """Recorta al periodo de desarrollo: el holdout del pre-registro no se mira aquí.

    En el panel de liquidaciones también anula el objetivo de la última fila si la siguiente
    liquidación cae ya en el holdout, para que ni una sola tasa del holdout entre en el modelo.
    """
    dev = frame.filter(pl.col(column) <= DEV_END)
    if "next_funding_time" in dev.columns:
        dev = dev.with_columns(
            pl.when(pl.col("next_funding_time") <= DEV_END)
            .then(pl.col("target_next_annualized"))
            .otherwise(None)
            .alias("target_next_annualized")
        )
    return dev
