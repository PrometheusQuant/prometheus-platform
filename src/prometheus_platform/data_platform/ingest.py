"""Ingesta bronze: lleva archivos de un proveedor histórico al lakehouse sin transformarlos.

Es idempotente: un archivo que ya está guardado con el mismo checksum se salta sin descargarlo.
Un archivo con checksum inválido se rechaza y queda registrado, y la ingesta sigue con el resto:
un archivo corrupto no debe impedir ingerir los demás.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date

from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Market,
)
from prometheus_platform.domain.ports import BronzeStore, HistoricalDataSource
from prometheus_platform.ops.logging import get_logger


@dataclass
class IngestReport:
    written: list[ArchiveRef] = field(default_factory=list)
    skipped: list[ArchiveRef] = field(default_factory=list)
    missing: list[ArchiveRef] = field(default_factory=list)
    rejected: list[ArchiveRef] = field(default_factory=list)
    failed: list[ArchiveRef] = field(default_factory=list)
    rows_written: int = 0

    @property
    def ok(self) -> bool:
        """False si algún archivo se rechazó o falló: los ausentes no cuentan como error."""
        return not (self.rejected or self.failed)


def months(start: date, end: date) -> Iterator[date]:
    """Día 1 de cada mes entre ``start`` y ``end``, ambos incluidos."""
    if end < start:
        raise ValueError(f"El fin ({end}) es anterior al inicio ({start})")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, 1)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def monthly_klines(
    market: Market, symbol: str, interval: str, start: date, end: date
) -> list[ArchiveRef]:
    return [
        ArchiveRef(market, DatasetKind.KLINES, symbol, period, interval)
        for period in months(start, end)
    ]


def monthly_funding(symbol: str, start: date, end: date) -> list[ArchiveRef]:
    return [
        ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, symbol, period)
        for period in months(start, end)
    ]


def ingest(
    refs: Iterable[ArchiveRef], source: HistoricalDataSource, store: BronzeStore
) -> IngestReport:
    log = get_logger(component="ingest")
    report = IngestReport()
    for ref in refs:
        archive = str(ref)
        try:
            expected = source.expected_checksum(ref)
            if store.contains(ref, expected):
                report.skipped.append(ref)
                log.debug("archive_skipped", archive=archive, reason="ya ingerido")
                continue
            rows = store.write(source.fetch(ref, expected))
        except ArchiveNotFoundError:
            report.missing.append(ref)
            log.info("archive_missing", archive=archive)
        except ChecksumMismatchError as exc:
            report.rejected.append(ref)
            store.record_rejection(ref, str(exc))
            log.error("archive_rejected", archive=archive, expected=exc.expected, actual=exc.actual)
        except (DataSourceError, ValueError) as exc:
            # ValueError cubre un CSV con forma inesperada (BronzeFormatError).
            report.failed.append(ref)
            store.record_rejection(ref, str(exc))
            log.error("archive_failed", archive=archive, error=str(exc))
        else:
            report.written.append(ref)
            report.rows_written += rows
            log.info("archive_written", archive=archive, rows=rows)
    log.info(
        "ingest_finished",
        written=len(report.written),
        skipped=len(report.skipped),
        missing=len(report.missing),
        rejected=len(report.rejected),
        failed=len(report.failed),
        rows=report.rows_written,
    )
    return report
