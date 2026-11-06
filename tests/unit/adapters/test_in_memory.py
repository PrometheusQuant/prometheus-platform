from datetime import UTC, datetime, timedelta

import pytest

from prometheus_platform.adapters.in_memory import FixedClock, InMemoryEventJournal
from prometheus_platform.domain.events import RiskLimitBreached
from prometheus_platform.domain.ports import Clock, EventJournal

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def breach(at: datetime) -> RiskLimitBreached:
    return RiskLimitBreached(occurred_at=at, rule="max_drawdown", detail="-20%")


def test_journal_replays_in_append_order() -> None:
    journal = InMemoryEventJournal()
    first, second = breach(T0), breach(T0 + timedelta(minutes=1))
    journal.append(first)
    journal.append(second)
    assert list(journal.replay()) == [first, second]
    assert len(journal) == 2


def test_journal_rejects_out_of_order_events() -> None:
    journal = InMemoryEventJournal()
    journal.append(breach(T0))
    with pytest.raises(ValueError, match="fuera de orden"):
        journal.append(breach(T0 - timedelta(seconds=1)))


def test_clock_only_moves_forward() -> None:
    clock = FixedClock(T0)
    clock.advance_to(T0 + timedelta(hours=1))
    assert clock.now() == T0 + timedelta(hours=1)
    with pytest.raises(ValueError, match="retroceder"):
        clock.advance_to(T0)


def test_adapters_satisfy_domain_ports() -> None:
    # mypy verifica estáticamente que los adaptadores cumplen los Protocol del dominio.
    journal: EventJournal = InMemoryEventJournal()
    clock: Clock = FixedClock(T0)
    assert clock.now() == T0
    assert list(journal.replay()) == []
