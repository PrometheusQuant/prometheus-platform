"""Mercado por websocket con respaldo REST (PQ-80): sin red real."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from prometheus_platform.adapters.binance_ws_market import (
    StreamCache,
    StreamingMarket,
    StreamWorker,
    apply_message,
    stream_urls,
)
from prometheus_platform.adapters.in_memory import FixedClock

T0 = datetime(2026, 11, 22, tzinfo=UTC)
H = 3_600_000


def mark(symbol: str, price: str, rate: str = "0.0001") -> str:
    return json.dumps(
        {"stream": "x", "data": {"e": "markPriceUpdate", "s": symbol, "p": price, "r": rate}}
    )


def spot(symbol: str, price: str) -> str:
    return json.dumps({"stream": "y", "data": {"e": "24hrMiniTicker", "s": symbol, "c": price}})


def kline(symbol: str, opened: int, closed: bool = True) -> str:
    return json.dumps({"data": {"e": "kline", "s": symbol, "k": {"t": opened, "x": closed}}})


def test_messages_fill_the_cache_and_only_fresh_quotes_are_used() -> None:
    cache = StreamCache()
    apply_message(cache, mark("SOLUSDT", "70.5", "0.0002"), T0)
    assert cache.fresh_prices("SOLUSDT", T0, timedelta(seconds=15)) is None  # falta el spot
    apply_message(cache, spot("SOLUSDT", "70.6"), T0)
    assert cache.fresh_prices("SOLUSDT", T0 + timedelta(seconds=10), timedelta(seconds=15)) == (
        Decimal("70.6"),
        Decimal("70.5"),
    )
    assert cache.estimated_funding("SOLUSDT") == Decimal("0.0002")
    assert cache.fresh_prices("SOLUSDT", T0 + timedelta(seconds=16), timedelta(seconds=15)) is None


def test_closed_klines_detect_gaps_and_open_ones_are_ignored() -> None:
    cache = StreamCache()
    apply_message(cache, kline("SOLUSDT", 0), T0)
    apply_message(cache, kline("SOLUSDT", 5 * H, closed=False), T0)  # en curso: no cuenta
    apply_message(cache, kline("SOLUSDT", H), T0)
    assert cache.gaps == 0
    apply_message(cache, kline("SOLUSDT", 3 * H), T0)  # falta la de las 02:00
    assert cache.gaps == 1


def test_urls_use_the_market_route_for_futures() -> None:
    futures, spot_url = stream_urls(["SOLUSDT", "BTCUSDT"])
    assert futures.startswith("wss://fstream.binance.com/market/stream?streams=")  # KE-018
    assert "solusdt@markPrice@1s/solusdt@kline_1h" in futures
    assert spot_url.endswith("solusdt@miniTicker/btcusdt@miniTicker")


class Rest:
    def __init__(self) -> None:
        self.calls = 0

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        self.calls += 1
        return Decimal(100), Decimal(99)

    def recent_funding(self, symbol: str, limit: int) -> list[Any]:
        return []


def test_streaming_market_falls_back_to_rest_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    clock, cache, rest = FixedClock(T0), StreamCache(), Rest()
    market = StreamingMarket(rest, cache, clock)  # type: ignore[arg-type]
    assert market.prices("SOLUSDT") == (Decimal(100), Decimal(99))  # sin stream: REST
    assert market.degraded() == {"SOLUSDT"}
    apply_message(cache, mark("SOLUSDT", "70"), T0)
    apply_message(cache, spot("SOLUSDT", "71"), T0)
    assert market.prices("SOLUSDT") == (Decimal(71), Decimal(70))
    assert market.degraded() == frozenset()
    assert rest.calls == 1
    assert market.recent_funding("SOLUSDT", 3) == []  # lo liquidado siempre sale de REST


class FakeConnection:
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)

    def recv(self, timeout: float | None = None) -> str:
        if not self.messages:
            raise TimeoutError("silencio")  # un stream que calla cuenta como corte (KE-018)
        return self.messages.pop(0)


def test_worker_reconnects_with_growing_backoff_and_keeps_reading() -> None:
    cache = StreamCache()
    sleeps: list[float] = []
    sessions = [[spot("SOLUSDT", "70")], [], [spot("SOLUSDT", "72"), "no es json"]]

    @contextmanager
    def connect(_: str) -> Iterator[FakeConnection]:
        if not sessions:
            raise OSError("red caída")
        yield FakeConnection(sessions.pop(0))

    worker = StreamWorker(
        cache, ["wss://x"], connect=connect, clock=FixedClock(T0), sleep=sleeps.append
    )
    worker.run_url("wss://x", max_attempts=5)
    assert cache.quotes["SOLUSDT"].spot == Decimal(72)  # leyó tras reconectar; ignoró lo inválido
    assert worker.reconnects == 5
    # Cada conexión lograda vuelve la espera a 1 s; sin red, se duplica (2 s, 4 s…).
    assert sleeps == [1.0, 1.0, 1.0, 2.0, 4.0]
