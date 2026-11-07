"""Mercado en vivo por la API pública de Binance (PQ-54), con respuestas simuladas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from prometheus_platform.adapters.binance_public_market import BinancePublicMarket, MarketDataError
from prometheus_platform.adapters.in_memory import FixedClock

NOW = datetime(2026, 11, 6, 9, 30, tzinfo=UTC)
MS = 1000


def ms(at: datetime) -> int:
    return int(at.timestamp() * MS)


def market(routes: dict[str, Any], status: int = 200) -> BinancePublicMarket:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(status, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BinancePublicMarket(client, FixedClock(NOW))


def test_prices_reads_spot_and_mark() -> None:
    m = market(
        {
            "/api/v3/ticker/price": {"symbol": "SOLUSDT", "price": "160.12"},
            "/fapi/v1/premiumIndex": {"symbol": "SOLUSDT", "markPrice": "160.05000000"},
        }
    )
    assert m.prices("SOLUSDT") == (Decimal("160.12"), Decimal("160.05000000"))


def test_recent_funding_keeps_only_past_settlements_with_their_interval() -> None:
    past = datetime(2026, 11, 6, 8, tzinfo=UTC)
    future = datetime(2026, 11, 6, 12, tzinfo=UTC)
    m = market(
        {
            "/fapi/v1/fundingRate": [
                {"symbol": "SOLUSDT", "fundingTime": ms(past) + 7, "fundingRate": "0.0001"},
                {"symbol": "SOLUSDT", "fundingTime": ms(future), "fundingRate": "0.0002"},
            ],
            "/fapi/v1/fundingInfo": [{"symbol": "SOLUSDT", "fundingIntervalHours": 4}],
        }
    )
    (rate,) = m.recent_funding("SOLUSDT", 10)
    assert rate.funding_time == past
    assert rate.rate == Decimal("0.0001")
    assert rate.interval_hours == 4
    assert rate.instrument.symbol == "SOLUSDT-PERP"


def test_symbols_missing_from_funding_info_use_eight_hours() -> None:
    m = market(
        {
            "/fapi/v1/fundingRate": [
                {
                    "symbol": "XRPUSDT",
                    "fundingTime": ms(datetime(2026, 11, 6, 8, tzinfo=UTC)),
                    "fundingRate": "-0.00005",
                }
            ],
            "/fapi/v1/fundingInfo": [{"symbol": "OTHER", "fundingIntervalHours": 4}],
        }
    )
    assert m.recent_funding("XRPUSDT", 5)[0].interval_hours == 8


@pytest.mark.parametrize(
    ("routes", "status"),
    [
        ({"/api/v3/ticker/price": {"price": "1"}}, 500),
        ({"/api/v3/ticker/price": ["no es un objeto"]}, 200),
        ({}, 200),
    ],
)
def test_bad_responses_raise_market_data_error(routes: dict[str, Any], status: int) -> None:
    with pytest.raises(MarketDataError):
        market(routes, status).prices("SOLUSDT")


def test_funding_must_be_a_list() -> None:
    with pytest.raises(MarketDataError, match="lista"):
        market({"/fapi/v1/fundingRate": {"code": -1121}}).recent_funding("SOLUSDT", 5)
