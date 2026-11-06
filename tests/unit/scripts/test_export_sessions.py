import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from prometheus_platform.ops.logging import REDACTED

SCRIPT = Path(__file__).parents[3] / "scripts" / "export_sessions.py"


@pytest.fixture(scope="module")
def exporter() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_sessions", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # las dataclasses lo necesitan
    spec.loader.exec_module(module)
    return module


def record(kind: str, content: object, ts: str, **extra: object) -> str:
    return json.dumps({"type": kind, "timestamp": ts, "message": {"content": content}, **extra})


SESSION = [
    record(
        "user",
        "<system-reminder>contexto interno</system-reminder>Configura el bot con "
        "PQ_TELEGRAM_BOT_TOKEN=123456789:" + "AAH4kq9" + "x" * 28,
        "2026-11-04T10:00:00Z",
    ),
    record(
        "assistant",
        [
            {"type": "thinking", "thinking": "razonamiento privado"},
            {"type": "text", "text": "Reviso la configuración."},
            {"type": "tool_use", "name": "Bash", "input": {"description": "Ver .env"}},
        ],
        "2026-11-04T10:00:05Z",
    ),
    record(
        "user",
        [{"type": "tool_result", "content": "SALIDA DE HERRAMIENTA"}],
        "2026-11-04T10:00:06Z",
    ),
    record("assistant", [{"type": "text", "text": "Listo."}], "2026-11-04T10:00:09Z"),
    "esto no es json",
    record("user", "turno de un subagente", "2026-11-04T10:01:00Z", isSidechain=True),
    record("user", "Resumen previo de la sesión", "2026-11-05T09:00:00Z", isCompactSummary=True),
    record("user", "¿Y el dashboard?", "2026-11-05T09:01:00Z"),
]


def test_turns_keep_dialogue_and_drop_noise(exporter: ModuleType) -> None:
    turns = exporter._merge(exporter.read_turns(SESSION))
    assert [t.role for t in turns] == ["usuario", "asistente", "resumen", "usuario"]
    user, assistant = turns[0].text, turns[1].text
    assert "contexto interno" not in user
    assert "AAH4kq9" not in user
    assert REDACTED in user
    assert "Reviso la configuración." in assistant
    assert "*[herramienta: Bash — Ver .env]*" in assistant
    assert "Listo." in assistant  # respuestas consecutivas unidas
    assert "razonamiento privado" not in assistant
    assert "SALIDA DE HERRAMIENTA" not in assistant


def test_export_filters_by_session_and_date(exporter: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "proyecto"
    source.mkdir()
    (source / "aaaa1111-x.jsonl").write_text("\n".join(SESSION), encoding="utf-8")
    (source / "bbbb2222-y.jsonl").write_text(SESSION[-1], encoding="utf-8")
    out = tmp_path / "out"

    assert [p.name for p in exporter.export(source, out)] == [
        "sesion-aaaa1111.md",
        "sesion-bbbb2222.md",
    ]
    [only] = exporter.export(source, out, session="aaaa")
    assert only.name == "sesion-aaaa1111.md"

    [recent] = exporter.export(source, out, session="aaaa", since=date(2026, 11, 5))
    text = recent.read_text(encoding="utf-8")
    assert "¿Y el dashboard?" in text
    assert "Reviso la configuración" not in text
    assert exporter.export(source, out, until=date(2026, 11, 1)) == []


def test_main_reports_missing_source(exporter: ModuleType, tmp_path: Path) -> None:
    assert exporter.main(["--source", str(tmp_path / "no-existe")]) == 1
    assert exporter.projects_dir_for(Path("/home/u/code/repo")).name == "-home-u-code-repo"
