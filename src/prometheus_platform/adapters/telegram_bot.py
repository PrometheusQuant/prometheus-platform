"""Adaptador del puerto ``ChatTransport`` sobre la Bot API de Telegram (PQ-72).

Usa *long polling* (``getUpdates``), no webhook: el servidor no abre ningún puerto, igual que el
resto del despliegue (solo el 22). El token va en la URL, así que, como en ``notifiers.py``,
**nunca** se registra el texto de una excepción de httpx: solo su tipo o el código HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from prometheus_platform.adapters.notifiers import TELEGRAM_API, TELEGRAM_MAX_CHARS
from prometheus_platform.domain.chat import ChatMessage
from prometheus_platform.ops.logging import get_logger

log = get_logger(component="telegram_bot")


class TelegramBotApi:
    def __init__(self, client: httpx.Client, token: SecretStr) -> None:
        self._client = client
        self._token = token

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API}/bot{self._token.get_secret_value()}/{method}"

    def _call(self, method: str, payload: dict[str, Any], timeout: float) -> Any | None:
        try:
            response = self._client.post(self._url(method), json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            log.warning("telegram_bot_network_error", method=method, error=type(exc).__name__)
            return None
        if response.status_code != httpx.codes.OK:
            log.warning("telegram_bot_http_error", method=method, status=response.status_code)
            return None
        try:
            body = response.json()
        except ValueError:
            log.warning("telegram_bot_bad_response", method=method)
            return None
        return body.get("result") if isinstance(body, dict) and body.get("ok") else None

    def updates(self, offset: int | None, timeout_seconds: int) -> list[ChatMessage]:
        """Mensajes nuevos desde ``offset``. Los que no son texto vuelven con ``text`` vacío:
        así el bot igual avanza el ``offset`` y no los recibe otra vez."""
        payload: dict[str, Any] = {"timeout": timeout_seconds, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload, timeout=timeout_seconds + 10)
        if not isinstance(result, list):
            return []
        messages = []
        for update in result:
            parsed = _parse(update)
            if parsed is not None:
                messages.append(parsed)
        return messages

    def send(self, chat_id: str, text: str) -> bool:
        payload = {
            "chat_id": chat_id,
            "text": text[:TELEGRAM_MAX_CHARS],
            "disable_web_page_preview": True,
        }
        return self._call("sendMessage", payload, timeout=10) is not None


def _parse(update: Any) -> ChatMessage | None:
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        return None
    message = _dict(update.get("message"))
    chat, sender = _dict(message.get("chat")), _dict(message.get("from"))
    date = message.get("date")
    text = message.get("text")
    return ChatMessage(
        update_id=update["update_id"],
        chat_id=str(chat.get("id", "")),
        text=text if isinstance(text, str) else "",
        sent_at=datetime.fromtimestamp(date, UTC) if isinstance(date, int) else datetime.now(UTC),
        sender=str(sender.get("username") or sender.get("first_name") or ""),
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
