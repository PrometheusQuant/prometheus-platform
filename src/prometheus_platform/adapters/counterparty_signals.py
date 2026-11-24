"""Señales públicas de riesgo de contraparte, sin claves (PQ-96). Cumple ``CounterpartyFeed``.

- Estado del sistema de Binance: ``GET /sapi/v1/system/status`` (``status`` 0 = normal).
- USDT frente a USDC: ``GET /api/v3/ticker/price?symbol=USDCUSDT``. La prima de USDT es
  ``1 / precio - 1`` (si 1 USDC cuesta más de 1 USDT, el USDT está con descuento).
- Perpetuo BTCUSDT: el mark de Binance frente a la mediana de Bybit (mark) y OKX (último precio).

Cada fuente se lee por separado. Si una falla, su campo queda en ``None`` y el motivo, en
``sources``: nunca lanza, porque un monitor caído no puede tumbar el runner.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from typing import Any

import httpx

from prometheus_platform.domain.counterparty import CounterpartyReading
from prometheus_platform.domain.ports import Clock

BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
OKX = "https://www.okx.com"


class PublicCounterpartySignals:
    def __init__(self, client: httpx.Client, clock: Clock) -> None:
        self._client = client
        self._clock = clock

    def read(self) -> CounterpartyReading:
        sources: dict[str, str] = {}
        system = self._guard("estado", sources, self._system_normal)
        usdt = self._guard("usdt", sources, self._usdt_premium)
        spread = self._guard("spread", sources, self._perp_spread)
        return CounterpartyReading(
            at=self._clock.now(),
            system_normal=system,
            usdt_premium=usdt,
            perp_spread=spread,
            sources=sources,
        )

    def _guard[T](self, name: str, sources: dict[str, str], fn: Callable[[], T]) -> T | None:
        try:
            return fn()
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            ZeroDivisionError,
        ) as e:
            sources[name] = type(e).__name__
            return None

    def _json(self, url: str, **params: str) -> Any:
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _system_normal(self) -> bool:
        return int(self._json(f"{BINANCE_SPOT}/sapi/v1/system/status")["status"]) == 0

    def _usdt_premium(self) -> float:
        price = float(self._json(f"{BINANCE_SPOT}/api/v3/ticker/price", symbol="USDCUSDT")["price"])
        if price <= 0:
            raise ValueError(f"precio USDCUSDT no válido: {price}")
        return 1 / price - 1

    def _perp_spread(self) -> float:
        binance = float(
            self._json(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex", symbol="BTCUSDT")["markPrice"]
        )
        others = []
        for fetch in (self._bybit, self._okx):
            try:
                others.append(fetch())
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                continue  # basta con uno de los dos para comparar
        if not others or binance <= 0:
            raise ValueError("sin precio de otro exchange para comparar")
        return binance / statistics.median(others) - 1

    def _bybit(self) -> float:
        data = self._json(f"{BYBIT}/v5/market/tickers", category="linear", symbol="BTCUSDT")
        return float(data["result"]["list"][0]["markPrice"])

    def _okx(self) -> float:
        data = self._json(f"{OKX}/api/v5/market/ticker", instId="BTC-USDT-SWAP")
        return float(data["data"][0]["last"])
