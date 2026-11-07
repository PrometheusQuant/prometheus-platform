"""Mercado en vivo desde la API pública de Binance, sin claves (PQ-54).

- Precio spot: ``GET /api/v3/ticker/price``.
- Mark price del perpetuo: ``GET /fapi/v1/premiumIndex``.
- Liquidaciones recientes: ``GET /fapi/v1/fundingRate``. El intervalo de cada liquidación se
  deduce de la distancia a la anterior; si no se puede, se usa el actual de
  ``GET /fapi/v1/fundingInfo`` (8 h si el símbolo no aparece, igual que en la ingesta, PQ-65).

Solo devuelve liquidaciones **ya ocurridas** (``fundingTime <= ahora``): nunca una tasa estimada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from prometheus_platform.domain.model import FundingRate
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import get_logger
from prometheus_platform.strategies.carry import perp_instrument

SPOT_API = "https://api.binance.com"
FUTURES_API = "https://fapi.binance.com"
DEFAULT_INTERVAL_HOURS = 8
VALID_INTERVALS = (1, 2, 4, 8)
INTERVALS_TTL = timedelta(hours=1)
HOUR_MS = 3_600_000
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

    def _get_list(self, url: str, **params: str | int) -> list[dict[str, Any]]:
        data = self._get(url, **params)
        if not isinstance(data, list):
            raise MarketDataError(f"{url}: se esperaba una lista")
        return data
