"""Kill-switch: detiene la operación y no se rearma solo (PQ-53, gate de la fase 5).

El estado vive en un **archivo bandera** (``data/paper/KILL_SWITCH``). Sobrevive a un reinicio o a
una caída del proceso, y se puede activar desde fuera, creando el archivo, aunque el proceso no esté
sano. Hay tres vías: automática (``enforce``), CLI (``pq paper kill``) y archivo creado a mano.

Al activarse, en este orden y cada paso protegido por separado (ninguno impide el siguiente):

1. se crea el archivo bandera, de forma **exclusiva y atómica**. Desde ese instante no se aprueban
   órdenes que aumenten exposición. Si no se puede escribir, se lanza la excepción: el proceso no
   debe seguir operando sin poder detenerse;
2. sale la alerta CRITICAL, que el ``AlertForwarder`` envía a Telegram;
3. se cancelan las órdenes abiertas (``OrderGateway.cancel_all``);
4. queda un ``KillSwitchTripped`` en el diario.

La CLI y el archivo manual no tienen acceso al exchange. Por eso el runner llama a ``observe`` en
**cada ciclo**: si el kill-switch está activado, cancela las órdenes (es idempotente) y, si la
activación no llegó al diario (archivo manual o fallo del diario), la registra y alerta. Cerrar las
posiciones lo hace el runner con ``flatten_orders``.

Rearmar exige una acción manual con autor. Primero se aparta el archivo con un renombrado atómico;
después se registra el ``KillSwitchReset``; si el diario falla, el archivo se restaura y el
kill-switch sigue activado.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from prometheus_platform.domain.events import KillSwitchReset, KillSwitchTripped, RiskLimitBreached
from prometheus_platform.domain.ports import Clock, EventJournal, OrderGateway
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.portfolio_risk.risk import Breach

FLAG_NAME = "KILL_SWITCH"
MAX_REASON_CHARS = 500  # líneas cortas en el diario (escrituras atómicas)
log = get_logger(component="kill_switch")


class KillSwitch:
    def __init__(
        self,
        flag_path: Path,
        clock: Clock,
        journal: EventJournal,
        gateway: OrderGateway | None = None,
    ) -> None:
        self._flag = flag_path
        self._clock = clock
        self._journal = journal
        self._gateway = gateway
        self._observed = False  # el aviso de «visto activado» sale una vez por proceso

    @property
    def flag_path(self) -> Path:
        return self._flag

    @property
    def active(self) -> bool:
        return self._flag.exists()

    def state(self) -> dict[str, Any] | None:
        """Motivo, vía, instante y si quedó en el diario, o ``None`` si está armado."""
        if not self.active:
            return None
        try:
            data = json.loads(self._flag.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Vacío, ilegible o un directorio: también cuenta como activado; alguien lo creó a mano.
            return {
                "reason": "archivo bandera sin detalle",
                "source": "archivo",
                "journaled": False,
            }
        if not isinstance(data, dict):
            return {"reason": str(data), "source": "archivo", "journaled": False}
        return data

    def trip(self, reason: str, source: str = "automatico") -> bool:
        """Activa el kill-switch. Devuelve ``False`` si ya estaba activado (idempotente)."""
        reason = reason[:MAX_REASON_CHARS]
        now = self._clock.now()
        if not self._create_flag(reason, source, now):
            return False
        log.critical("kill_switch_tripped", reason=reason, source=source)
        self._cancel_all()
        self._journal_trip(reason, source, now)
        return True

    def observe(self) -> bool:
        """Lo llama el runner en cada ciclo. Devuelve si el kill-switch está activado.

        Si lo está, cancela las órdenes abiertas y completa lo que la vía de activación no pudo
        hacer: el registro en el diario y la alerta (archivo manual o fallo previo del diario).
        """
        state = self.state()
        if state is None:
            self._observed = False
            return False
        self._cancel_all()
        if not state.get("journaled", False):
            at = self._parse_time(state.get("at"))
            self._journal_trip(
                str(state.get("reason", "")), str(state.get("source", "archivo")), at
            )
        if not self._observed:
            log.critical(
                "kill_switch_active", reason=state.get("reason"), source=state.get("source")
            )
            self._observed = True
        return True

    def reset(self, by: str) -> bool:
        """Rearma la operación. Devuelve ``False`` si no estaba activado."""
        if not by.strip():
            raise ValueError("El rearme exige indicar quién lo hace")
        if not self.active:
            return False
        if self._flag.is_dir():
            raise IsADirectoryError(f"{self._flag} es un directorio: bórralo a mano tras revisarlo")
        parked = self._flag.with_name(f"{self._flag.name}.rearmando")
        os.replace(self._flag, parked)  # atómico: una activación posterior crea un archivo nuevo
        try:
            self._journal.append(KillSwitchReset(occurred_at=self._clock.now(), by=by))
        except Exception:
            if not self._flag.exists():
                os.replace(parked, self._flag)  # sin registro no hay rearme
            raise
        parked.unlink(missing_ok=True)
        log.warning("kill_switch_reset", by=by)
        return True

    def _create_flag(self, reason: str, source: str, at: datetime) -> bool:
        payload = {"reason": reason, "source": source, "at": at.isoformat(), "journaled": False}
        self._flag.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        except OSError:
            log.critical("kill_switch_flag_failed", reason=reason, source=source)
            raise
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        return True

    def _cancel_all(self) -> None:
        if self._gateway is None:
            return
        try:
            self._gateway.cancel_all()
        except Exception as exc:  # se reintenta en el próximo observe(); nunca oculta el aviso
            log.critical("kill_switch_cancel_failed", error=type(exc).__name__)

    def _journal_trip(self, reason: str, source: str, at: datetime) -> None:
        try:
            self._journal.append(KillSwitchTripped(occurred_at=at, reason=reason, source=source))
        except Exception as exc:  # observe() lo reintenta: la bandera sigue sin "journaled"
            log.critical("kill_switch_journal_failed", error=type(exc).__name__)
            return
        self._mark_journaled()

    def _mark_journaled(self) -> None:
        state = self.state()
        if state is None or self._flag.is_dir():
            return
        state["journaled"] = True
        tmp = self._flag.with_name(f"{self._flag.name}.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        if self._flag.exists():  # no resucita una bandera rearmada mientras tanto
            os.replace(tmp, self._flag)
        else:
            tmp.unlink(missing_ok=True)

    def _parse_time(self, raw: Any) -> datetime:
        try:
            return datetime.fromisoformat(str(raw))
        except ValueError:
            return self._clock.now()


def enforce(
    breaches: Sequence[Breach], kill_switch: KillSwitch, journal: EventJournal, clock: Clock
) -> bool:
    """Registra cada violación y activa el kill-switch si alguna es grave. Devuelve si se activó."""
    severe = [b for b in breaches if b.trips_kill_switch]
    if severe:  # primero detener; registrar después
        tripped = kill_switch.trip("; ".join(f"{b.rule}: {b.detail}" for b in severe))
    else:
        tripped = False
    now = clock.now()
    for breach in breaches:
        try:
            journal.append(
                RiskLimitBreached(occurred_at=now, rule=breach.rule, detail=breach.detail)
            )
        except Exception as exc:
            log.critical("risk_breach_journal_failed", rule=breach.rule, error=type(exc).__name__)
    return tripped
