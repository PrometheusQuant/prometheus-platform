"""Alertas operativas: lo que un humano tiene que ver aunque no esté mirando los logs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
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

    def render(self, local_tz: tzinfo | None = None) -> str:
        """Texto plano (sin Markdown, para no tener que escapar nada al enviarlo).

        La hora de referencia es UTC, como en logs y datos; con ``local_tz`` se muestra primero la
        hora local de quien lee la alerta, por ejemplo ``13:27:37 -04 (17:27:37 UTC)``.
        """
        lines = [
            f"[{self.severity.value.upper()}] {self.title}",
            f"entorno={self.environment} hora={self._when(local_tz)}",
        ]
        lines += [f"{k}: {_truncate(v)}" for k, v in sorted(self.details.items())]
        return "\n".join(lines)

    def _when(self, local_tz: tzinfo | None) -> str:
        if local_tz is None:
            return self.occurred_at.isoformat(timespec="seconds")
        local = self.occurred_at.astimezone(local_tz)
        utc = self.occurred_at.astimezone(UTC)
        return f"{local:%Y-%m-%d %H:%M:%S} {local:%Z} ({utc:%H:%M:%S} UTC)"


def _truncate(value: str) -> str:
    return value if len(value) <= MAX_DETAIL_CHARS else value[: MAX_DETAIL_CHARS - 1] + "…"
