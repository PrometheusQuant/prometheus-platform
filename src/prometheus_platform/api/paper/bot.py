"""Bot de Telegram para vigilar y detener el paper trading desde el celular (PQ-72).

Comandos:

| Comando | Qué hace |
|---|---|
| ``/estado`` | Kill-switch, salud del runner (heartbeat), equity y posiciones |
| ``/pnl`` | Resultado de hoy, de los últimos 7 días y desde el inicio, con funding y costes |
| ``/kill`` | Pide un código de 6 dígitos; ``/kill <código>`` activa el kill-switch |
| ``/pregunta <texto>`` | Responde en lenguaje natural con el estado real (PQ-90, solo lectura) |
| ``/ayuda`` | La lista de comandos |

Seguridad:

- Solo responde a los chats autorizados (``PQ_TELEGRAM_AUTHORIZED_CHAT_IDS``, o el chat de
  alertas). A los demás no les contesta: registra el intento y alerta una vez por chat.
- ``/kill`` exige un segundo mensaje con un código aleatorio que vence en 2 minutos: un toque
  accidental no detiene la operación. Rearmar **no** se puede desde Telegram: exige la CLI con
  ``--confirm`` y ``--by``.
- Ignora los comandos de más de 5 minutos (los que esperaban mientras el bot estaba apagado).
- *Long polling*: no abre puertos.

Lee el diario y el heartbeat con las mismas funciones que el dashboard y el resumen diario
(``report.py``), así que las cifras coinciden.
"""

from __future__ import annotations

import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from decimal import Decimal
from pathlib import Path

import httpx

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.telegram_bot import TelegramBotApi
from prometheus_platform.api.paper.assistant import COST_FILE, Assistant, Context, CostLedger
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import PaperView, build_view, read_heartbeat
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.chat import ChatMessage
from prometheus_platform.domain.ports import ChatTransport, Clock, EventJournal, Notifier
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.ops.settings import Settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch

log = get_logger(component="telegram_bot")

STALE_AFTER = timedelta(minutes=5)
KILL_CODE_TTL = timedelta(minutes=2)
WEEK = timedelta(days=7)
HELP = (
    "Comandos de PrometheusQuant:\n"
    "/estado: kill-switch, runner, equity y posiciones\n"
    "/pnl: resultado de hoy, de 7 días y desde el inicio\n"
    "/kill: detiene la operación (pide un código de confirmación)\n"
    "/pregunta <texto>: explica el estado en lenguaje natural (no opera)\n"
    "Rearmar el kill-switch solo se puede desde la CLI."
)


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


@dataclass(frozen=True, slots=True)
class _PendingKill:
    code: str
    expires_at: datetime


def parse_command(text: str) -> tuple[str, list[str]] | None:
    """``/kill@MiBot 123`` → ``("/kill", ["123"])``. ``None`` si no es un comando."""
    parts = text.strip().split()
    if not parts or not parts[0].startswith("/"):
        return None
    return parts[0].split("@", 1)[0].lower(), parts[1:]


def pnl_since(view: PaperView, since: datetime | None) -> tuple[Decimal, Decimal] | None:
    """Variación de la equity desde ``since`` (o desde el inicio): monto y porcentaje.

    La base es la última valoración anterior a ``since``; si no hay ninguna, la primera.
    """
    if not view.valuations:
        return None
    end = view.valuations[-1].equity
    before = [v for v in view.valuations if since is not None and v.occurred_at < since]
    base = before[-1].equity if before else view.valuations[0].equity
    change = end - base
    return change, (change / base if base > 0 else Decimal(0))


