"""Señales públicas de contraparte (PQ-96), con respuestas simuladas: nunca lanza."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from prometheus_platform.adapters.counterparty_signals import PublicCounterpartySignals
from prometheus_platform.adapters.in_memory import FixedClock

NOW = datetime(2026, 11, 22, tzinfo=UTC)
ROUTES: dict[str, Any] = {
    "/sapi/v1/system/status": {"status": 0, "msg": "normal"},
    "/api/v3/ticker/price": {"symbol": "USDCUSDT", "price": "1.002"},
    "/fapi/v1/premiumIndex": {"symbol": "BTCUSDT", "markPrice": "60300"},
    "/v5/market/tickers": {"result": {"list": [{"markPrice": "60000"}]}},
    "/api/v5/market/ticker": {"data": [{"last": "60000"}]},
}


def signals(
    routes: dict[str, Any], failing: frozenset[str] = frozenset()
) -> PublicCounterpartySignals:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in failing:
            return httpx.Response(503)
        body = routes.get(request.url.path)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)

    return PublicCounterpartySignals(
        httpx.Client(transport=httpx.MockTransport(handler)), FixedClock(NOW)
    )


def test_reads_the_three_public_signals() -> None:
    r = signals(ROUTES).read()
    assert r.at == NOW
    assert r.system_normal is True
    assert r.usdt_premium == pytest.approx(1 / 1.002 - 1)  # USDT con descuento
    assert r.perp_spread == pytest.approx(60300 / 60000 - 1)
    assert r.sources == {}


def test_a_failing_source_leaves_its_field_unknown() -> None:
    r = signals(ROUTES, failing=frozenset({"/api/v3/ticker/price"})).read()
    assert r.usdt_premium is None
    assert r.sources == {"usdt": "HTTPStatusError"}
    assert r.system_normal is True


def test_one_other_exchange_is_enough_and_none_means_unknown() -> None:
    only_okx = signals(ROUTES, failing=frozenset({"/v5/market/tickers"})).read()
    assert only_okx.perp_spread == pytest.approx(60300 / 60000 - 1)
    neither = signals(
        ROUTES, failing=frozenset({"/v5/market/tickers", "/api/v5/market/ticker"})
    ).read()
    assert neither.perp_spread is None
    assert neither.sources["spread"] == "ValueError"


def test_maintenance_and_bad_prices_are_handled() -> None:
    routes = {
        **ROUTES,
        "/sapi/v1/system/status": {"status": 1},
        "/api/v3/ticker/price": {"price": "0"},
    }
    r = signals(routes).read()
    assert r.system_normal is False
    assert r.usdt_premium is None
