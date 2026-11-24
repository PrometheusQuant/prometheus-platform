"""Funding de otros exchanges por su API pública: Bybit y OKX (PQ-79).

Cumple ``HistoricalDataSource``.

Igual que ``binance_rest``: cada **mes** se descarga paginado, se escribe un CSV con **las mismas
columnas que Data Vision** (``calc_time``, ``funding_interval_hours``, ``last_funding_rate``) y se
empaqueta en un ZIP determinista. Así bronze guarda cada exchange con el mismo esquema y otra fuente
(``source=bybit_api``, ``source=okx_api``), y silver lo construye con el mismo ``build_funding``.

- Sin claves: solo endpoints públicos de mercado.
- El intervalo de cada liquidación se deduce de la distancia a la anterior; la primera del mes usa
  la distancia a la siguiente, o 8 h si está sola. Un hueco que no es un intervalo válido también
  usa 8 h.
- **Límite de OKX:** su API pública solo guarda unos 3 meses de funding (verificado el 22-nov-2026).
  Los meses anteriores se informan como «no publicados»: OKX no cubre el periodo de desarrollo.
- Un mes sin liquidaciones (el símbolo aún no cotizaba) es ``ArchiveNotFoundError``, como en Data
  Vision.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

import httpx

from prometheus_platform.adapters.binance_rest import FUNDING_COLUMNS, deterministic_zip
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    ChecksumMismatchError,
    DatasetKind,
    DataSourceError,
    Granularity,
    RawArchive,
)

BYBIT_URL = "https://api.bybit.com"
OKX_URL = "https://www.okx.com"
HOUR_MS = 3_600_000
VALID_INTERVALS = (1, 2, 4, 8)
DEFAULT_INTERVAL = 8
_BYBIT_PAGE = 200
_OKX_PAGE = 100
_MAX_PAGES = 50  # 50 páginas de 100: más que un mes con funding horario


def _month_bounds(ref: ArchiveRef) -> tuple[int, int]:
    start = datetime.combine(ref.period, datetime.min.time(), UTC)
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    end = start.replace(year=year, month=month)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def settlement_rows(points: list[tuple[int, str]]) -> list[list[str]]:
    """``(milisegundos, tasa)`` → filas de Data Vision con el intervalo deducido, en orden."""
    ordered = sorted(set(points))
    rows = []
    for i, (at, rate) in enumerate(ordered):
        if i > 0:
            gap = round((at - ordered[i - 1][0]) / HOUR_MS)
        elif len(ordered) > 1:
            gap = round((ordered[1][0] - at) / HOUR_MS)
        else:
            gap = DEFAULT_INTERVAL
        interval = gap if gap in VALID_INTERVALS else DEFAULT_INTERVAL
        rows.append([str(at), str(interval), rate])
    return rows


class _MonthlyFundingSource:
    """Base común: archivos mensuales de funding con checksum del ZIP generado."""

    name = "exchange"

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._cache: dict[ArchiveRef, RawArchive] = {}

    def expected_checksum(self, ref: ArchiveRef) -> str:
        archive = self._download(ref)
        self._cache[ref] = archive
        return archive.sha256

    def fetch(self, ref: ArchiveRef, expected_sha256: str) -> RawArchive:
        archive = self._cache.pop(ref, None) or self._download(ref)
        if archive.sha256 != expected_sha256:
            raise ChecksumMismatchError(ref, expected_sha256, archive.sha256)
        return archive

    def _download(self, ref: ArchiveRef) -> RawArchive:
        if (
            ref.dataset is not DatasetKind.FUNDING_RATE
            or ref.granularity is not Granularity.MONTHLY
        ):
            raise DataSourceError(ref, f"{self.name} solo da funding mensual")
        start, end = _month_bounds(ref)
        try:
            points = [p for p in self._points(ref.symbol, start, end) if start <= p[0] <= end]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise DataSourceError(ref, f"{self.name}: {type(exc).__name__}") from exc
        if not points:
            raise ArchiveNotFoundError(ref, f"{self.name} no tiene liquidaciones de ese mes")
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(FUNDING_COLUMNS)
        writer.writerows(settlement_rows(points))
        name = f"{ref.symbol}-{ref.dataset.value}-{ref.period:%Y-%m}.csv"
        payload = deterministic_zip(name, out.getvalue())
        return RawArchive(ref=ref, payload=payload, sha256=hashlib.sha256(payload).hexdigest())

    def _points(self, symbol: str, start: int, end: int) -> list[tuple[int, str]]:
        raise NotImplementedError

    def _get(self, url: str, **params: str | int) -> Any:
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()


class BybitFundingSource(_MonthlyFundingSource):
    """``GET /v5/market/funding/history``: 200 liquidaciones por página, de la más reciente."""

    name = "bybit"

    def __init__(self, client: httpx.Client, base_url: str = BYBIT_URL) -> None:
        super().__init__(client)
        self._base = base_url.rstrip("/")

    def _points(self, symbol: str, start: int, end: int) -> list[tuple[int, str]]:
        points: list[tuple[int, str]] = []
        cursor = end
        for _ in range(_MAX_PAGES):
            data = self._get(
                f"{self._base}/v5/market/funding/history",
                category="linear",
                symbol=symbol,
                startTime=start,
                endTime=cursor,
                limit=_BYBIT_PAGE,
            )
            if int(data.get("retCode", -1)) != 0:
                raise ValueError(f"retCode {data.get('retCode')}: {data.get('retMsg')}")
            page = [
                (int(r["fundingRateTimestamp"]), str(r["fundingRate"]))
                for r in data["result"]["list"]
            ]
            points += page
            if len(page) < _BYBIT_PAGE:
                return points
            cursor = min(t for t, _ in page) - 1
        raise ValueError("la paginación de Bybit no termina")


class OkxFundingSource(_MonthlyFundingSource):
    """``GET /api/v5/public/funding-rate-history``: 100 por página; ``after`` da las anteriores."""

    name = "okx"

    def __init__(self, client: httpx.Client, base_url: str = OKX_URL) -> None:
        super().__init__(client)
        self._base = base_url.rstrip("/")

    def _points(self, symbol: str, start: int, end: int) -> list[tuple[int, str]]:
        inst = f"{symbol.removesuffix('USDT')}-USDT-SWAP"
        points: list[tuple[int, str]] = []
        cursor = end + 1
        for _ in range(_MAX_PAGES):
            data = self._get(
                f"{self._base}/api/v5/public/funding-rate-history",
                instId=inst,
                after=cursor,
                limit=_OKX_PAGE,
            )
            if str(data.get("code")) != "0":
                raise ValueError(f"code {data.get('code')}: {data.get('msg')}")
            page = [(int(r["fundingTime"]), str(r["realizedRate"])) for r in data["data"]]
            points += page
            if len(page) < _OKX_PAGE or min(t for t, _ in page) < start:
                return points
            cursor = min(t for t, _ in page)
        raise ValueError("la paginación de OKX no termina")


SOURCES: dict[str, type[_MonthlyFundingSource]] = {
    "bybit": BybitFundingSource,
    "okx": OkxFundingSource,
}
