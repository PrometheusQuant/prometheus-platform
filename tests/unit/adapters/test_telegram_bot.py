"""Adaptador de la Bot API para el bot de comandos (PQ-72)."""

import io
import json
from collections.abc import Iterator

import httpx
import pytest
import structlog
from pydantic import SecretStr

from prometheus_platform.adapters.telegram_bot import TelegramBotApi
from prometheus_platform.ops.logging import configure_logging
from prometheus_platform.ops.settings import Environment, Settings

TOKEN = "123456789:" + "AAH4kq9" + "x" * 28  # por partes: no es una credencial real


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    configure_logging(Settings(environment=Environment.PAPER), stream=stream)
    yield stream
    structlog.reset_defaults()


def api(handler: httpx.MockTransport) -> TelegramBotApi:
    return TelegramBotApi(httpx.Client(transport=handler), SecretStr(TOKEN))


def test_updates_parse_messages_and_send_the_offset() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path.endswith("/getUpdates")
        result = [
            {
                "update_id": 7,
                "message": {
                    "date": 1_795_000_000,
                    "text": "/estado",
                    "chat": {"id": -1001},
                    "from": {"username": "david"},
                },
            },
            {"update_id": 8, "message": {"date": 1_795_000_001, "chat": {"id": -1001}}},
            {"update_id": "roto"},
        ]
        return httpx.Response(200, json={"ok": True, "result": result})

    [first, second] = api(httpx.MockTransport(handler)).updates(offset=7, timeout_seconds=30)
    assert (first.update_id, first.chat_id, first.text, first.sender) == (
        7,
        "-1001",
        "/estado",
        "david",
    )
    assert second.text == ""  # no es texto, pero vuelve para que el offset avance
    assert seen == [{"timeout": 30, "allowed_updates": ["message"], "offset": 7}]


def test_send_posts_the_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path.endswith("/sendMessage")
        assert body["chat_id"] == "-1001"
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    assert api(httpx.MockTransport(handler)).send("-1001", "hola")


def test_failures_return_empty_and_never_log_the_token(log_stream: io.StringIO) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no se pudo conectar a {request.url}")  # la URL lleva el token

    broken = api(httpx.MockTransport(down))
    assert broken.updates(None, 30) == []
    assert not broken.send("-1001", "hola")
    unauthorized = api(httpx.MockTransport(lambda r: httpx.Response(401, json={"ok": False})))
    assert unauthorized.updates(None, 30) == []
    not_ok = api(httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False})))
    assert not not_ok.send("-1001", "hola")
    output = log_stream.getvalue()
    assert "ConnectError" in output
    assert "AAH4kq9" not in output
