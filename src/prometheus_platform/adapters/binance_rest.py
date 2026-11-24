"""Adaptador de la API REST pública de Binance: los datos de hoy, que Data Vision aún no publicó.

Cumple el puerto ``HistoricalDataSource`` con archivos **diarios** (``Granularity.DAILY``): cada
día UTC de velas o de funding se descarga paginado, se escribe como un CSV con **las mismas
columnas que Data Vision** y se empaqueta en un ZIP determinista. Así ``ParquetBronzeStore`` lo
guarda sin cambios, el esquema de bronze es idéntico por construcción y el SHA-256 del ZIP sirve
para la idempotencia: los mismos datos producen el mismo checksum.

- Sin claves: solo endpoints públicos de mercado.
- Solo velas **cerradas**: la que está en curso se descarta hasta que cierre.
- El funding de la API no trae el intervalo de liquidación: se toma de ``/fapi/v1/fundingInfo``
  (los símbolos ajustados) y, si no aparece, el estándar de 8 h. Data Vision, cuando publique el
  mes, reemplaza estos datos (PQ-65).
- Límites de tasa: HTTP 429 y 418 respetan ``Retry-After``; con el peso usado del minuto por
  encima del 80 % del límite, se pausa antes de la siguiente petición.
"""

from __future__ import annotations

import csv
import hashlib
import io
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from prometheus_platform.adapters.parquet_bronze import KLINE_COLUMNS
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Granularity,
    Market,
    RawArchive,
)
from prometheus_platform.ops.logging import get_logger

SOURCE_NAME = "binance_api"
SPOT_URL = "https://api.binance.com"
FUTURES_URL = "https://fapi.binance.com"
FUNDING_COLUMNS = ("calc_time", "funding_interval_hours", "last_funding_rate")
DEFAULT_FUNDING_INTERVAL_HOURS = 8
DAY_MS = 86_400_000
_PAGE_LIMIT = {Market.SPOT: 1000, Market.USDM: 1500}
_FUNDING_PAGE_LIMIT = 1000
# Límites de peso por minuto publicados por Binance (spot 6000, futuros 2400): se pausa antes.
_WEIGHT_LIMIT = {Market.SPOT: 6000, Market.USDM: 2400}
_WEIGHT_PAUSE_FRACTION = 0.8
_RETRYABLE_STATUS = frozenset({418, 429, 500, 502, 503, 504})
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # fecha fija dentro del ZIP: mismo contenido, mismo SHA-256


def day_refs(first: ArchiveRef, until: date) -> list[ArchiveRef]:
    """Un archivo diario por día UTC desde ``first.period`` hasta ``until``, ambos incluidos."""
    if until < first.period:
        raise ValueError(f"El fin ({until}) es anterior al inicio ({first.period})")
    return [
        replace(first, period=first.period + timedelta(days=i), granularity=Granularity.DAILY)
        for i in range((until - first.period).days + 1)
    ]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts debe ser al menos 1")


def deterministic_zip(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, text)
    return buffer.getvalue()


