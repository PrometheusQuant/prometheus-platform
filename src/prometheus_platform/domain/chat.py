"""Mensajes de un canal de chat de ida y vuelta (bot de Telegram, PQ-72)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Un mensaje de texto recibido. ``update_id`` ordena los mensajes y sirve para confirmarlos."""

    update_id: int
    chat_id: str
    text: str
    sent_at: datetime
    sender: str = ""
