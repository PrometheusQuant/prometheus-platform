"""Mercado en vivo por websocket con respaldo REST (PQ-80).

Cumple ``LiveMarket`` y ``MarketDataFeed``.

- **Streams públicos de Binance** (sin claves), en un hilo aparte:
  - ``<s>@markPrice@1s`` en futuros: mark price y funding estimado de la próxima liquidación;
  - ``<s>@miniTicker`` en spot: último precio;
  - ``<s>@kline_1h`` en futuros: velas de 1 h, para **detectar huecos** (una vela cerrada que no
    sigue a la anterior se registra como ``market_stream_gap``).
- **Reconexión** con espera creciente (1, 2, 4… hasta 60 s). Las URL se cambian para Demo Trading
  (``wss://demo-fstream.binance.com``).
- **El runner usa el stream si está sano y cae a REST si no.** Un precio con más de ``max_age``
  (15 s por defecto) no se usa: se pide a la API REST y se registra el cambio
  (``market_stream_fallback``) una vez por transición, igual que la vuelta
  (``market_stream_recovered``).
- Las liquidaciones ya ocurridas, el historial y las velas para las estrategias siguen saliendo de
  REST: el stream solo trae estimaciones y precios.

El estado del runner vive en el diario y el bróker, no en el stream: un corte de red solo cambia de
dónde salen los precios (la prueba de caos lo comprueba).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from prometheus_platform.adapters.binance_public_market import BinancePublicMarket
from prometheus_platform.domain.model import Bar, FundingRate, InstrumentId
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import get_logger

# Los streams de mercado de USDⓈ-M van por ``/market`` (verificado el 22-nov-2026): la ruta antigua
# abre la conexión pero no envía nada. Ver KE-018.
FUTURES_WS = "wss://fstream.binance.com/market"
SPOT_WS = "wss://stream.binance.com:9443"
MAX_AGE = timedelta(seconds=15)
HOUR_MS = 3_600_000
log = get_logger(component="binance_ws_market")


@dataclass
class _Quote:
    spot: Decimal | None = None
    mark: Decimal | None = None
    estimated_funding: Decimal | None = None
    spot_at: datetime | None = None
    mark_at: datetime | None = None
    last_kline_open: int | None = None


@dataclass
class StreamCache:
    """Últimos precios por símbolo, compartidos entre el hilo del stream y el runner."""

    quotes: dict[str, _Quote] = field(default_factory=dict)
    gaps: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def fresh_prices(
        self, symbol: str, now: datetime, max_age: timedelta
    ) -> tuple[Decimal, Decimal] | None:
        with self.lock:
            q = self.quotes.get(symbol)
            if (
                q is None
                or q.spot is None
                or q.mark is None
                or q.spot_at is None
                or q.mark_at is None
            ):
                return None
            if now - min(q.spot_at, q.mark_at) > max_age:
                return None
            return q.spot, q.mark

    def estimated_funding(self, symbol: str) -> Decimal | None:
        with self.lock:
            q = self.quotes.get(symbol)
            return None if q is None else q.estimated_funding


def apply_message(cache: StreamCache, raw: str | bytes, now: datetime) -> None:
    """Aplica un mensaje combinado de Binance (``{"stream": ..., "data": {...}}``) a la caché."""
    message: dict[str, Any] = json.loads(raw)
    data = message.get("data", message)
    event = data.get("e")
    symbol = str(data.get("s", "")).upper()
    if not symbol:
        return
    with cache.lock:
        q = cache.quotes.setdefault(symbol, _Quote())
        if event == "markPriceUpdate":
            q.mark, q.mark_at = Decimal(str(data["p"])), now
            q.estimated_funding = (
                Decimal(str(data["r"])) if data.get("r") not in (None, "") else None
            )
        elif event == "24hrMiniTicker":
            q.spot, q.spot_at = Decimal(str(data["c"])), now
        elif event == "kline" and data["k"].get("x"):  # solo velas cerradas
            opened = int(data["k"]["t"])
            if q.last_kline_open is not None and opened != q.last_kline_open + HOUR_MS:
                cache.gaps += 1
                log.warning(
                    "market_stream_gap",
                    symbol=symbol,
                    expected=q.last_kline_open + HOUR_MS,
                    received=opened,
                )
            q.last_kline_open = opened


class _Connection(Protocol):
    def recv(self, timeout: float | None = None) -> str | bytes: ...


Connect = Callable[[str], AbstractContextManager[_Connection]]


def stream_urls(
    symbols: Sequence[str], futures_ws: str = FUTURES_WS, spot_ws: str = SPOT_WS
) -> list[str]:
    lower = [s.lower() for s in symbols]
    futures = "/".join(f"{s}@markPrice@1s/{s}@kline_1h" for s in lower)
    spot = "/".join(f"{s}@miniTicker" for s in lower)
    return [f"{futures_ws}/stream?streams={futures}", f"{spot_ws}/stream?streams={spot}"]


class StreamWorker:
    """Un hilo por URL que lee el stream y reconecta con espera creciente."""

    def __init__(  # noqa: PLR0913 - keyword-only: conexión, reloj y espera inyectables para pruebas
        self,
        cache: StreamCache,
        urls: Iterable[str],
        *,
        connect: Connect,
        clock: Clock,
        sleep: Callable[[float], None] = time.sleep,
        max_backoff: float = 60.0,
        idle_timeout: float = 30.0,
    ) -> None:
        self._cache, self._urls = cache, list(urls)
        self._connect, self._clock, self._sleep = connect, clock, sleep
        self._max_backoff = max_backoff
        # Un stream que abre pero calla (KE-018) cuenta como corte: se reconecta.
        self._idle = idle_timeout
        self._stop = threading.Event()
        self.reconnects = 0

    def run_url(self, url: str, max_attempts: int | None = None) -> None:
        backoff, attempts = 1.0, 0
        while not self._stop.is_set() and (max_attempts is None or attempts < max_attempts):
            attempts += 1
            try:
                with self._connect(url) as connection:
                    backoff = 1.0
                    while not self._stop.is_set():
                        raw = connection.recv(timeout=self._idle)  # TimeoutError: reconectar
                        try:
                            apply_message(self._cache, raw, self._clock.now())
                        except (ValueError, KeyError, TypeError, ArithmeticError):
                            log.warning("market_stream_bad_message")
            except Exception as exc:  # cualquier corte: se reconecta, nunca tumba el runner
                log.warning(
                    "market_stream_disconnected",
                    url=url.split("?", maxsplit=1)[0],
                    error=type(exc).__name__,
                )
            if self._stop.is_set():
                return
            self.reconnects += 1
            self._sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)

    def start(self) -> None:
        for url in self._urls:
            threading.Thread(
                target=self.run_url, args=(url,), daemon=True, name="market-stream"
            ).start()

    def stop(self) -> None:
        self._stop.set()


class StreamingMarket:
    """``LiveMarket``: precios del stream si están frescos; si no, de REST (y lo registra)."""

    def __init__(
        self,
        rest: BinancePublicMarket,
        cache: StreamCache,
        clock: Clock,
        max_age: timedelta = MAX_AGE,
    ) -> None:
        self._rest, self._cache, self._clock, self._max_age = rest, cache, clock, max_age
        self._degraded: set[str] = set()

    def prices(self, symbol: str) -> tuple[Decimal, Decimal]:
        quote = self._cache.fresh_prices(symbol, self._clock.now(), self._max_age)
        if quote is not None:
            if symbol in self._degraded:
                self._degraded.discard(symbol)
                log.info("market_stream_recovered", symbol=symbol)
            return quote
        if symbol not in self._degraded:
            self._degraded.add(symbol)
            log.warning(
                "market_stream_fallback", symbol=symbol, detail="precio del stream viejo: REST"
            )
        return self._rest.prices(symbol)

    def recent_funding(self, symbol: str, limit: int) -> list[FundingRate]:
        return self._rest.recent_funding(symbol, limit)

    def bars(self, instrument: InstrumentId, start: datetime, end: datetime) -> list[Bar]:
        return self._rest.bars(instrument, start, end)

    def funding_rates(
        self, instrument: InstrumentId, start: datetime, end: datetime
    ) -> list[FundingRate]:
        return self._rest.funding_rates(instrument, start, end)

    def degraded(self) -> frozenset[str]:
        return frozenset(self._degraded)


def connect_websocket(url: str) -> AbstractContextManager[_Connection]:
    """Conexión real (``websockets``, cliente síncrono). Las pruebas inyectan una falsa."""
    from websockets.sync.client import connect  # noqa: PLC0415 - solo si se usa el stream

    return connect(url, open_timeout=10, close_timeout=5)