def _csv(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


class BinanceRestSource:
    """Descarga días de velas y funding de la API pública. Cumple ``HistoricalDataSource``."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        base_urls: Mapping[Market, str] | None = None,
        retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - inmutable (frozen)
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        urls = {Market.SPOT: SPOT_URL, Market.USDM: FUTURES_URL} | dict(base_urls or {})
        self._client = client
        self._now = now
        self._base = {market: url.rstrip("/") for market, url in urls.items()}
        self._max_attempts = retry.max_attempts
        self._backoff = retry.backoff_seconds
        self._sleep = sleep
        self._cache: dict[ArchiveRef, RawArchive] = {}
        self._funding_intervals: dict[str, int] | None = None
        self._log = get_logger(component="binance_rest")

    # --- Puerto HistoricalDataSource ----------------------------------------------------------

    def expected_checksum(self, ref: ArchiveRef) -> str:
        """La API no publica checksums: se descarga el día y el checksum es el del ZIP generado."""
        archive = self._download(ref)
        self._cache[ref] = archive
        return archive.sha256

    def fetch(self, ref: ArchiveRef, expected_sha256: str) -> RawArchive:
        archive = self._cache.pop(ref, None) or self._download(ref)
        if archive.sha256 != expected_sha256:
            raise ChecksumMismatchError(ref, expected_sha256, archive.sha256)
        return archive

    # --- Descarga -----------------------------------------------------------------------------

    def _download(self, ref: ArchiveRef) -> RawArchive:
        if ref.granularity is not Granularity.DAILY:
            raise DataSourceError(ref, "la API solo se usa para archivos diarios")
        start = int(datetime.combine(ref.period, datetime.min.time(), UTC).timestamp() * 1000)
        end = start + DAY_MS - 1
        if ref.dataset is DatasetKind.KLINES:
            header, rows = list(KLINE_COLUMNS), self._klines(ref, start, end)
        else:
            header, rows = list(FUNDING_COLUMNS), self._funding(ref, start, end)
        if not rows:
            raise ArchiveNotFoundError(ref, "la API no devolvió datos para ese día")
        name = f"{ref.symbol}-{ref.interval or ref.dataset.value}-{ref.period.isoformat()}.csv"
        payload = deterministic_zip(name, _csv(header, rows))
        return RawArchive(ref=ref, payload=payload, sha256=hashlib.sha256(payload).hexdigest())

    def _klines(self, ref: ArchiveRef, start: int, end: int) -> list[list[str]]:
        path = "/api/v3/klines" if ref.market is Market.SPOT else "/fapi/v1/klines"
        limit = _PAGE_LIMIT[ref.market]
        now_ms = int(self._now().timestamp() * 1000)
        rows: list[list[str]] = []
        cursor = start
        while cursor <= end:
            params = {
                "symbol": ref.symbol,
                "interval": ref.interval,
                "startTime": cursor,
                "endTime": end,
                "limit": limit,
            }
            page = self._get_json(ref, ref.market, path, params)
            if not isinstance(page, list):
                raise DataSourceError(ref, f"respuesta inesperada de {path}")
            for item in page:
                if int(item[6]) >= now_ms:  # vela aún abierta: se descarta hasta que cierre
                    continue
                rows.append([str(v) for v in item[: len(KLINE_COLUMNS)]])
            if len(page) < limit:
                break
            cursor = int(page[-1][0]) + 1
        return rows

    def _funding(self, ref: ArchiveRef, start: int, end: int) -> list[list[str]]:
        interval = str(self._funding_interval(ref))
        rows: list[list[str]] = []
        cursor = start
        while cursor <= end:
            params = {
                "symbol": ref.symbol,
                "startTime": cursor,
                "endTime": end,
                "limit": _FUNDING_PAGE_LIMIT,
            }
            page = self._get_json(ref, Market.USDM, "/fapi/v1/fundingRate", params)
            if not isinstance(page, list):
                raise DataSourceError(ref, "respuesta inesperada de /fapi/v1/fundingRate")
            rows += [[str(i["fundingTime"]), interval, str(i["fundingRate"])] for i in page]
            if len(page) < _FUNDING_PAGE_LIMIT:
                break
            cursor = int(page[-1]["fundingTime"]) + 1
        return rows

    def _funding_interval(self, ref: ArchiveRef) -> int:
        if self._funding_intervals is None:
            info = self._get_json(ref, Market.USDM, "/fapi/v1/fundingInfo", {})
            self._funding_intervals = {
                str(i["symbol"]): int(i["fundingIntervalHours"])
                for i in (info if isinstance(info, list) else [])
                if "fundingIntervalHours" in i
            }
        return self._funding_intervals.get(ref.symbol, DEFAULT_FUNDING_INTERVAL_HOURS)

    def _get_json(self, ref: ArchiveRef, market: Market, path: str, params: dict[str, Any]) -> Any:
        url = f"{self._base[market]}{path}"
        for attempt in range(1, self._max_attempts + 1):
            delay = self._backoff * 2 ** (attempt - 1)
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                failure = f"{type(exc).__name__}: {exc}"
            else:
                if response.is_success:
                    self._respect_weight(market, response)
                    return response.json()
                if response.status_code not in _RETRYABLE_STATUS:
                    raise DataSourceError(ref, f"HTTP {response.status_code} ({path})")
                failure = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, float(retry_after))
            if attempt == self._max_attempts:
                raise DataSourceError(ref, f"{failure} tras {attempt} intentos ({path})")
            self._log.warning("api_retry", path=path, attempt=attempt, error=failure, delay=delay)
            self._sleep(delay)
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _respect_weight(self, market: Market, response: httpx.Response) -> None:
        used = response.headers.get("X-MBX-USED-WEIGHT-1M", "")
        if used.isdigit() and int(used) >= _WEIGHT_PAUSE_FRACTION * _WEIGHT_LIMIT[market]:
            pause = 60 - self._now().second  # hasta el próximo minuto, cuando se reinicia el peso
            self._log.warning("api_weight_pause", market=market.value, used=int(used), pause=pause)
            self._sleep(float(pause))
