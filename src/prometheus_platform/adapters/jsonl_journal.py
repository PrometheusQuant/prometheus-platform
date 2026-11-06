"""Diario de eventos append-only en un archivo JSON Lines (puerto ``EventJournal``).

Una línea por evento, con su tipo y sus campos. Nunca reescribe ni borra: solo agrega al final, con
``fsync`` para que un corte de luz no pierda el último evento confirmado. ``replay`` reconstruye
los eventos tipados, que es lo que permite rehacer el estado del paper trading tras un reinicio.
"""

from __future__ import annotations

import dataclasses
import json
import os
import typing
from collections.abc import Callable, Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from prometheus_platform.domain import events as domain_events
from prometheus_platform.domain.events import DomainEvent
from prometheus_platform.domain.model import InstrumentId, Side, Signal, Venue
from prometheus_platform.ops.logging import get_logger

log = get_logger(component="journal")

_EVENT_TYPES: dict[str, type[DomainEvent]] = {
    name: cls
    for name, cls in vars(domain_events).items()
    if isinstance(cls, type) and issubclass(cls, DomainEvent) and cls is not DomainEvent
}


class JournalCorruptError(ValueError):
    """Una línea del diario no se puede leer: no se adivina, se detiene."""


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    if isinstance(value, InstrumentId):
        return {"symbol": value.symbol, "venue": value.venue.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Side | Venue):
        return value.value
    return value


def _decode_signal(raw: dict[str, Any]) -> Signal:
    hints = typing.get_type_hints(Signal)
    return Signal(**{k: _decode(hints[k], v) for k, v in raw.items()})


_DECODERS: dict[Any, Callable[[Any], Any]] = {
    datetime: datetime.fromisoformat,
    Decimal: Decimal,
    UUID: UUID,
    Side: Side,
    InstrumentId: lambda raw: InstrumentId(raw["symbol"], Venue(raw["venue"])),
    Signal: _decode_signal,
}


def _decode(kind: Any, raw: Any) -> Any:
    decoder = _DECODERS.get(kind)
    return decoder(raw) if decoder is not None else raw


class JsonlEventJournal:
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, event: DomainEvent) -> None:
        line = json.dumps({"type": type(event).__name__, **_encode(event)}, ensure_ascii=False)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Si un corte dejó la última línea a medias, se cierra antes de escribir: así esa línea
        # queda aislada y no se pega al evento nuevo.
        prefix = "\n" if self._ends_mid_line() else ""
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(prefix + line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _ends_mid_line(self) -> bool:
        if not self._path.exists() or self._path.stat().st_size == 0:
            return False
        with self._path.open("rb") as fh:
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) != b"\n"

    def replay(self) -> Iterator[DomainEvent]:
        """Eventos tipados en orden. Una línea corrupta detiene la lectura (no se adivina).

        Única excepción: una **última** línea sin salto de línea es una escritura que un corte
        dejó a medias; se omite con una alerta CRITICAL para que el proceso pueda reiniciar.
        """
        if not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").split("\n")
        truncated = lines.pop()  # lo que hay tras el último salto de línea ("" si está completo)
        for number, line in enumerate(lines, start=1):
            if line.strip():
                yield self._parse(line, number)
        if truncated.strip():
            log.critical("journal_truncated_line", path=str(self._path), line=len(lines) + 1)

    def _parse(self, line: str, number: int) -> DomainEvent:
        try:
            raw = json.loads(line)
            cls = _EVENT_TYPES[raw.pop("type")]
            hints = typing.get_type_hints(cls)
            expected = {f.name for f in dataclasses.fields(cls)}
            if set(raw) != expected:
                raise ValueError(f"campos {sorted(set(raw) ^ expected)}")
            for name, value in raw.items():
                if hints[name] is str and not isinstance(value, str):
                    raise TypeError(f"{name} debe ser texto")
            return cls(**{k: _decode(hints[k], v) for k, v in raw.items()})
        except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as exc:
            raise JournalCorruptError(f"{self._path}:{number}: {type(exc).__name__}") from exc
