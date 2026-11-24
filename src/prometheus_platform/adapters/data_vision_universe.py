"""Listado de símbolos y volumen mensual desde Binance Data Vision (PQ-114).

- ``list_usdm_symbols`` recorre el listado público del bucket (S3, paginado). Incluye los perpetuos
  deslistados, que ya no aparecen en ``exchangeInfo``: así el universo no tiene sesgo de
  supervivencia.
- ``monthly_quote_volume`` descarga el archivo diario de un mes, con su checksum SHA-256, y suma el
  volumen en USDT. Devuelve ``None`` si el archivo no existe, es decir, si el símbolo no cotizaba.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date

import httpx

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.parquet_bronze import _read_csv
from prometheus_platform.domain.datasets import (
    ArchiveNotFoundError,
    ArchiveRef,
    DatasetKind,
    Market,
)

LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
USDM_KLINES_PREFIX = "data/futures/um/monthly/klines/"
_PREFIX = re.compile(r"<Prefix>([^<]+)</Prefix>")
_NEXT = re.compile(r"<NextMarker>([^<]+)</NextMarker>")
_TRUNCATED = re.compile(r"<IsTruncated>true</IsTruncated>")
MAX_PAGES = 50  # ~1000 símbolos por página: tope de seguridad, no un límite esperado
MAX_ATTEMPTS = 4


def _get_page(
    client: httpx.Client, url: str, params: dict[str, str], sleep: Callable[[float], None]
) -> str:
    """Una página del listado, con reintentos ante cortes de red (backoff exponencial)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == MAX_ATTEMPTS:
                raise
            sleep(2.0 ** (attempt - 1))
        else:
            return response.text
    raise AssertionError("inalcanzable")  # pragma: no cover


def list_usdm_symbols(
    client: httpx.Client,
    *,
    url: str = LISTING_URL,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Todos los símbolos con velas mensuales USDⓈ-M en Data Vision, incluidos los deslistados."""
    symbols: set[str] = set()
    marker = ""
    for _ in range(MAX_PAGES):
        params = {"prefix": USDM_KLINES_PREFIX, "delimiter": "/", "marker": marker}
        text = _get_page(client, url, params, sleep)
        for prefix in _PREFIX.findall(text):
            name = prefix.removeprefix(USDM_KLINES_PREFIX).strip("/")
            if name:
                symbols.add(name)
        if not _TRUNCATED.search(text):
            return sorted(symbols)
        next_marker = _NEXT.search(text)
        if next_marker is None:
            raise RuntimeError("Listado truncado sin NextMarker")
        marker = next_marker.group(1)
    raise RuntimeError(f"El listado no terminó en {MAX_PAGES} páginas")


def monthly_quote_volume(source: BinanceDataVisionSource, symbol: str, month: date) -> float | None:
    """Volumen en USDT del mes (suma de ``quote_volume`` diario); ``None`` si no cotizaba."""
    ref = ArchiveRef(Market.USDM, DatasetKind.KLINES, symbol, month.replace(day=1), interval="1d")
    try:
        archive = source.fetch(ref, source.expected_checksum(ref))
    except ArchiveNotFoundError:
        return None
    header, rows = _read_csv(archive)
    column = header.index("quote_volume")
    return sum(float(row[column]) for row in rows)
