"""API pública de Polymarket (PQ-92): paginación, ventanas y reintentos, con transporte simulado."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from prometheus_platform.adapters import polymarket
from prometheus_platform.adapters.polymarket import PolymarketSource, iso
from prometheus_platform.domain.prediction_markets import PredictionMarketError

JAN = datetime(2024, 1, 1, tzinfo=UTC)
JAN_END = datetime(2024, 1, 31, 23, 59, 59, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


def source(handler: Handler, sleeps: list[float] | None = None) -> PolymarketSource:
    pauses = [] if sleeps is None else sleeps
    return PolymarketSource(
        httpx.Client(transport=httpx.MockTransport(handler)), retries=2, sleep=pauses.append
    )


def test_iso_requires_utc() -> None:
    assert iso(JAN) == "2024-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="UTC"):
        iso(datetime(2024, 1, 1))  # noqa: DTZ001 - el caso que se rechaza


def test_gamma_pages_by_id_with_tags_until_a_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polymarket, "GAMMA_PAGE", 2)
    seen: list[dict[str, str]] = []
    pages = [[{"id": "1"}, {"id": "2"}], [{"id": "3"}]]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=pages[len(seen) - 1])

    result = source(handler).closed_markets(JAN, JAN_END, 1000)

    assert [r["id"] for p in result for r in p.rows] == ["1", "2", "3"]
    assert [s["offset"] for s in seen] == ["0", "2"]
    first = seen[0]
    assert first["order"] == "id"
    assert first["ascending"] == "true"
    assert first["include_tag"] == "true"
    assert first["closed"] == "true"
    assert first["end_date_min"] == "2024-01-01T00:00:00Z"
    assert first["end_date_max"] == "2024-01-31T23:59:59Z"
    assert "offset=0" in result[0].request  # linaje: la URL exacta


def test_gamma_splits_a_window_that_exceeds_the_offset_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con offset ≤ 2.000, una ventana llena se parte en dos mitades sin solape."""
    monkeypatch.setattr(polymarket, "GAMMA_PAGE", 2)
    monkeypatch.setattr(polymarket, "GAMMA_MAX_OFFSET", 2)
    windows: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        window = (params["end_date_min"], params["end_date_max"])
        if params["offset"] == "0":
            windows.append(window)
        full = window == (iso(JAN), iso(JAN_END))
        return httpx.Response(200, json=[{"id": "x"}, {"id": "y"}] if full else [{"id": "z"}])

    result = source(handler).closed_markets(JAN, JAN_END, 0)

    assert windows[0] == (iso(JAN), iso(JAN_END))
    first_half, second_half = windows[1], windows[2]
    assert first_half[0] == iso(JAN)
    assert second_half[1] == iso(JAN_END)
    end_first = datetime.fromisoformat(first_half[1])
    assert datetime.fromisoformat(second_half[0]) - end_first == timedelta(seconds=1)
    assert [r["id"] for p in result for r in p.rows] == ["z", "z"]


def test_gamma_gives_up_when_one_hour_is_still_too_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(polymarket, "GAMMA_PAGE", 1)
    monkeypatch.setattr(polymarket, "GAMMA_MAX_OFFSET", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": "x"}])

    with pytest.raises(PredictionMarketError, match="Más de"):
        source(handler).closed_markets(JAN, JAN + timedelta(minutes=30), 0)


def test_clob_full_history_uses_interval_max() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"history": [{"t": 1, "p": 0.4}]})

    pages = source(handler).price_history("123", 1440)

    assert seen == [{"market": "123", "interval": "max", "fidelity": "1440"}]
    assert pages[0].rows == [{"t": 1, "p": 0.4}]


def test_clob_windows_are_at_most_fifteen_days_and_do_not_overlap() -> None:
    seen: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        seen.append((int(params["startTs"]), int(params["endTs"])))
        return httpx.Response(200, json={"history": []})

    start, end = JAN, JAN + timedelta(days=40)
    source(handler).price_history("123", 1, start, end)

    assert seen[0][0] == int(start.timestamp())
    assert seen[-1][1] == int(end.timestamp())
    assert all(b - a <= 15 * 86400 for a, b in seen)
    assert all(nxt[0] == prev[1] + 1 for prev, nxt in itertools.pairwise(seen))


def test_clob_window_needs_both_ends() -> None:
    with pytest.raises(ValueError, match="juntos"):
        source(lambda r: httpx.Response(200)).price_history("1", 60, start=JAN)


def test_clob_error_body_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "interval is too long"})

    with pytest.raises(PredictionMarketError, match="history"):
        source(handler).price_history("1", 1440)


def test_trades_follow_the_cursor_until_has_more_is_false() -> None:
    seen: list[dict[str, str]] = []
    bodies: list[dict[str, Any]] = [
        {"data": [{"price": 0.5}], "pagination": {"has_more": True, "next_cursor": "abc"}},
        {"data": [{"price": 0.6}], "pagination": {"has_more": False}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=bodies[len(seen) - 1])

    pages = source(handler).trades("0xabc", max_pages=10)

    assert [p.rows[0]["price"] for p in pages] == [0.5, 0.6]
    assert "cursor" not in seen[0]
    assert seen[1]["cursor"] == "abc"
    assert seen[0]["condition"] == "0xabc"


def test_trades_stop_at_max_pages() -> None:
    body = {"data": [{}], "pagination": {"has_more": True, "next_cursor": "c"}}
    pages = source(lambda r: httpx.Response(200, json=body)).trades("0x1", max_pages=3)
    assert len(pages) == 3


def test_retries_rate_limits_then_succeeds() -> None:
    sleeps: list[float] = []
    answers = [httpx.Response(429), httpx.Response(503), httpx.Response(200, json=[])]

    def handler(request: httpx.Request) -> httpx.Response:
        return answers.pop(0)

    assert source(handler, sleeps).closed_markets(JAN, JAN_END, 0)[0].rows == []
    assert sleeps == [2.0, 4.0]


def test_retries_are_bounded() -> None:
    with pytest.raises(PredictionMarketError, match="tras reintentar"):
        source(lambda r: httpx.Response(429)).closed_markets(JAN, JAN_END, 0)


def test_transport_errors_are_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("caído", request=request)
        return httpx.Response(200, json=[])

    assert source(handler).closed_markets(JAN, JAN_END, 0)[0].rows == []


def test_client_errors_are_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(422, json={"error": "offset too large"})

    with pytest.raises(PredictionMarketError, match="HTTP 422"):
        source(handler).closed_markets(JAN, JAN_END, 0)
    assert len(calls) == 1


def test_non_json_and_wrong_shapes_are_errors() -> None:
    with pytest.raises(PredictionMarketError, match="JSON"):
        source(lambda r: httpx.Response(200, text="<html>")).closed_markets(JAN, JAN_END, 0)
    with pytest.raises(PredictionMarketError, match="lista"):
        source(lambda r: httpx.Response(200, json={"a": 1})).closed_markets(JAN, JAN_END, 0)
    with pytest.raises(PredictionMarketError, match="data"):
        source(lambda r: httpx.Response(200, json=[])).trades("0x1", 1)
    with pytest.raises(ValueError, match="anterior"):
        source(lambda r: httpx.Response(200, json=[])).closed_markets(JAN_END, JAN, 0)