class CommandBot:
    def __init__(  # noqa: PLR0913 - keyword-only: cada argumento es una pieza del bot
        self,
        *,
        transport: ChatTransport,
        authorized_chats: frozenset[str],
        paths: PaperPaths,
        journal: EventJournal,
        kill_switch: KillSwitch,
        clock: Clock,
        notifier: Notifier | None,
        environment: str,
        heartbeat_max_age: timedelta,
        local_tz: tzinfo | None = None,
        poll_timeout_seconds: int = 30,
        new_code: Callable[[], str] = _new_code,
        assistant: Assistant | None = None,
    ) -> None:
        self._transport = transport
        self._authorized = authorized_chats
        self._paths = paths
        self._journal = journal
        self._kill = kill_switch
        self._clock = clock
        self._notifier = notifier
        self._environment = environment
        self._max_age = heartbeat_max_age
        self._tz = local_tz
        self._poll_timeout = poll_timeout_seconds
        self._new_code = new_code
        self._assistant = assistant
        self._offset: int | None = None
        self._pending: dict[str, _PendingKill] = {}
        self._alerted_chats: set[str] = set()

    def poll_once(self) -> int:
        """Una vuelta de *long polling*. Devuelve cuántos comandos respondió."""
        answered = 0
        for message in self._transport.updates(self._offset, self._poll_timeout):
            self._offset = max(self._offset or 0, message.update_id + 1)
            answered += self.handle(message)
        return answered

    def handle(self, message: ChatMessage) -> bool:
        parsed = parse_command(message.text)
        if parsed is None:
            return False
        command, args = parsed
        if message.chat_id not in self._authorized:
            self._reject(message, command)
            return False
        if self._clock.now() - message.sent_at > STALE_AFTER:
            log.info("telegram_bot_stale_command", command=command)
            return False
        log.info("telegram_bot_command", command=command, chat=message.chat_id)
        self._transport.send(message.chat_id, self._answer(command, args, message))
        return True

    # --- comandos --------------------------------------------------------------------------

    def _answer(self, command: str, args: list[str], message: ChatMessage) -> str:
        if command == "/estado":
            return self._status()
        if command == "/pnl":
            return self._pnl()
        if command == "/kill":
            return self._kill_command(args, message)
        if command == "/pregunta":
            return self._question(args)
        if command in {"/start", "/ayuda", "/help"}:
            return HELP
        return f"No conozco {command}.\n\n{HELP}"

    def _question(self, args: list[str]) -> str:
        """PQ-90: el asistente solo lee; sin clave de la API, lo dice."""
        if self._assistant is None:
            return "El asistente no está configurado: falta PQ_ANTHROPIC_API_KEY en el .env."
        return self._assistant.answer(" ".join(args))

    def _status(self) -> str:
        state = self._kill.state()
        view = build_view(self._journal.replay())
        lines = ["Estado del paper trading"]
        lines.append(
            "Kill-switch: ARMADO (operación permitida)"
            if state is None
            else f"Kill-switch: ACTIVADO ({state.get('reason', 'sin motivo')})"
        )
        lines.append(f"Runner: {self._health()}")
        if view.equity is not None:
            lines.append(f"Equity: {view.equity:.2f} USD")
        if view.positions:
            lines.append("Posiciones:")
            lines += [
                f"  {inst}: {qty:+f}" for inst, qty in sorted(view.positions.items(), key=str)
            ]
        else:
            lines.append("Posiciones: ninguna")
        return "\n".join(lines)

    def _health(self) -> str:
        beat = read_heartbeat(self._paths.heartbeat)
        if beat is None:
            return "sin heartbeat (¿está corriendo `pq paper run`?)"
        age = self._clock.now() - beat["at"]
        minutes = int(age.total_seconds() // 60)
        when = f"último latido hace {minutes} min ({self._local(beat['at'])})"
        if age > self._max_age:
            return f"CAÍDO, {when}"
        if not beat.get("ok", False):
            detail = str(beat.get("detail", ""))[:200]
            return f"con fallos, {when}" + (f": {detail}" if detail else "")
        return f"sano, {when}"

    def _pnl(self) -> str:
        view = build_view(self._journal.replay())
        now = self._clock.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        periods = (
            ("Hoy (UTC)", start_of_day),
            ("Últimos 7 días", now - WEEK),
            ("Desde el inicio", None),
        )
        lines = ["Resultado del paper trading"]
        for label, since in periods:
            result = pnl_since(view, since)
            lines.append(
                f"{label}: sin valoraciones"
                if result is None
                else f"{label}: {result[0]:+.2f} USD ({result[1]:+.3%})"
            )
        lines.append(f"Funding cobrado: {view.funding:+.4f} USD")
        lines.append(f"Comisiones y slippage: {view.costs:.4f} USD")
        return "\n".join(lines)

    def _kill_command(self, args: list[str], message: ChatMessage) -> str:
        now = self._clock.now()
        if not args:
            code = self._new_code()
            self._pending[message.chat_id] = _PendingKill(code, now + KILL_CODE_TTL)
            minutes = int(KILL_CODE_TTL.total_seconds() // 60)
            return (
                f"Para activar el kill-switch, responde /kill {code} en los próximos "
                f"{minutes} minutos."
            )
        pending = self._pending.pop(message.chat_id, None)
        if (
            pending is None
            or now > pending.expires_at
            or not secrets.compare_digest(args[0], pending.code)
        ):
            log.warning("telegram_bot_kill_code_rejected", chat=message.chat_id)
            return "Código incorrecto o vencido. Vuelve a enviar /kill para pedir otro."
        who = message.sender or message.chat_id
        tripped = self._kill.trip(f"Telegram ({who})", source="telegram")
        if not tripped:
            return "El kill-switch ya estaba activado."
        return (
            "Kill-switch ACTIVADO. El runner cancela las órdenes y cierra las posiciones en su "
            "próximo ciclo. Rearmar exige la CLI: pq paper kill --reset --confirm --by <nombre>."
        )

    # --- apoyo -----------------------------------------------------------------------------

    def _reject(self, message: ChatMessage, command: str) -> None:
        log.warning(
            "telegram_bot_unauthorized",
            chat=message.chat_id,
            sender=message.sender,
            command=command,
        )
        if self._notifier is None or message.chat_id in self._alerted_chats:
            return
        self._alerted_chats.add(message.chat_id)  # una alerta por chat: no se puede inundar
        self._notifier.notify(
            Alert(
                severity=AlertSeverity.WARNING,
                title="comando del bot desde un chat no autorizado",
                occurred_at=self._clock.now(),
                environment=self._environment,
                details={"chat": message.chat_id, "usuario": message.sender, "comando": command},
            )
        )

    def _local(self, moment: datetime) -> str:
        return (moment.astimezone(self._tz) if self._tz else moment).strftime("%H:%M")


def _assistant(
    settings: Settings, paths: PaperPaths, journal: EventJournal, clock: Clock
) -> Assistant | None:
    """El asistente de PQ-90, solo si hay clave de la API de Claude en el ``.env``."""
    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value().strip():
        return None
    import anthropic  # noqa: PLC0415 - solo se carga si el asistente está configurado

    client = anthropic.Anthropic(api_key=key.get_secret_value())
    return Assistant(
        create=client.beta.messages.create,
        ctx=Context(paths=paths, data_dir=settings.data_dir, replay=lambda: list(journal.replay())),
        ledger=CostLedger(paths.root / COST_FILE, Decimal(str(settings.assistant_daily_limit_usd))),
        clock=clock,
    )


def serve(settings: Settings, notifier: Notifier | None, paper_dir: Path) -> int:
    """``pq paper bot``: compone el bot con los adaptadores reales y atiende hasta Ctrl+C."""
    token = settings.telegram_bot_token
    authorized = settings.bot_authorized_chats
    if token is None or not token.get_secret_value().strip() or not authorized:
        print("sin bot: configura PQ_TELEGRAM_BOT_TOKEN y PQ_TELEGRAM_CHAT_ID", file=sys.stderr)
        return 2
    paths = PaperPaths(paper_dir)
    clock = SystemClock()
    journal = JsonlEventJournal(paths.journal)
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        bot = CommandBot(
            transport=TelegramBotApi(client, token),
            authorized_chats=authorized,
            paths=paths,
            journal=journal,
            kill_switch=KillSwitch(paths.kill_switch, clock, journal),
            clock=clock,
            notifier=notifier,
            environment=settings.environment.value,
            heartbeat_max_age=timedelta(minutes=settings.paper_heartbeat_max_age_minutes),
            local_tz=settings.alert_tz,
            assistant=_assistant(settings, paths, journal, clock),
        )
        print(
            f"bot de Telegram atendiendo {len(authorized)} chat(s) autorizado(s); Ctrl+C para salir"
        )
        try:
            while True:
                if bot.poll_once() == 0:
                    time.sleep(1)  # sin red, getUpdates vuelve al instante: no girar en vacío
        except KeyboardInterrupt:
            return 0
