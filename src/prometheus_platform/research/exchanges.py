"""Funding de Binance frente a Bybit y OKX: comparación descriptiva (PQ-79).

**Solo el periodo de desarrollo** (antes de ``HOLDOUT_START``) y **sin evaluar estrategias**: eso
exige su propio pre-registro (H4, PQ-94). Para cada símbolo y exchange, en las liquidaciones que
coinciden con las de Binance:

- nivel medio y mediano anualizado de cada uno, y la diferencia media (la mediana importa: un
  episodio extremo como el de SOL en noviembre de 2022 arrastra la media);
- % de liquidaciones positivas;
- correlación de las tasas;
- % de liquidaciones en que el otro exchange paga más que Binance.

Un exchange sin datos del desarrollo (OKX solo guarda unos 3 meses por API) se informa como tal, no
se rellena.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from prometheus_platform.data_platform.silver import silver_path
from prometheus_platform.domain.datasets import DatasetKind
from prometheus_platform.domain.protocol import HOLDOUT_START

EXCHANGES = ("bybit", "okx")


def _development(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    frame = pl.read_parquet(path, columns=["funding_time", "funding_rate_annualized"])
    return frame.filter(pl.col("funding_time") < HOLDOUT_START)


def compare_symbol(silver: Path, symbol: str, exchange: str) -> dict[str, Any]:
    binance = _development(silver_path(silver, DatasetKind.FUNDING_RATE, symbol))
    other = _development(silver_path(silver, DatasetKind.FUNDING_RATE, symbol, exchange=exchange))
    base: dict[str, Any] = {"simbolo": symbol, "exchange": exchange}
    if binance.is_empty() or other.is_empty():
        return {**base, "liquidaciones_comunes": 0, "nota": "sin datos del desarrollo"}
    joined = binance.rename({"funding_rate_annualized": "binance"}).join(
        other.rename({"funding_rate_annualized": "otro"}), on="funding_time", how="inner"
    )
    if joined.height < 2:
        return {**base, "liquidaciones_comunes": joined.height, "nota": "casi sin solapamiento"}
    corr = joined.select(pl.corr("binance", "otro")).item()
    return {
        **base,
        "liquidaciones_comunes": joined.height,
        "desde": str(joined["funding_time"].min()),
        "hasta": str(joined["funding_time"].max()),
        "media_binance": float(joined["binance"].mean()),  # type: ignore[arg-type]
        "media_otro": float(joined["otro"].mean()),  # type: ignore[arg-type]
        # La mediana, porque episodios extremos (SOL en nov-2022: -2 % cada 2 h) arrastran la media.
        "mediana_binance": float(joined["binance"].median()),  # type: ignore[arg-type]
        "mediana_otro": float(joined["otro"].median()),  # type: ignore[arg-type]
        "diferencia_media": float((joined["otro"] - joined["binance"]).mean()),  # type: ignore[arg-type]
        "positivas_binance": float((joined["binance"] > 0).mean()),  # type: ignore[arg-type]
        "positivas_otro": float((joined["otro"] > 0).mean()),  # type: ignore[arg-type]
        "correlacion": None if corr is None else float(corr),
        "otro_paga_mas": float((joined["otro"] > joined["binance"]).mean()),  # type: ignore[arg-type]
    }


def compare(
    silver: Path, symbols: Sequence[str], exchanges: Sequence[str] = EXCHANGES
) -> list[dict[str, Any]]:
    return [compare_symbol(silver, s, e) for s in symbols for e in exchanges]
