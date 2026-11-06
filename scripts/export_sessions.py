"""Exporta sesiones de Claude Code a Markdown para cargarlas en NotebookLM (PQ-40).

Qué hace: lee las transcripciones JSONL de Claude Code (``~/.claude/projects/<proyecto>/``) y
escribe un Markdown por sesión con los mensajes del usuario y las respuestas del asistente. No
vuelca salidas de herramientas ni razonamiento interno; de cada herramienta deja una línea con
su descripción. Los secretos se enmascaran con ``redact_text`` (mismo criterio que el logging).

Cómo se ejecuta::

    uv run python scripts/export_sessions.py                      # sesiones de este repo
    uv run python scripts/export_sessions.py --since 2026-11-01
    uv run python scripts/export_sessions.py --session 11c62f58 --out notebooklm/

La salida va a ``notebooklm/`` (ignorado por git). Es idempotente: reescribe los archivos.
Solo lee las transcripciones; no las modifica.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from prometheus_platform.ops.logging import redact_text

_TAGS = re.compile(
    r"<(system-reminder|command-[a-z]+|local-command-[a-z]+|task-notification|"
    r"user-prompt-submit-hook)>.*?</\1>",
    re.S,
)
_PASTED = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)


@dataclass(frozen=True)
class Turn:
    role: str  # "usuario" | "asistente" | "resumen"
    text: str
    timestamp: datetime | None


def projects_dir_for(repo: Path) -> Path:
    """Claude Code guarda cada proyecto en una carpeta con la ruta y "/" cambiado por "-"."""
    return Path.home() / ".claude" / "projects" / str(repo.resolve()).replace("/", "-")


def _timestamp(record: dict[str, Any]) -> datetime | None:
    raw = record.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean(text: str) -> str:
    text = _TAGS.sub("", text)
    text = _PASTED.sub(lambda m: "\n> (texto pegado)\n> " + m.group(1).strip()[:2000], text)
    return redact_text(text).strip()


def _user_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _assistant_text(content: Any) -> str:
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_input = block.get("input") or {}
            what = tool_input.get("description") or tool_input.get("file_path") or ""
            parts.append(f"*[herramienta: {block.get('name', '?')}{' — ' + what if what else ''}]*")
    return "\n\n".join(p for p in parts if p)


def read_turns(lines: Iterable[str]) -> Iterator[Turn]:
    """Turnos legibles de una transcripción, en orden. Ignora líneas corruptas y metadatos."""
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        kind = record.get("type")
        if kind == "user":
            role = "resumen" if record.get("isCompactSummary") else "usuario"
            text = _clean(_user_text(message.get("content")))
        elif kind == "assistant":
            role, text = "asistente", _clean(_assistant_text(message.get("content")))
        else:
            continue
        if text:
            yield Turn(role, text, _timestamp(record))


def _merge(turns: Iterable[Turn]) -> list[Turn]:
    """Une respuestas consecutivas del asistente (una respuesta llega en varios registros)."""
    merged: list[Turn] = []
    for turn in turns:
        if merged and turn.role == "asistente" and merged[-1].role == "asistente":
            last = merged[-1]
            merged[-1] = Turn(last.role, f"{last.text}\n\n{turn.text}", last.timestamp)
        else:
            merged.append(turn)
    return merged


def to_markdown(session_id: str, turns: list[Turn]) -> str:
    stamps = [t.timestamp for t in turns if t.timestamp]
    period = f"{min(stamps):%Y-%m-%d %H:%M} → {max(stamps):%Y-%m-%d %H:%M} UTC" if stamps else "?"
    out = [
        f"# Sesión {session_id}",
        "",
        f"- **Periodo:** {period}",
        f"- **Turnos:** {len(turns)}",
        "",
    ]
    titles = {"usuario": "Usuario", "asistente": "Claude", "resumen": "Resumen de contexto"}
    for turn in turns:
        when = f" ({turn.timestamp:%Y-%m-%d %H:%M})" if turn.timestamp else ""
        out += [f"## {titles[turn.role]}{when}", "", turn.text, ""]
    return "\n".join(out)


def export(
    source: Path,
    out_dir: Path,
    *,
    session: str | None = None,
    since: date | None = None,
    until: date | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path in sorted(source.glob("*.jsonl")):
        if session and not path.stem.startswith(session):
            continue
        with path.open(encoding="utf-8") as handle:
            turns = _merge(read_turns(handle))
        if since or until:
            turns = [
                t
                for t in turns
                if t.timestamp
                and (since is None or t.timestamp.astimezone(UTC).date() >= since)
                and (until is None or t.timestamp.astimezone(UTC).date() <= until)
            ]
        if not turns:
            continue
        target = out_dir / f"sesion-{path.stem[:8]}.md"
        target.write_text(to_markdown(path.stem, turns), encoding="utf-8")
        written.append(target)
    return written


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha inválida {value!r}: usa AAAA-MM-DD") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--source", type=Path, help="carpeta con los .jsonl (por defecto, la de este repo)"
    )
    parser.add_argument("--session", help="id de sesión o su prefijo")
    parser.add_argument("--since", type=_date, help="desde esta fecha (UTC), inclusive")
    parser.add_argument("--until", type=_date, help="hasta esta fecha (UTC), inclusive")
    parser.add_argument("--out", type=Path, default=Path("notebooklm"))
    args = parser.parse_args(argv)

    source = args.source or projects_dir_for(Path.cwd())
    if not source.is_dir():
        print(f"no hay transcripciones en {source}; usa --source", file=sys.stderr)
        return 1
    written = export(source, args.out, session=args.session, since=args.since, until=args.until)
    for path in written:
        print(path)
    print(f"{len(written)} sesiones exportadas a {args.out}/ (fuera de git)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
