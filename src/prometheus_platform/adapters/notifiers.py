"""Adaptadores del puerto ``Notifier``: consola y Telegram (PQ-38).

Telegram usa la Bot API (``sendMessage``). El token va en la URL, así que **nunca** se escribe el
texto de una excepción de httpx (podría contenerla): solo el tipo de error o el código HTTP.
"""

from __future__ import annotations

import contextlib
import sys
from datetime import tzinfo
from typing import TextIO

import httpx
from pydantic import SecretStr

from prometheus_platform.domain.alerts import Alert
from prometheus_platform.domain.ports import Notifier
from prometheus_platform.ops.settings import Environment, Settings

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_MAX_CHARS = 4096


class ConsoleNotifier:
    """Escribe la alerta destacada en un stream. Para paper/live sin Telegram configurado."""

    def __init__(self, stream: TextIO | None = None, *, local_tz: tzinfo | None = None) -> None:
        self._stream = stream
        self._local_tz = local_tz

    def notify(self, alert: Alert) -> bool:
        stream = self._stream if self._stream is not None else sys.stderr
        try:
            stream.write(
                f"\n{'=' * 20} ALERTA {'=' * 20}\n{alert.render(self._local_tz)}\n{'=' * 48}\n"
            )
            stream.flush()
        except (OSError, ValueError):
            return False
        return True


class TelegramNotifier:
    def __init__(
        self,
        client: httpx.Client,
        token: SecretStr,
        chat_id: str,
        *,
        fallback: TextIO | None = None,
        local_tz: tzinfo | None = None,
    ) -> None:
        self._client = client
        self._local_tz = local_tz
        self._token = token
        self._chat_id = chat_id
        self._fallback = fallback

    def notify(self, alert: Alert) -> bool:
        url = f"{TELEGRAM_API}/bot{self._token.get_secret_value()}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": alert.render(self._local_tz)[:TELEGRAM_MAX_CHARS],
            "disable_web_page_preview": True,
        }
        try:
            response = self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            self._warn(f"error de red ({type(exc).__name__})")
            return False
        if response.status_code != httpx.codes.OK:
            self._warn(f"HTTP {response.status_code}")
            return False
        return True

    def _warn(self, reason: str) -> None:
        stream = self._fallback if self._fallback is not None else sys.stderr
        with contextlib.suppress(OSError, ValueError):
            stream.write(f"telegram_alert_failed: {reason}\n")


def notifier_from_settings(
    settings: Settings, client: httpx.Client | None = None
) -> Notifier | None:
    """Telegram si hay token y chat; consola en paper/live; nada en dev (ya se ve en pantalla)."""
    token, chat = settings.telegram_bot_token, settings.telegram_chat_id
    if token is not None and token.get_secret_value().strip() and chat:
        http = client or httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0))
        return TelegramNotifier(http, token, chat, local_tz=settings.alert_tz)
    if settings.environment is Environment.DEV:
        return None
    return ConsoleNotifier(local_tz=settings.alert_tz)
