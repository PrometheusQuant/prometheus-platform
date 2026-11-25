"""Cliente del Fear & Greed Index (PQ-128), sin red."""

from __future__ import annotations

import httpx
import pytest

from prometheus_platform.adapters.fear_greed import FearGreedError, FearGreedSource

BODY = '{"data": [{"value": "11", "value_classification": "Extreme Fear", "timestamp": "1"}]}'


def source(handler: object, sleeps: list[float] | None = None) -> FearGreedSource:
    client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return FearGreedSource(client, sleep=(sleeps if sleeps is not None else []).append)


def test_asks_for_the_whole_history_and_returns_the_raw_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "0"
        return httpx.Response(200, text=BODY)

    url, raw = source(handler).history()
    assert "limit=0" in url
    assert raw == BODY


def test_retries_on_server_errors_and_fails_on_client_errors() -> None:
    answers = [httpx.Response(503), httpx.Response(200, text=BODY)]
    sleeps: list[float] = []
    assert source(lambda _r: answers.pop(0), sleeps).history()[1] == BODY
    assert sleeps == [2.0]
    with pytest.raises(FearGreedError, match="HTTP 404"):
        source(lambda _r: httpx.Response(404)).history()
