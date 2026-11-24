"""Instantánea point-in-time del mercado: lo único que ve una estrategia (PQ-113, ADR-0011).

Una ``MarketSnapshot`` lleva **solo** datos con ``knowledge_time <= as_of``. Si alguien intenta
construir una con un dato posterior, falla: el sesgo de anticipación se detiene al construirla, y
no depende de que cada estrategia se acuerde de filtrar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from prometheus_platform.domain.model import Bar, DomainError, FundingRate, InstrumentId


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    as_of: datetime
    bars: Mapping[InstrumentId, Sequence[Bar]] = field(default_factory=dict)
    funding: Mapping[InstrumentId, Sequence[FundingRate]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() != timedelta(0):
            raise DomainError("as_of debe estar en UTC")
        series: list[tuple[InstrumentId, Sequence[Bar | FundingRate]]] = [
            *self.bars.items(),
            *self.funding.items(),
        ]
        for instrument, rows in series:
            times = [r.knowledge_time for r in rows]
            if times and times[-1] > self.as_of:
                raise DomainError(
                    f"Dato del futuro en la instantánea: {instrument} conocido en "
                    f"{max(times).isoformat()} > as_of {self.as_of.isoformat()}"
                )
            if times != sorted(times):
                raise DomainError(f"{instrument}: la serie debe ir de la más antigua a la reciente")


def snapshot_at(
    as_of: datetime,
    *,
    bars: Mapping[InstrumentId, Iterable[Bar]] | None = None,
    funding: Mapping[InstrumentId, Iterable[FundingRate]] | None = None,
    lookback: timedelta | None = None,
) -> MarketSnapshot:
    """Corta el historial en ``as_of`` (y, si se da, a la ventana ``lookback``)."""
    start = None if lookback is None else as_of - lookback

    def cut[T: (Bar, FundingRate)](rows: Iterable[T]) -> list[T]:
        kept = [
            r
            for r in rows
            if r.knowledge_time <= as_of and (start is None or r.knowledge_time >= start)
        ]
        return sorted(kept, key=lambda r: r.knowledge_time)

    return MarketSnapshot(
        as_of=as_of,
        bars={i: cut(rows) for i, rows in (bars or {}).items()},
        funding={i: cut(rows) for i, rows in (funding or {}).items()},
    )
