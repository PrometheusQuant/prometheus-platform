from datetime import date

import pytest

from prometheus_platform.domain.datasets import (
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    Granularity,
    Market,
    RawArchive,
)
from prometheus_platform.domain.model import DomainError

JAN = date(2024, 1, 1)


def test_kline_ref_string_form() -> None:
    ref = ArchiveRef(Market.USDM, DatasetKind.KLINES, "BTCUSDT", JAN, "1h")
    assert str(ref) == "um/klines/BTCUSDT/1h/2024-01-01"


def test_daily_ref_can_start_any_day() -> None:
    ref = ArchiveRef(
        Market.SPOT, DatasetKind.KLINES, "ETHUSDT", date(2024, 1, 15), "1h", Granularity.DAILY
    )
    assert ref.period.day == 15


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": "btcusdt"},
        {"symbol": "BTC-USDT"},
        {"interval": None},
        {"interval": "1x"},
        {"period": date(2024, 1, 2)},
    ],
)
def test_invalid_kline_refs(kwargs: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "market": Market.USDM,
        "dataset": DatasetKind.KLINES,
        "symbol": "BTCUSDT",
        "period": JAN,
        "interval": "1h",
    }
    fields.update(kwargs)
    with pytest.raises(DomainError):
        ArchiveRef(**fields)  # type: ignore[arg-type]


def test_funding_only_exists_for_perpetuals() -> None:
    with pytest.raises(DomainError, match="perpetuos"):
        ArchiveRef(Market.SPOT, DatasetKind.FUNDING_RATE, "BTCUSDT", JAN)
    with pytest.raises(DomainError, match="no tiene intervalo"):
        ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", JAN, "8h")


def test_raw_archive_requires_a_sha256_and_hides_payload() -> None:
    ref = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", JAN)
    with pytest.raises(DomainError):
        RawArchive(ref, b"x", "not-a-digest")
    archive = RawArchive(ref, b"secret-bytes", "a" * 64)
    assert "secret-bytes" not in repr(archive)


def test_checksum_mismatch_message_names_the_archive() -> None:
    ref = ArchiveRef(Market.USDM, DatasetKind.FUNDING_RATE, "BTCUSDT", JAN)
    error = ChecksumMismatchError(ref, "a" * 64, "b" * 64)
    assert str(ref) in str(error)
    assert error.ref == ref
