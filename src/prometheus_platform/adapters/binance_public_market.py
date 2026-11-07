"""Mercado en vivo desde la API pública de Binance, sin claves (PQ-54).

- Precio spot: ``GET /api/v3/ticker/price``.
- Mark price del perpetuo: ``GET /fapi/v1/premiumIndex``.
- Liquidaciones recientes: ``GET /fapi/v1/fundingRate``. El intervalo de cada símbolo sale de
  ``GET /fapi/v1/fundingInfo``; si no aparece ahí, es el estándar de 8 h, igual que en la ingesta
  (PQ-65).

Solo devuelve liquidaciones **ya ocurridas** (``fundingTime <= ahora``): nunca una tasa estimada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from prometheus_platform.domain.model import FundingRate
from prometheus_platform.domain.ports import Clock
from prometheus_platform.strategies.carry import perp_instrument

SPOT_API = "https://api.binance.com"
FUTURES_API = "https://fapi.binance.com"
DEFAULT_INTERVAL_HOURS = 8


class MarketDataError(RuntimeError):
    """La API pública no respondió como se esperaba: este ciclo no decide."""


class BinancePublicMarket:
    def __init__(self, client: httpx.Client, clock: Clock) -> None:
        self._client = client
        self._clock = clock
        self._intervals: dict[str, int] | None = None

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        spot = self._get_dict(f"{SPOT_API}/api/v3/ticker/price", symbol=symbol)
        perp = self._get_dict(f"{FUTURES_API}/fapi/v1/premiumIndex", symbol=symbol)
        return Decimal(str(spot["price"])), Decimal(str(perp["markPrice"]))

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        rows = self._get_list(f"{FUTURES_API}/fapi/v1/fundingRate", symbol=symbol, limit=limit)
        now = self._clock.now()
        interval = self._interval(symbol)
        settlements = []
        for row in rows:
            at = datetime.fromtimestamp(int(row["fundingTime"]) / 1000, tz=UTC)
            # La API redondea fundingTime al milisegundo de la liquidación; se lleva a la hora.
            at = at.replace(second=0, microsecond=0)
            if at > now:
                continue
            settlements.append(
                FundingRate(
                    instrument=perp_instrument(symbol),
                    funding_time=at,
                    rate=Decimal(str(row["fundingRate"])),
                    interval_hours=interval,
                )
            )
        return sorted(settlements, key=lambda r: r.funding_time)

    def _interval(self, symbol: str) -> int:
        if self._intervals is None:
            info = self._get_list(f"{FUTURES_API}/fapi/v1/fundingInfo")
            self._intervals = {
                str(r["symbol"]): int(r["fundingIntervalHours"])
                for r in info
                if "fundingIntervalHours" in r
            }
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
