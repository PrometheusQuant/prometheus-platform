"""Mercado en vivo desde la API pública de Binance, sin claves (PQ-54).

- Precio spot: ``GET /api/v3/ticker/price``.
- Mark price del perpetuo: ``GET /fapi/v1/premiumIndex``.
- Liquidaciones recientes: ``GET /fapi/v1/fundingRate``. El intervalo de cada liquidación se
  deduce de la distancia a la anterior; si no se puede, se usa el actual de
  ``GET /fapi/v1/fundingInfo`` (8 h si el símbolo no aparece, igual que en la ingesta, PQ-65).

Solo devuelve liquidaciones **ya ocurridas** (``fundingTime <= ahora``): nunca una tasa estimada.

También implementa ``MarketDataFeed`` para el ejecutor genérico de señales (PQ-116):

- ``bars``: velas de **1 h** ya cerradas (``GET /api/v3/klines`` o ``/fapi/v1/klines``). Como en el
  silver, la vela se conoce al cerrar: ``close_time = open_time + 1 h``.
- ``funding_rates``: liquidaciones de un rango, con el mismo intervalo por fila que
  ``recent_funding``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from prometheus_platform.domain.model import Bar, FundingRate, InstrumentId
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.strategies.carry import is_perp, perp_instrument, symbol_of

SPOT_API = "https://api.binance.com"
FUTURES_API = "https://fapi.binance.com"
DEFAULT_INTERVAL_HOURS = 8
VALID_INTERVALS = (1, 2, 4, 8)
INTERVALS_TTL = timedelta(hours=1)
HOUR_MS = 3_600_000
PAGE = 1000  # filas por petición de klines y fundingRate
MAX_PAGES = 20  # tope de seguridad: 20 000 velas son más de 2 años de historia horaria
log = get_logger(component="binance_public_market")


def _to_hour(funding_ms: int) -> datetime:
    """``fundingTime`` trae milisegundos de jitter: se redondea a la hora más cercana (silver)."""
    rounded = (funding_ms + HOUR_MS // 2) // HOUR_MS * HOUR_MS
    return datetime.fromtimestamp(rounded / 1000, tz=UTC)


class MarketDataError(RuntimeError):
    """La API pública no respondió como se esperaba: este ciclo no decide."""


class BinancePublicMarket:
    def __init__(self, client: httpx.Client, clock: Clock) -> None:
        self._client = client
        self._clock = clock
        self._intervals: dict[str, int] = {}
        self._intervals_at: datetime | None = None

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        spot = self._get_dict(f"{SPOT_API}/api/v3/ticker/price", symbol=symbol)
        perp = self._get_dict(f"{FUTURES_API}/fapi/v1/premiumIndex", symbol=symbol)
        return Decimal(str(spot["price"])), Decimal(str(perp["markPrice"]))

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        """Liquidaciones ya ocurridas, con el intervalo **de cada una**.

        El intervalo cambia con el tiempo (Binance lo acorta en episodios de tasas extremas), y la
        tasa se anualiza con el suyo, como en el silver. Se deduce de la distancia a la liquidación
        anterior; la primera de la ventana, o una distancia que no es un intervalo válido (un
        hueco), usa el intervalo actual de ``fundingInfo``.
        """
        rows = self._get_list(f"{FUTURES_API}/fapi/v1/fundingRate", symbol=symbol, limit=limit)
        return self._settlements(symbol, rows)

    def funding_rates(
        self, instrument: InstrumentId, start: datetime, end: datetime
    ) -> list[FundingRate]:
        """Liquidaciones ya ocurridas con ``start <= funding_time <= end``."""
        if not is_perp(instrument):
            return []
        symbol = symbol_of(instrument)
        rows = self._pages(
            f"{FUTURES_API}/fapi/v1/fundingRate",
            symbol,
            start,
            end,
            lambda row: int(row["fundingTime"]),
        )
        return [r for r in self._settlements(symbol, rows) if start <= r.funding_time <= end]

    def bars(self, instrument: InstrumentId, start: datetime, end: datetime) -> list[Bar]:
        """Velas de 1 h **ya cerradas** que abren en ``[start, end)``."""
        symbol = symbol_of(instrument)
        url = (
            f"{FUTURES_API}/fapi/v1/klines" if is_perp(instrument) else f"{SPOT_API}/api/v3/klines"
        )
        now = self._clock.now()
        rows = self._pages(url, symbol, start, end, lambda row: int(row[0]), interval="1h")
        bars: dict[datetime, Bar] = {}
        for row in rows:
            opened = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
            closed = opened + timedelta(hours=1)
            if not start <= opened < end or closed > now:
                continue  # fuera del rango, o la vela en curso: aún no se conoce
            bars[opened] = Bar(
                instrument=instrument,
                open_time=opened,
                close_time=closed,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
        return [bars[t] for t in sorted(bars)]

    def _pages(
        self,
        url: str,
        symbol: str,
        start: datetime,
        end: datetime,
        time_of: Callable[[Any], int],
        **extra: str,
    ) -> list[Any]:
        """Pide el rango por páginas de ``PAGE`` filas, avanzando desde la última fila recibida."""
        cursor, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        rows: list[Any] = []
        for _ in range(MAX_PAGES):
            page = self._get_list(
                url, symbol=symbol, startTime=cursor, endTime=end_ms, limit=PAGE, **extra
            )
            rows += page
            if len(page) < PAGE:
                return rows
            last = time_of(page[-1])
            if last < cursor:  # la API no avanza: mejor fallar que pedir en bucle
                raise MarketDataError(f"{url}: la paginación no avanza")
            cursor = last + 1
        raise MarketDataError(f"{url}: el rango pide más de {MAX_PAGES} páginas")

    def _settlements(self, symbol: str, rows: list[Any]) -> list[FundingRate]:
        now = self._clock.now()
        current = self._interval(symbol)
        parsed = sorted(
            (_to_hour(int(row["fundingTime"])), Decimal(str(row["fundingRate"]))) for row in rows
        )
        settlements = []
        previous: datetime | None = None
        for at, rate in parsed:
            if at > now:
                continue
            gap = None if previous is None else (at - previous) // timedelta(hours=1)
            settlements.append(
                FundingRate(
                    instrument=perp_instrument(symbol),
                    funding_time=at,
                    rate=rate,
                    interval_hours=gap if gap in VALID_INTERVALS else current,
                )
            )
            previous = at
        return settlements

    def _interval(self, symbol: str) -> int:
        now = self._clock.now()
        if self._intervals_at is None or now - self._intervals_at >= INTERVALS_TTL:
            try:
                info = self._get_list(f"{FUTURES_API}/fapi/v1/fundingInfo")
            except MarketDataError:
                if self._intervals_at is None:
                    raise
                # Mejor el intervalo de hace una hora que dejar de liquidar: se reintenta luego.
                log.warning("funding_info_stale", symbol=symbol)
                return self._intervals.get(symbol, DEFAULT_INTERVAL_HOURS)
            self._intervals = {
                str(r["symbol"]): int(r["fundingIntervalHours"])
                for r in info
                if "fundingIntervalHours" in r
            }
            self._intervals_at = now
        return self._intervals.get(symbol, DEFAULT_INTERVAL_HOURS)

    def _get(self, url: str, **params: str | int) -> Any:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataError(f"{url}: {type(exc).__name__}") from exc

    def _get_dict(self, url: str, **params: str | int) -> dict[str, Any]:
        data = self._get(url, **params)
        if not isinstance(data, dict):
            raise MarketDataError(f"{url}: se esperaba un objeto")
        return data

    def _get_list(self, url: str, **params: str | int) -> list[Any]:
        data = self._get(url, **params)
        if not isinstance(data, list):
            raise MarketDataError(f"{url}: se esperaba una lista")
        return data
