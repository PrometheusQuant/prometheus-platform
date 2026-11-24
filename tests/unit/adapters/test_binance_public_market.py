"""Mercado en vivo por la API pública de Binance (PQ-54), con respuestas simuladas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from prometheus_platform.adapters import binance_public_market as module
from prometheus_platform.adapters.binance_public_market import BinancePublicMarket, MarketDataError
from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.domain.model import InstrumentId, Venue

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


def test_each_settlement_keeps_its_own_interval_and_rounds_to_the_hour() -> None:
    """Revisión C3/K3: el intervalo sale de la distancia entre liquidaciones, como en el silver."""
    times = [
        datetime(2026, 11, 5, 16, tzinfo=UTC),
        datetime(2026, 11, 6, 0, tzinfo=UTC),  # 8 h
        datetime(2026, 11, 6, 4, tzinfo=UTC),  # 4 h: Binance acortó el intervalo
        datetime(2026, 11, 6, 8, tzinfo=UTC),
    ]
    rows = [
        {"symbol": "XRPUSDT", "fundingTime": ms(t) - 2, "fundingRate": "0.0001"}  # 07:59:59.998
        for t in times
    ]
    m = market(
        {
            "/fapi/v1/fundingRate": rows,
            "/fapi/v1/fundingInfo": [{"symbol": "XRPUSDT", "fundingIntervalHours": 4}],
        }
    )
    got = m.recent_funding("XRPUSDT", 10)
    assert [r.funding_time for r in got] == times
    assert [r.interval_hours for r in got] == [4, 8, 4, 4]  # la primera usa el actual


# --- MarketDataFeed para el ejecutor genérico (PQ-116) --------------------------------------

HOUR_MS = 3_600_000


def kline(open_ms: int, close: str = "101") -> list[object]:
    return [open_ms, "100", "102", "99", close, "5", open_ms + HOUR_MS - 1, "0", 1, "0", "0", "0"]


def paged_market(rows: list[list[object]], seen: list[dict[str, str]]) -> BinancePublicMarket:
    """Responde a klines como Binance: desde ``startTime``, hasta ``limit`` filas."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append({"path": request.url.path, **params})
        start, limit = int(params["startTime"]), int(params["limit"])
        page = [r for r in rows if int(str(r[0])) >= start][:limit]
        return httpx.Response(200, json=page)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BinancePublicMarket(client, FixedClock(NOW))


def test_bars_are_closed_hourly_candles_known_at_their_close() -> None:
    start = datetime(2026, 11, 6, 6, tzinfo=UTC)
    rows = [kline(ms(start) + i * HOUR_MS) for i in range(4)]  # 06, 07, 08 y 09 (en curso)
    seen: list[dict[str, str]] = []
    btc = InstrumentId("BTCUSDT", Venue.BINANCE)
    bars = paged_market(rows, seen).bars(btc, start, NOW)
    assert [b.open_time.hour for b in bars] == [6, 7, 8]  # la de las 09:00 cierra a las 10:00
    assert bars[0].close_time == datetime(2026, 11, 6, 7, tzinfo=UTC)
    assert bars[0].close == Decimal("101")
    assert seen[0]["path"] == "/api/v3/klines"
    assert seen[0]["interval"] == "1h"

    perp = InstrumentId("BTCUSDT-PERP", Venue.BINANCE)
    seen.clear()
    paged_market(rows, seen).bars(perp, start, NOW)
    assert seen[0]["path"] == "/fapi/v1/klines"
    assert seen[0]["symbol"] == "BTCUSDT"


def test_bars_follow_the_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "PAGE", 2)
    start = datetime(2026, 11, 6, 3, tzinfo=UTC)
    rows = [kline(ms(start) + i * HOUR_MS) for i in range(5)]
    seen: list[dict[str, str]] = []
    bars = paged_market(rows, seen).bars(InstrumentId("BTCUSDT", Venue.BINANCE), start, NOW)
    assert [b.open_time.hour for b in bars] == [3, 4, 5, 6, 7]
    assert len(seen) == 3


def test_endless_pagination_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "PAGE", 1)
    monkeypatch.setattr(module, "MAX_PAGES", 2)
    start = datetime(2026, 11, 6, 3, tzinfo=UTC)
    rows = [kline(ms(start) + i * HOUR_MS) for i in range(5)]
    with pytest.raises(MarketDataError, match="páginas"):
        paged_market(rows, []).bars(InstrumentId("BTCUSDT", Venue.BINANCE), start, NOW)


def test_funding_rates_cover_a_range_and_spot_has_none() -> None:
    times = [datetime(2026, 11, 5, h, tzinfo=UTC) for h in (0, 8, 16)]
    m = market(
        {
            "/fapi/v1/fundingRate": [
                {"symbol": "SOLUSDT", "fundingTime": ms(t) + 3, "fundingRate": "0.0001"}
                for t in times
            ],
            "/fapi/v1/fundingInfo": [{"symbol": "SOLUSDT", "fundingIntervalHours": 8}],
        }
    )
    perp = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
    rates = m.funding_rates(perp, times[1], NOW)
    assert [r.funding_time for r in rates] == times[1:]
    assert all(r.interval_hours == 8 for r in rates)
    assert m.funding_rates(InstrumentId("SOLUSDT", Venue.BINANCE), times[0], NOW) == []
