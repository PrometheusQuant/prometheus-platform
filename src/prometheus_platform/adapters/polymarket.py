"""API pública de Polymarket: catálogo, historial de precios y operaciones (PQ-92).

Cumple ``PredictionMarketSource``. Sin claves: solo endpoints públicos. Lo que se sabe de cada
endpoint viene del spike PQ-78 (``docs/investigacion/2026-11-24-spike-datos-polymarket.md``):

- **Gamma** ``/markets``: como mucho 100 filas por página y ``offset`` ≤ 2.000. Se ordena por
  ``id`` para que la paginación sea estable. Si una ventana de fechas tiene más mercados de los que
  caben, se parte en dos y se pide cada mitad. ``end_date_min/max`` incluyen los dos extremos.
  ``include_tag=true`` trae las etiquetas del evento (``Sports``…).
- **CLOB** ``/prices-history``: sin ventana, ``interval=max`` solo da la serie diaria
  (``fidelity=1440``). Con ``startTs``/``endTs`` la ventana es de 15 días como mucho, así que una
  ventana mayor se pide en tramos.
- **Data API v2** ``/v2/trades?condition=``: cursor opaco en ``pagination.next_cursor``; la v1
  está retirada desde el 2-nov-2026.

Los límites documentados (300 a 1.000 peticiones cada 10 s por IP) quedan lejos del ritmo de una
ingesta secuencial. Ante un 429 o un 5xx se reintenta con espera creciente.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from prometheus_platform.domain.prediction_markets import PredictionMarketError, RawPage

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
GAMMA_PAGE = 100
GAMMA_MAX_OFFSET = 2000  # medido el 2026-11-24: offset=2001 responde 422
CLOB_MAX_WINDOW = timedelta(days=15)
TRADES_PAGE = 1000  # máximo documentado de /v2/trades
MIN_SPLIT = timedelta(hours=1)
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_HTTP_OK = 200


def iso(at: datetime) -> str:
    """Instante UTC con segundos y ``Z``, el formato que acepta Gamma."""
    if at.tzinfo is None or at.utcoffset() != timedelta(0):
        raise ValueError(f"Se esperaba un instante UTC: {at!r}")
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PolymarketSource:
    """Cliente de las API públicas de Polymarket."""

    def __init__(  # noqa: PLR0913 - URLs y reintentos configurables para los tests
        self,
        client: httpx.Client,
        *,
        gamma_url: str = GAMMA_URL,
        clob_url: str = CLOB_URL,
        data_url: str = DATA_URL,
        retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._gamma = gamma_url.rstrip("/")
        self._clob = clob_url.rstrip("/")
        self._data = data_url.rstrip("/")
        self._retries = retries
        self._sleep = sleep

    def _get(self, url: str, params: Mapping[str, str | int | float]) -> tuple[str, Any]:
        """GET con reintentos. Devuelve la URL exacta pedida y el JSON."""
        last = ""
        for attempt in range(self._retries + 1):
            try:
                response = self._client.get(url, params=dict(params))
            except httpx.TransportError as exc:
                last = type(exc).__name__
            else:
                if response.status_code == _HTTP_OK:
                    try:
                        return str(response.request.url), response.json()
                    except ValueError as exc:
                        raise PredictionMarketError(f"{url}: respuesta que no es JSON") from exc
                if response.status_code not in _RETRY_STATUS:
                    raise PredictionMarketError(f"{url}: HTTP {response.status_code}")
                last = f"HTTP {response.status_code}"
            if attempt < self._retries:
                self._sleep(2.0 * (attempt + 1))
        raise PredictionMarketError(f"{url}: sin respuesta válida tras reintentar ({last})")

    def closed_markets(self, start: datetime, end: datetime, min_volume: float) -> list[RawPage]:
        if end < start:
            raise ValueError(f"El fin ({end}) es anterior al inicio ({start})")
        pages: list[RawPage] = []
        offset = 0
        while offset <= GAMMA_MAX_OFFSET:
            request, rows = self._get(
                f"{self._gamma}/markets",
                {
                    "closed": "true",
                    "volume_num_min": min_volume,
                    "end_date_min": iso(start),
                    "end_date_max": iso(end),
                    "include_tag": "true",
                    "order": "id",
                    "ascending": "true",
                    "limit": GAMMA_PAGE,
                    "offset": offset,
                },
            )
            if not isinstance(rows, list):
                raise PredictionMarketError(f"Gamma no devolvió una lista: {request}")
            pages.append(RawPage(request, rows))
            if len(rows) < GAMMA_PAGE:
                return pages
            offset += GAMMA_PAGE
        # La ventana tiene más mercados de los que Gamma deja paginar: se parte en dos.
        if end - start <= MIN_SPLIT:
            raise PredictionMarketError(
                f"Más de {GAMMA_MAX_OFFSET + GAMMA_PAGE} mercados entre {iso(start)} e {iso(end)}"
            )
        middle = (start + (end - start) / 2).replace(microsecond=0)
        return self.closed_markets(start, middle, min_volume) + self.closed_markets(
            middle + timedelta(seconds=1), end, min_volume
        )

    def price_history(
        self,
        token_id: str,
        fidelity_minutes: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RawPage]:
        url = f"{self._clob}/prices-history"
        if start is None or end is None:
            if start is not None or end is not None:
                raise ValueError("start y end van juntos")
            return [self._history(url, {"market": token_id, "interval": "max"}, fidelity_minutes)]
        pages = []
        cursor = start
        while cursor <= end:
            stop = min(cursor + CLOB_MAX_WINDOW, end)
            window: dict[str, str | int] = {
                "market": token_id,
                "startTs": int(cursor.timestamp()),
                "endTs": int(stop.timestamp()),
            }
            pages.append(self._history(url, window, fidelity_minutes))
            cursor = stop + timedelta(seconds=1)
        return pages

    def _history(self, url: str, params: dict[str, str | int], fidelity: int) -> RawPage:
        request, body = self._get(url, {**params, "fidelity": fidelity})
        history = body.get("history") if isinstance(body, dict) else None
        if not isinstance(history, list):
            raise PredictionMarketError(f"El CLOB no devolvió 'history': {request}")
        return RawPage(request, history)

    def trades(self, condition_id: str, max_pages: int) -> list[RawPage]:
        pages: list[RawPage] = []
        cursor: str | None = None
        for _ in range(max_pages):
            params: dict[str, str | int] = {"condition": condition_id, "limit": TRADES_PAGE}
            if cursor:
                params["cursor"] = cursor
            request, body = self._get(f"{self._data}/v2/trades", params)
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise PredictionMarketError(f"La Data API no devolvió 'data': {request}")
            pages.append(RawPage(request, body["data"]))
            pagination = body.get("pagination") or {}
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not cursor:
                break
        return pages
