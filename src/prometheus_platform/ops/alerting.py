"""Reenvío de eventos de log graves a un ``Notifier`` (PQ-38).

``AlertForwarder`` es un procesador de structlog: se coloca **después** de enmascarar secretos,
así que la alerta nunca lleva una clave. Para no inundar el canal, el mismo evento solo se
reenvía una vez por ventana de enfriamiento.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from structlog.typing import EventDict, WrappedLogger

from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.ports import Notifier

_RANK = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
_RESERVED = {"event", "level", "timestamp", "environment"}
DEFAULT_COOLDOWN = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AlertForwarder:
    def __init__(
        self,
        notifier: Notifier,
        *,
        min_severity: AlertSeverity = AlertSeverity.ERROR,
        cooldown: timedelta = DEFAULT_COOLDOWN,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._notifier = notifier
        self._min_rank = _RANK[min_severity.value]
        self._cooldown = cooldown
        self._clock = clock
        self._last_sent: dict[tuple[str, str], datetime] = {}
        self.suppressed = 0
        self.failed = 0

    def __call__(self, _logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
        level = str(event_dict.get("level", method)).lower()
        if level == "exception":
            level = "error"
        if _RANK.get(level, 0) < self._min_rank:
            return event_dict

        title = str(event_dict.get("event", "evento sin nombre"))
        now = self._clock()
        key = (title, level)
        last = self._last_sent.get(key)
        if last is not None and now - last < self._cooldown:
            self.suppressed += 1
            return event_dict
        self._last_sent[key] = now

        alert = Alert(
            severity=AlertSeverity(level),
            title=title,
            occurred_at=now,
            environment=str(event_dict.get("environment", "desconocido")),
            details={k: _text(v) for k, v in event_dict.items() if k not in _RESERVED},
        )
        try:
            delivered = self._notifier.notify(alert)
        except Exception:  # el canal de alertas nunca tumba el proceso
            delivered = False
        if not delivered:
            self.failed += 1
        return event_dict


def _text(value: Any) -> str:
    return value if isinstance(value, str) else repr(value)
