from datetime import date

import pytest

from prometheus_platform.data_platform.ingest import (
    ingest,
    monthly_funding,
    monthly_klines,
    months,
)
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Market,
    RawArchive,
)
from prometheus_platform.domain.ports import BronzeStore, HistoricalDataSource

GOOD = "a" * 64
BAD = "b" * 64


class FakeSource:
    """Simula un proveedor: por periodo, devuelve un archivo válido, corrupto o ausente."""

    def __init__(
        self,
        corrupt: frozenset[date] = frozenset(),
        absent: frozenset[date] = frozenset(),
        broken: frozenset[date] = frozenset(),
    ) -> None:
        self.corrupt, self.absent, self.broken = corrupt, absent, broken
        self.downloads: list[ArchiveRef] = []

    def expected_checksum(self, ref: ArchiveRef) -> str:
        if ref.period in self.absent:
            raise ArchiveNotFoundError(ref, "no publicado")
        if ref.period in self.broken:
            raise DataSourceError(ref, "HTTP 503 tras 4 intentos")
        return GOOD

    def fetch(self, ref: ArchiveRef, expected_sha256: str) -> RawArchive:
        self.downloads.append(ref)
        if ref.period in self.corrupt:
            raise ChecksumMismatchError(ref, expected_sha256, BAD)
        return RawArchive(ref, b"zip", expected_sha256)


class MemoryStore:
    def __init__(self) -> None:
        self.archives: dict[ArchiveRef, str] = {}
        self.rejections: list[tuple[ArchiveRef, str]] = []

    def contains(self, ref: ArchiveRef, sha256: str) -> bool:
        return self.archives.get(ref) == sha256

    def write(self, archive: RawArchive) -> int:
        self.archives[archive.ref] = archive.sha256
        return 24

    def record_rejection(self, ref: ArchiveRef, reason: str) -> None:
        self.rejections.append((ref, reason))


def refs(n: int = 3) -> list[ArchiveRef]:
    return monthly_klines(Market.USDM, "BTCUSDT", "1h", date(2024, 1, 1), date(2024, n, 1))


def test_months_cross_year_boundaries() -> None:
    assert list(months(date(2023, 11, 20), date(2024, 2, 1))) == [
        date(2023, 11, 1),
        date(2023, 12, 1),
        date(2024, 1, 1),
        date(2024, 2, 1),
    ]
    with pytest.raises(ValueError, match="anterior"):
        list(months(date(2024, 2, 1), date(2024, 1, 1)))


def test_funding_refs_are_perpetual_without_interval() -> None:
    [ref] = monthly_funding("ETHUSDT", date(2024, 5, 1), date(2024, 5, 1))
    assert ref.market is Market.USDM
    assert ref.dataset is DatasetKind.FUNDING_RATE
    assert ref.interval is None


def test_ingest_is_idempotent() -> None:
    source, store = FakeSource(), MemoryStore()
    first = ingest(refs(), source, store)
    second = ingest(refs(), source, store)

    assert len(first.written) == 3
    assert first.rows_written == 72
    assert second.written == []
    assert len(second.skipped) == 3
    assert len(source.downloads) == 3  # la segunda pasada no descarga nada
    assert first.ok
    assert second.ok


def test_corrupt_archive_is_rejected_recorded_and_does_not_stop_the_rest() -> None:
    feb = date(2024, 2, 1)
    store = MemoryStore()
    report = ingest(refs(), FakeSource(corrupt=frozenset({feb})), store)

    assert [r.period for r in report.rejected] == [feb]
    assert len(report.written) == 2
    assert all(r.period != feb for r in store.archives)
    [(ref, reason)] = store.rejections
    assert ref.period == feb
    assert "checksum" in reason
    assert not report.ok


def test_unpublished_months_are_missing_not_errors() -> None:
    mar = date(2024, 3, 1)
    report = ingest(refs(), FakeSource(absent=frozenset({mar})), MemoryStore())
    assert [r.period for r in report.missing] == [mar]
    assert report.ok


def test_transport_failures_are_recorded_as_failed() -> None:
    jan = date(2024, 1, 1)
    store = MemoryStore()
    report = ingest(refs(), FakeSource(broken=frozenset({jan})), store)
    assert [r.period for r in report.failed] == [jan]
    assert len(store.rejections) == 1
    assert not report.ok


def test_fakes_satisfy_the_ports() -> None:
    source: HistoricalDataSource = FakeSource()
    store: BronzeStore = MemoryStore()
    assert ingest([], source, store).ok
