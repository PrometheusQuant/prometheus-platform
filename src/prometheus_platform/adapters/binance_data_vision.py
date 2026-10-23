"""Adaptador de Binance Data Vision: archivos históricos públicos con checksum SHA-256.

Cumple el puerto ``HistoricalDataSource``. Cada archivo ``.zip`` se publica junto a un
``.zip.CHECKSUM`` con su SHA-256; un archivo que no coincide se rechaza. Los fallos transitorios
(timeouts, errores de red, HTTP 429 y 5xx) se reintentan con backoff exponencial.

Hallazgos del spike PQ-19 que afectan a quien consuma estos archivos (se tratan en silver):
spot usa microsegundos desde 2025-01 y los CSV de futuros solo tienen cabecera desde 2022-01.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable

import httpx

from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DataSourceError,
    Granularity,
    Market,
    RawArchive,
)
from prometheus_platform.ops.logging import get_logger

BASE_URL = "https://data.binance.vision"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def archive_path(ref: ArchiveRef) -> str:
    """Ruta del archivo en Data Vision, p. ej.
    ``data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip``."""
    market = "spot" if ref.market is Market.SPOT else "futures/um"
    period = (
        ref.period.strftime("%Y-%m")
        if ref.granularity is Granularity.MONTHLY
        else ref.period.isoformat()
    )
    label = ref.interval or ref.dataset.value
    folder = f"{ref.symbol}/{ref.interval}" if ref.interval else ref.symbol
    return (
        f"data/{market}/{ref.granularity}/{ref.dataset}/{folder}/{ref.symbol}-{label}-{period}.zip"
    )


class BinanceDataVisionSource:
    """Descarga archivos de Data Vision. Cumple el puerto ``HistoricalDataSource``."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        base_url: str = BASE_URL,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts debe ser al menos 1")
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._log = get_logger(component="binance_data_vision")

    def expected_checksum(self, ref: ArchiveRef) -> str:
        text = self._get(ref, f"{archive_path(ref)}.CHECKSUM").decode().strip()
        digest = text.split()[0].lower() if text else ""
        if not _SHA256.match(digest):
            raise DataSourceError(ref, f"archivo CHECKSUM ilegible: {text[:80]!r}")
        return digest

    def fetch(self, ref: ArchiveRef, expected_sha256: str) -> RawArchive:
        payload = self._get(ref, archive_path(ref))
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected_sha256:
            raise ChecksumMismatchError(ref, expected_sha256, actual)
        return RawArchive(ref=ref, payload=payload, sha256=actual)

    def _get(self, ref: ArchiveRef, path: str) -> bytes:
        url = f"{self._base_url}/{path}"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                failure = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == httpx.codes.NOT_FOUND:
                    raise ArchiveNotFoundError(ref, f"no publicado ({url})")
                if response.is_success:
                    return response.content
                if response.status_code not in _RETRYABLE_STATUS:
                    raise DataSourceError(ref, f"HTTP {response.status_code} ({url})")
                failure = f"HTTP {response.status_code}"
            if attempt == self._max_attempts:
                raise DataSourceError(ref, f"{failure} tras {attempt} intentos ({url})")
            delay = self._backoff * 2 ** (attempt - 1)
            self._log.warning(
                "download_retry", url=url, attempt=attempt, error=failure, delay=delay
            )
            self._sleep(delay)
        raise AssertionError("inalcanzable")  # pragma: no cover
