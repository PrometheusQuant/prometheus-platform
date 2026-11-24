"""Bot de Telegram del paper trading (PQ-72), con un transporte simulado."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from prometheus_platform.adapters.in_memory import FixedClock, RecordingNotifier
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper.bot import (
    KILL_CODE_TTL,
    STALE_AFTER,
    CommandBot,
    parse_command,
    pnl_since,
)
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import build_view
from prometheus_platform.domain.chat import ChatMessage
from prometheus_platform.domain.events import OrderFilled, OrderSubmitted, PortfolioValued
from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)
TEAM = "-1001"
STRANGER = "999"


@dataclass
class FakeTransport:
    inbox: list[ChatMessage] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)
    offsets: list[int | None] = field(default_factory=list)

    def updates(self, offset: int | None, timeout_seconds: int) -> list[ChatMessage]:
        self.offsets.append(offset)
        pending, self.inbox = self.inbox, []
        return pending

    def send(self, chat_id: str, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@dataclass
class Rig:
    bot: CommandBot
    transport: FakeTransport
    notifier: RecordingNotifier
    clock: FixedClock
    paths: PaperPaths
    journal: JsonlEventJournal
    switch: KillSwitch
    next_id: int = 1

    def say(self, text: str, chat: str = TEAM, *, age: timedelta = timedelta(0)) -> str | None:
        """Manda un mensaje y devuelve la respuesta del bot (o ``None`` si no respondió)."""
        message = ChatMessage(self.next_id, chat, text, self.clock.now() - age, "david")
        self.next_id += 1
        before = len(self.transport.sent)
        self.bot.handle(message)
        return self.transport.sent[-1][1] if len(self.transport.sent) > before else None


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    clock = FixedClock(NOW)
    paths = PaperPaths(tmp_path)
    journal = JsonlEventJournal(paths.journal)
    switch = KillSwitch(paths.kill_switch, clock, journal)
    transport, notifier = FakeTransport(), RecordingNotifier()
    codes = iter(["123456", "654321", "111111"])
    bot = CommandBot(
        transport=transport,
        authorized_chats=frozenset({TEAM}),
        paths=paths,
        journal=journal,
        kill_switch=switch,
        clock=clock,
        notifier=notifier,
        environment="paper",
        heartbeat_max_age=timedelta(minutes=10),
        new_code=lambda: next(codes),
    )
    return Rig(bot, transport, notifier, clock, paths, journal, switch)


def write_heartbeat(paths: PaperPaths, at: datetime, *, ok: bool = True) -> None:
    paths.heartbeat.write_text(json.dumps({"at": at.isoformat(), "ok": ok, "detail": ""}))


def value(journal: JsonlEventJournal, at: datetime, equity: str) -> None:
    journal.append(
        PortfolioValued(
            occurred_at=at, equity=Decimal(equity), cash=Decimal(0), gross_notional=Decimal(0)
        )
    )


def test_parse_command_strips_bot_name_and_keeps_arguments() -> None:
    assert parse_command("/kill@PrometheusBot 123456") == ("/kill", ["123456"])
    assert parse_command("  /ESTADO ") == ("/estado", [])
    assert parse_command("hola bot") is None
    assert parse_command("") is None


def test_unauthorized_chat_gets_no_answer_and_alerts_once(rig: Rig) -> None:
    assert rig.say("/estado", chat=STRANGER) is None
    assert rig.say("/kill", chat=STRANGER) is None
    assert rig.transport.sent == []
    [alert] = rig.notifier.alerts  # dos intentos, una sola alerta: no se puede inundar el canal
    assert alert.details["chat"] == STRANGER
    assert not rig.switch.active


def test_plain_text_and_stale_commands_are_ignored(rig: Rig) -> None:
    assert rig.say("hola") is None
    assert rig.say("/kill", age=STALE_AFTER + timedelta(seconds=1)) is None
    assert rig.transport.sent == []


def test_status_without_data_says_so(rig: Rig) -> None:
    reply = rig.say("/estado")
    assert reply is not None
    assert "ARMADO" in reply
    assert "sin heartbeat" in reply
    assert "Posiciones: ninguna" in reply


def test_status_shows_positions_equity_and_health(rig: Rig) -> None:
    spot = InstrumentId("SOLUSDT", Venue.BINANCE)
    rig.journal.append(
        OrderSubmitted(
            occurred_at=NOW, client_order_id="o-entrada-1", instrument=spot, side=Side.BUY,
            quantity=Decimal("2.5"),
        )
    )  # fmt: skip
    rig.journal.append(
        OrderFilled(
            occurred_at=NOW, client_order_id="o-entrada-1", fill_price=Decimal(100),
            fill_quantity=Decimal("2.5"), fee=Decimal("0.25"),
        )
    )  # fmt: skip
    value(rig.journal, NOW, "1000.5")
    write_heartbeat(rig.paths, NOW - timedelta(minutes=2))
    reply = rig.say("/estado")
    assert reply is not None
    assert "SOLUSDT.BINANCE: +2.5" in reply
    assert "Equity: 1000.50 USD" in reply
    assert "sano, último latido hace 2 min" in reply

    write_heartbeat(rig.paths, NOW - timedelta(minutes=30))
    assert "CAÍDO" in (rig.say("/estado") or "")
    write_heartbeat(rig.paths, NOW, ok=False)
    assert "con fallos" in (rig.say("/estado") or "")


def test_pnl_by_period_uses_the_last_valuation_before_each_start(rig: Rig) -> None:
    value(rig.journal, NOW - timedelta(days=10), "1000")  # inicio
    value(rig.journal, NOW - timedelta(days=3), "1010")  # base de los 7 días: la de hace 10
    value(rig.journal, NOW - timedelta(hours=16), "1020")  # ayer: base de hoy
    value(rig.journal, NOW, "1025")
    reply = rig.say("/pnl")
    assert reply is not None
    assert "Hoy (UTC): +5.00 USD (+0.490%)" in reply
    assert "Últimos 7 días: +25.00 USD (+2.500%)" in reply
    assert "Desde el inicio: +25.00 USD (+2.500%)" in reply


def test_pnl_without_valuations() -> None:
    assert pnl_since(build_view([]), None) is None


def test_kill_needs_the_code_sent_back(rig: Rig) -> None:
    assert "/kill 123456" in (rig.say("/kill") or "")
    assert not rig.switch.active  # pedir el código no detiene nada
    assert "ACTIVADO" in (rig.say("/kill 123456") or "")
    state = rig.switch.state()
    assert state is not None
    assert state["source"] == "telegram"
    assert "david" in state["reason"]
    rig.say("/kill")
    assert "ya estaba activado" in (rig.say("/kill 654321") or "")


def test_wrong_code_is_rejected_and_burns_the_pending_code(rig: Rig) -> None:
    rig.say("/kill")
    assert "incorrecto" in (rig.say("/kill 000000") or "")
    assert "incorrecto" in (rig.say("/kill 123456") or "")  # el código ya no sirve
    assert not rig.switch.active


def test_expired_code_is_rejected(rig: Rig) -> None:
    rig.say("/kill")
    rig.clock.advance_to(NOW + KILL_CODE_TTL + timedelta(seconds=1))
    assert "vencido" in (rig.say("/kill 123456") or "")
    assert not rig.switch.active


def test_code_from_one_chat_does_not_work_in_another(rig: Rig, tmp_path: Path) -> None:
    rig.bot = CommandBot(
        transport=rig.transport,
        authorized_chats=frozenset({TEAM, "-1002"}),
        paths=rig.paths,
        journal=rig.journal,
        kill_switch=rig.switch,
        clock=rig.clock,
        notifier=rig.notifier,
        environment="paper",
        heartbeat_max_age=timedelta(minutes=10),
        new_code=lambda: "123456",
    )
    rig.say("/kill", chat=TEAM)
    assert "incorrecto" in (rig.say("/kill 123456", chat="-1002") or "")
    assert not rig.switch.active


def test_poll_once_answers_and_advances_the_offset(rig: Rig) -> None:
    rig.transport.inbox = [
        ChatMessage(41, TEAM, "/ayuda", NOW),
        ChatMessage(42, TEAM, "sticker", NOW),
    ]
    assert rig.bot.poll_once() == 1
    rig.bot.poll_once()
    assert rig.transport.offsets == [None, 43]  # confirma también el mensaje que no era comando
    assert "/estado" in rig.transport.sent[0][1]


def test_unknown_command_lists_the_valid_ones(rig: Rig) -> None:
    reply = rig.say("/comprar BTC")
    assert reply is not None
    assert "No conozco /comprar" in reply
    assert "/pnl" in reply
