"""PQ-123: ¿el funding bajo desde octubre de 2026 es un régimen temporal o estructural?

Describe el funding anualizado de los cinco símbolos del carry por semestre, desde el silver: la
mediana y la parte de las liquidaciones por encima de θ = 20 % (el umbral de entrada de H2) y por
debajo de 0. **Es descriptivo:** no evalúa ninguna regla y no es un ensayo. El holdout del carry ya
se abrió (PQ-50), así que cualquier variante que se diseñe después de ver esto solo puede validarse
con datos futuros.

Uso:
    uv run python scripts/pdca_regimen_funding.py --out regimen-funding.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import polars as pl

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
THETA = 0.20


def regime(silver: Path) -> pl.DataFrame:
    frames = []
    for symbol in SYMBOLS:
        f = pl.read_parquet(silver / "funding" / f"{symbol}.parquet")
        frames.append(
            f.select(
                pl.lit(symbol).alias("symbol"),
                pl.col("funding_time"),
                pl.col("funding_rate_annualized").alias("anual"),
            )
        )
    data = pl.concat(frames)
    half = pl.col("funding_time").dt.year().cast(pl.String) + pl.when(
        pl.col("funding_time").dt.month() <= 6
    ).then(pl.lit("-S1")).otherwise(pl.lit("-S2"))
    return (
        data.with_columns(half.alias("semestre"))
        .group_by("symbol", "semestre")
        .agg(
            pl.col("anual").median().alias("mediana"),
            (pl.col("anual") > THETA).mean().alias("sobre_theta"),
            (pl.col("anual") < 0).mean().alias("negativas"),
            pl.len().alias("liquidaciones"),
        )
        .sort("semestre", "symbol")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="regimen-funding.json")
    args = parser.parse_args()
    silver = Path(os.environ.get("PQ_DATA_DIR", "data")) / "silver"
    table = regime(silver)
    Path(args.out).write_text(json.dumps(table.to_dicts(), indent=1, default=str), encoding="utf-8")
    with pl.Config(tbl_rows=200, tbl_cols=10):
        print(table)


if __name__ == "__main__":
    main()
