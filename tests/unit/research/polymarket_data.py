"""Datos sintéticos de Polymarket con el silver de PQ-92, compartidos por los tests de PQ-93."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import polars as pl

from prometheus_platform.data_platform.polymarket import build_markets, build_prices

D0 = datetime(2024, 3, 1, tzinfo=UTC)


def raw_market(  # noqa: PLR0913 - un mercado de Gamma con lo justo para cada caso
    mid: str,
    *,
    closed: datetime | None = D0 + timedelta(days=10),
    payouts: str = '["1", "0"]',
    tags: tuple[str, ...] = ("Politics",),
    fee_type: str | None = None,
    volume: float = 5000.0,
    event: str | None = None,
    outcomes: str = '["Yes", "No"]',
) -> dict[str, Any]:
    return {
        "id": mid,
        "conditionId": f"0x{mid}",
        "outcomes": outcomes,
        "outcomePrices": payouts,
        "clobTokenIds": json.dumps([f"{mid}a", f"{mid}b"]),
        "endDate": (closed or D0 + timedelta(days=10)).isoformat(),
        "closedTime": closed.strftime("%Y-%m-%d %H:%M:%S+00") if closed else None,
        "volumeNum": volume,
        "feeType": fee_type,
        "tags": [{"label": t} for t in tags],
        "events": [{"id": event or f"ev{mid}"}],
    }


def silver_markets(*rows: dict[str, Any]) -> pl.DataFrame:
    bronze = pl.DataFrame(
        {
            "id": [r["id"] for r in rows],
            "condition_id": [r["conditionId"] for r in rows],
            "raw": [json.dumps(r) for r in rows],
            "request": ["x"] * len(rows),
            "fetched_at": ["2026-11-24"] * len(rows),
        }
    )
    return build_markets(bronze)[0]


def silver_prices(markets: pl.DataFrame, series: dict[str, list[float]]) -> pl.DataFrame:
    """``series[mid]`` = precio diario del primer token desde D0."""
    rows = [
        (f"{mid}a", f"0x{mid}", int((D0 + timedelta(days=i)).timestamp()), p)
        for mid, prices in series.items()
        for i, p in enumerate(prices)
    ]
    bronze = pl.DataFrame(
        {
            "token_id": [r[0] for r in rows],
            "condition_id": [r[1] for r in rows],
            "outcome_index": ["0"] * len(rows),
            "t": [str(r[2]) for r in rows],
            "p": [str(r[3]) for r in rows],
            "request": ["x"] * len(rows),
            "fetched_at": ["x"] * len(rows),
        }
    )
    return build_prices(bronze, markets)[0]
