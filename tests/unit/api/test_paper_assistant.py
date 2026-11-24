"""Asistente /pregunta del bot (PQ-90): explica, no opera. Sin llamadas reales a la API."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from prometheus_platform.adapters.in_memory import FixedClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper import assistant as asst
from prometheus_platform.api.paper.assistant import (
    TOOLS,
    Assistant,
    Context,
    CostLedger,
    run_tool,
    tool_definitions,
)
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.domain.events import FundingSettled, PortfolioValued

from .test_paper_bot import Rig, rig  # noqa: F401 - la fixture del bot se reutiliza

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(name: str, block_id: str = "t1", **arguments: object) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=arguments)


def reply(
    stop: str, *blocks: SimpleNamespace, tokens: tuple[int, int] = (1000, 100)
) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1])
    return SimpleNamespace(stop_reason=stop, content=list(blocks), usage=usage)


class FakeClaude:
    """Devuelve respuestas guionadas y guarda cada petición."""

    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def context(root: Path) -> tuple[Context, JsonlEventJournal, PaperPaths]:
    paths = PaperPaths(root / "paper")
    journal = JsonlEventJournal(paths.journal)
    journal.append(
        PortfolioValued(
            occurred_at=NOW, equity=Decimal(1000), cash=Decimal(1000), gross_notional=Decimal(0)
        )
    )
    journal.append(
        FundingSettled(
            occurred_at=NOW,
            symbol="SOLUSDT",
            funding_time=NOW,
            rate=Decimal("0.00001"),
            interval_hours=8,
            amount=Decimal(0),
            action="mantener",
            s_k="0.04",
            target_open=False,
            was_open=False,
            rebalance=False,
        )
    )
    return (
        Context(paths=paths, data_dir=root, replay=lambda: list(journal.replay())),
        journal,
        paths,
    )


def assistant(root: Path, claude: FakeClaude, limit: str = "1") -> tuple[Assistant, CostLedger]:
    ctx, _, paths = context(root)
    ledger = CostLedger(paths.root / asst.COST_FILE, Decimal(limit))
    return Assistant(create=claude, ctx=ctx, ledger=ledger, clock=FixedClock(NOW)), ledger


# --- no puede operar --------------------------------------------------------------------------


def test_the_tool_registry_is_closed_and_read_only() -> None:
    assert set(TOOLS) == {"estado_paper", "decisiones_recientes", "evaluaciones"}
    assert [t["name"] for t in tool_definitions()] == list(TOOLS)
    forbidden = ("kill", "orden", "order", "cerrar", "submit", "trip", "reset", "comprar", "vender")
    assert not [n for n in TOOLS if any(word in n for word in forbidden)]


def test_the_module_does_not_import_execution_or_the_kill_switch() -> None:
    tree = ast.parse(Path(asst.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    banned = ("kill_switch", "simulated_broker", "runner", "execution", "executor", "binance")
    assert not [m for m in imported if any(b in m for b in banned)]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"KillSwitch", "Broker", "OrderGateway", "SimulatedBroker"}


def test_an_invented_tool_returns_an_error_and_changes_nothing(tmp_path: Path) -> None:
    ctx, _journal, paths = context(tmp_path)
    before = paths.journal.read_text()
    content, failed = run_tool("activar_kill_switch", {}, ctx)
    assert failed
    assert "solo puede leer" in content
    assert not paths.kill_switch.exists()
    assert paths.journal.read_text() == before


def test_every_tool_only_reads(tmp_path: Path) -> None:
    ctx, _, paths = context(tmp_path)
    before = paths.journal.read_text()
    for name in TOOLS:
        content, failed = run_tool(name, {}, ctx)
        assert not failed, content
        json.loads(content)
    assert paths.journal.read_text() == before
    assert not paths.kill_switch.exists()


def test_tools_read_the_real_state(tmp_path: Path) -> None:
    ctx, _, paths = context(tmp_path)
    paths.kill_switch.write_text(json.dumps({"reason": "simulacro", "source": "cli"}))
    state = json.loads(run_tool("estado_paper", {}, ctx)[0])
    assert state["equity_usd"] == "1000"
    assert state["kill_switch"] == "activado"
    assert state["motivo_kill_switch"] == "simulacro"
    decisions = json.loads(run_tool("decisiones_recientes", {"cuantas": 1, "extra": "x"}, ctx)[0])
    assert decisions["liquidaciones"][0]["estado_deseado"] == "fuera"


# --- la conversación ----------------------------------------------------------------------------


def test_answers_after_reading_the_state_and_records_the_cost(tmp_path: Path) -> None:
    claude = FakeClaude(
        reply("tool_use", tool_use("estado_paper")),
        reply("end_turn", text("No hay posición: la señal está por debajo del 20 %.")),
    )
    bot_assistant, ledger = assistant(tmp_path, claude)
    answer = bot_assistant.answer("¿por qué no hay posición abierta hoy?")
    assert answer == "No hay posición: la señal está por debajo del 20 %."
    first = claude.calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert first["output_config"] == {"effort": "low"}
    result = claude.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "t1"
    assert '"equity_usd": "1000"' in result["content"]
    # 2 llamadas de 1000 tokens de entrada y 100 de salida: 2 · (1000 · 4 + 100 · 20) / 1e6.
    assert ledger.spent(NOW.date()) == Decimal("0.012")


def test_the_daily_limit_stops_the_assistant_without_calling_the_api(tmp_path: Path) -> None:
    claude = FakeClaude()
    bot_assistant, ledger = assistant(tmp_path, claude, limit="0.01")
    ledger.add(NOW.date(), Decimal("0.01"))
    assert "límite" in bot_assistant.answer("¿cómo va?")
    assert claude.calls == []
    tomorrow = Assistant(
        create=FakeClaude(reply("end_turn", text("Bien."))),
        ctx=context(tmp_path / "otro")[0],
        ledger=ledger,
        clock=FixedClock(NOW + timedelta(days=1)),
    )
    assert tomorrow.answer("¿cómo va?") == "Bien."  # al día siguiente vuelve a responder


def test_refusals_empty_questions_and_endless_tool_loops_are_handled(tmp_path: Path) -> None:
    refused, _ = assistant(tmp_path / "a", FakeClaude(reply("refusal")))
    assert "No puedo responder" in refused.answer("algo")
    empty, _ = assistant(tmp_path / "b", FakeClaude())
    assert "/pregunta" in empty.answer("   ")
    loop = FakeClaude(
        *[reply("tool_use", tool_use("evaluaciones", f"t{i}")) for i in range(asst.MAX_TURNS)]
    )
    endless, ledger = assistant(tmp_path / "c", loop)
    assert "demasiadas consultas" in endless.answer("dime todo")
    assert len(loop.calls) == asst.MAX_TURNS
    assert ledger.spent(NOW.date()) > 0  # también se cobra lo que no llegó a responder


# --- el bot --------------------------------------------------------------------------------------


def test_bot_says_when_the_assistant_is_not_configured(rig: Rig) -> None:  # noqa: F811
    answer = rig.say("/pregunta ¿cómo va?")
    assert answer is not None
    assert "PQ_ANTHROPIC_API_KEY" in answer


def test_bot_passes_the_question_to_the_assistant(rig: Rig, tmp_path: Path) -> None:  # noqa: F811
    claude = FakeClaude(reply("end_turn", text("Todo en orden.")))
    rig.bot._assistant = assistant(tmp_path / "x", claude)[0]
    assert rig.say("/pregunta ¿todo bien?") == "Todo en orden."
    assert claude.calls[0]["messages"][0]["content"] == "¿todo bien?"


def test_serve_builds_no_assistant_without_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prometheus_platform.api.paper.bot import _assistant  # noqa: PLC0415
    from prometheus_platform.ops.settings import Settings  # noqa: PLC0415

    paths = PaperPaths(tmp_path)
    journal = JsonlEventJournal(paths.journal)
    monkeypatch.delenv("PQ_ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert _assistant(settings, paths, journal, FixedClock(NOW)) is None
    keyed = Settings(_env_file=None, anthropic_api_key="sk-" + "prueba")
    built = _assistant(keyed, paths, journal, FixedClock(NOW))
    assert isinstance(built, Assistant)
