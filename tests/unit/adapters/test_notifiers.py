import io
import json
from datetime import UTC, datetime

import httpx
from pydantic import SecretStr

from prometheus_platform.adapters.notifiers import (
    ConsoleNotifier,
    TelegramNotifier,
    notifier_from_settings,
)
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.ops.settings import Environment, Settings

TOKEN = "123456:SECRETO"
ALERT = Alert(
    severity=AlertSeverity.ERROR,
    title="hedge_leg_missing",
    occurred_at=datetime(2026, 11, 5, tzinfo=UTC),
    environment="paper",
    details={"symbol": "SOLUSDT"},
)


def telegram(handler: httpx.MockTransport, fallback: io.StringIO) -> TelegramNotifier:
    return TelegramNotifier(
        httpx.Client(transport=handler), SecretStr(TOKEN), "42", fallback=fallback
    )


def test_telegram_posts_plain_text_to_the_bot_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    assert telegram(httpx.MockTransport(handler), io.StringIO()).notify(ALERT)
    [request] = seen
    assert request.url.path == f"/bot{TOKEN}/sendMessage"
    body = json.loads(request.content)
    assert body["chat_id"] == "42"
    assert body["text"].startswith("[ERROR] hedge_leg_missing")
    assert "parse_mode" not in body


def test_telegram_failures_return_false_and_never_leak_the_token() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no se pudo conectar a {request.url}")

    for transport in (
        httpx.MockTransport(down),
        httpx.MockTransport(lambda r: httpx.Response(401, json={"ok": False})),
    ):
        fallback = io.StringIO()
        assert not telegram(transport, fallback).notify(ALERT)
        assert "telegram_alert_failed" in fallback.getvalue()
        assert "SECRETO" not in fallback.getvalue()


def test_console_notifier_writes_the_alert() -> None:
    stream = io.StringIO()
    assert ConsoleNotifier(stream).notify(ALERT)
    assert "ALERTA" in stream.getvalue()
    assert "SOLUSDT" in stream.getvalue()


def test_notifier_selection_by_settings() -> None:
    assert notifier_from_settings(Settings(environment=Environment.DEV)) is None
    assert isinstance(
        notifier_from_settings(Settings(environment=Environment.PAPER)), ConsoleNotifier
    )
    configured = Settings(telegram_bot_token=SecretStr(TOKEN), telegram_chat_id="42")
    assert isinstance(notifier_from_settings(configured), TelegramNotifier)
    blank = Settings(telegram_bot_token=SecretStr("  "), telegram_chat_id="42")
    assert notifier_from_settings(blank) is None
