"""Vigilante del runner de paper trading (PQ-55): avisa si deja de reportar.

Un proceso caído no puede avisar de su propia caída. Por eso el vigilante es **otro proceso**
(`pq paper watchdog`, por ejemplo con cron o systemd en el servidor, PQ-57): lee el heartbeat y
alerta en cada **cambio** de estado, no en cada revisión.

| Estado | Cuándo | Alerta |
|---|---|---|
| ``ok`` | Heartbeat reciente y sano | INFO de recuperación, si antes no lo estaba |
| ``con_fallos`` | Heartbeat reciente con ``ok: false`` | ERROR |
| ``caido`` | Heartbeat más viejo que el máximo | CRITICAL |
| ``sin_heartbeat`` | No existe o no se puede leer | CRITICAL |

El último estado se guarda en disco, así que funciona igual en un bucle que con ``--once``
desde cron. Un mismo estado malo no se repite antes de ``repeat_after``. Solo se guarda cuando el
canal confirma la entrega: si Telegram falla, la revisión siguiente lo reintenta.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from prometheus_platform.api.paper.report import read_heartbeat
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.ports import Clock, Notifier
from prometheus_platform.ops.logging import get_logger

log = get_logger(component="paper_watchdog")


class RunnerHealth(StrEnum):
    OK = "ok"
    FAILING = "con_fallos"
    DOWN = "caido"
    MISSING = "sin_heartbeat"


SEVERITY = {
    RunnerHealth.OK: AlertSeverity.INFO,
    RunnerHealth.FAILING: AlertSeverity.ERROR,
    RunnerHealth.DOWN: AlertSeverity.CRITICAL,
    RunnerHealth.MISSING: AlertSeverity.CRITICAL,
}


class Watchdog:
    def __init__(  # noqa: PLR0913 - keyword-only: cada argumento es una pieza del vigilante
        self,
        *,
        heartbeat_path: Path,
        state_path: Path,
        notifier: Notifier | None,
        clock: Clock,
        max_age: timedelta,
        environment: str,
        repeat_after: timedelta = timedelta(hours=1),
    ) -> None:
        self._heartbeat = heartbeat_path
        self._state = state_path
        self._notifier = notifier
        self._clock = clock
        self._max_age = max_age
        self._environment = environment
        self._repeat_after = repeat_after

    def check(self) -> RunnerHealth:
        now = self._clock.now()
        beat = read_heartbeat(self._heartbeat)
        detail = ""
        if beat is None:
            health = RunnerHealth.MISSING
        elif now - beat["at"] > self._max_age:
            health = RunnerHealth.DOWN
            detail = f"último heartbeat: {beat['at'].isoformat(timespec='seconds')}"
        elif not beat.get("ok", False):
            health = RunnerHealth.FAILING
            detail = str(beat.get("detail", ""))
        else:
            health = RunnerHealth.OK
        previous, alerted_at = self._load()
        changed = health is not previous
        repeat = (
            health is not RunnerHealth.OK
            and alerted_at is not None
            and now - alerted_at >= self._repeat_after
        )
        if (changed or repeat) and not self._alert(health, previous, detail, now):
            # No se entregó: el estado no avanza, así la próxima revisión lo reintenta en vez de
            # esperar una hora creyendo que el aviso salió.
            return health
        if changed or repeat:
            alerted_at = now
        self._save(health, alerted_at)
        return health

    def _alert(
        self, health: RunnerHealth, previous: RunnerHealth, detail: str, now: datetime
    ) -> bool:
        """Avisa y devuelve si se entregó. Sin canal configurado, el log es el aviso."""
        title = (
            "el runner de paper volvió a reportar"
            if health is RunnerHealth.OK
            else f"runner de paper: {health.value}"
        )
        details = {"antes": previous.value, "heartbeat": str(self._heartbeat)}
        if detail:
            details["detalle"] = detail
        log.warning("paper_watchdog_alert", health=health.value, previous=previous.value)
        if self._notifier is None:
            return True
        try:
            delivered = self._notifier.notify(
                Alert(
                    severity=SEVERITY[health],
                    title=title,
                    occurred_at=now,
                    environment=self._environment,
                    details=details,
                )
            )
        except Exception as exc:  # el canal de alertas nunca tumba el vigilante
            log.error("paper_watchdog_notify_failed", error=type(exc).__name__)
            return False
        if not delivered:
            log.error("paper_watchdog_notify_failed", error="no entregada")
        return delivered

    def _load(self) -> tuple[RunnerHealth, datetime | None]:
        try:
            data = json.loads(self._state.read_text(encoding="utf-8"))
            at = data.get("alerted_at")
            return RunnerHealth(data["health"]), datetime.fromisoformat(at) if at else None
        except (OSError, ValueError, KeyError, TypeError):
            return RunnerHealth.OK, None  # primera vez: se asume sano, así una caída avisa

    def _save(self, health: RunnerHealth, alerted_at: datetime | None) -> None:
        payload = {
            "health": health.value,
            "alerted_at": alerted_at.isoformat() if alerted_at else None,
        }
        self._state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state.with_name(f"{self._state.name}.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self._state)
