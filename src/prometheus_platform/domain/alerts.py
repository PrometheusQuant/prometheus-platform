"""Alertas operativas: lo que un humano tiene que ver aunque no esté mirando los logs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

MAX_DETAIL_CHARS = 300


class AlertSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True, kw_only=True)
class Alert:
    severity: AlertSeverity
    title: str
    occurred_at: datetime
    environment: str
    details: Mapping[str, str] = field(default_factory=dict)

    def render(self) -> str:
        """Texto plano (sin Markdown, para no tener que escapar nada al enviarlo)."""
        lines = [
            f"[{self.severity.value.upper()}] {self.title}",
            f"entorno={self.environment} hora={self.occurred_at.isoformat(timespec='seconds')}",
        ]
        lines += [f"{k}: {_truncate(v)}" for k, v in sorted(self.details.items())]
        return "\n".join(lines)


def _truncate(value: str) -> str:
    return value if len(value) <= MAX_DETAIL_CHARS else value[: MAX_DETAIL_CHARS - 1] + "…"
