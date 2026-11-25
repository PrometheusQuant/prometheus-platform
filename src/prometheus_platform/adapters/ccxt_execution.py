"""Ejecución real con CCXT en entornos de prueba (PQ-52, ADR-0014).

Implementa ``ExecutionPort`` sobre una instancia de CCXT. Hoy se usa con Binance Demo (spot y
USDⓈ-M); Bybit testnet (PQ-100) será otra instancia con otras URLs.

Lo que el spike de PQ-51 encontró y aquí se resuelve:

- **Solo entornos de prueba.** El constructor de Binance activa el Demo Trading y comprueba que
  **todas** las URLs de la API apuntan a ``demo-``; si no, no arranca.
- **Reloj.** El reloj de WSL va hasta 1,4 s atrasado y Binance rechaza timestamps adelantados más
  de 1 s. Se sincroniza cada 10 minutos y se resta un margen de 1 s, con ``recvWindow`` de 10 s.
- **Redondeo.** La cantidad se trunca al ``stepSize`` del par y se rechaza si queda por debajo
  de la cantidad o el nocional mínimos (``OrderTooSmallError``).
- **Idempotencia.** Cada orden lleva su ``clientOrderId``. Si la red falla al enviarla, primero se
  busca por ese id y solo se reenvía si el exchange no la tiene.
- **Comisiones reales.** Se suman de las operaciones de la orden. Si se cobran en el activo
  comprado (compra spot sin BNB), la cantidad neta las descuenta y se valoran al precio medio.
- **Secretos.** Los mensajes de error pasan por ``redact_text`` y además se borran las claves
  literales antes de salir del adaptador.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, Protocol, TypeVar

import ccxt

from prometheus_platform.domain.model import ExchangeFill, InstrumentId, Side, Venue
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import REDACTED, get_logger, redact_text
from prometheus_platform.strategies.carry import is_perp

log = get_logger()

CLOCK_MARGIN_MS = 1_000
RECV_WINDOW_MS = 10_000
CLOCK_RESYNC = timedelta(minutes=10)
FILL_POLLS = 10
POLL_SECONDS = 0.5
_EXCHANGE_ID = re.compile(r"^[.A-Za-z0-9:/_-]{1,36}$")
T = TypeVar("T")


class ExecutionError(RuntimeError):
    """El exchange rechazó o no confirmó una operación. El mensaje ya no contiene secretos."""


class OrderTooSmallError(ExecutionError):
    """La cantidad, redondeada al paso del par, queda por debajo del mínimo del exchange."""


class Exchange(Protocol):
    """La parte de la API de CCXT que usa el adaptador (permite un doble en memoria)."""

    markets: dict[str, Any]
    options: dict[str, Any]

    def load_markets(self) -> Any: ...

    def load_time_difference(self) -> Any: ...

    def amount_to_precision(self, symbol: str, amount: Any) -> str: ...

    def create_order(  # noqa: PLR0913, PLR0917 - firma de CCXT
        self,
        symbol: str,
        type: str,
        side: str,
        amount: Any,
        price: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def fetch_order(
        self,
        id: str,
        symbol: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def fetch_positions(
        self, symbols: list[str] | None = None, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    def fetch_ticker(self, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def cancel_all_orders(
        self, symbol: str | None = None, params: dict[str, Any] | None = None
    ) -> Any: ...

    def fetch_funding_history(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


def exchange_order_id(client_order_id: str) -> str:
    """Id aceptado por Binance (hasta 36 caracteres de ``[.A-Za-z0-9:/_-]``), determinista."""
    if _EXCHANGE_ID.match(client_order_id):
        return client_order_id
    return "pq-" + hashlib.sha256(client_order_id.encode()).hexdigest()[:32]


def require_test_endpoints(urls: Mapping[str, Any], marker: str) -> None:
    """Lanza si alguna URL de la API no contiene ``marker`` (p. ej. ``://demo-``)."""
    found = [u for u in _strings(urls) if u.startswith("http")]
    production = [u for u in found if marker not in u]
    if not found or production:
        raise ExecutionError(f"Endpoints fuera del entorno de prueba: {production or 'ninguno'}")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in _strings(v)]
    return []


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(0)


class CcxtExecution:
    """``ExecutionPort`` sobre CCXT. Carga los mercados una vez (unos 6,5 s en Binance)."""

    def __init__(
        self,
        exchange: Exchange,
        *,
        name: str,
        clock: Clock,
        secrets: Sequence[str] = (),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self._ex = exchange
        self._clock = clock
        self._secrets = [s for s in secrets if s]
        self._sleep = sleep
        self._synced_at: datetime | None = None
        self._traded: set[InstrumentId] = set()
        self._call(self._ex.load_markets)
        self._symbols = self._symbol_map()

    @classmethod
    def binance_demo(cls, api_key: str, api_secret: str, clock: Clock) -> CcxtExecution:
        exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {
                    "adjustForTimeDifference": False,  # se sincroniza aquí, con margen
                    "recvWindow": RECV_WINDOW_MS,
                    "fetchMarkets": {"types": ["spot", "linear"]},
                },
            }
        )
        exchange.enable_demo_trading(True)
        require_test_endpoints(exchange.urls["api"], "://demo-")
        return cls(exchange, name="binance-demo", clock=clock, secrets=(api_key, api_secret))

    # --- ExecutionPort ---------------------------------------------------------------------

    def balance(self, asset: str, *, perp: bool) -> Decimal:
        params = {"type": "future"} if perp else {}
        raw = self._call(lambda: self._ex.fetch_balance(params))
        return _dec(raw.get(asset, {}).get("free"))

    def price(self, instrument: InstrumentId) -> Decimal:
        ticker = self._call(lambda: self._ex.fetch_ticker(self._symbol(instrument)))
        return _dec(ticker["last"])

    def quote(self, instrument: InstrumentId) -> tuple[Decimal, Decimal]:
        ticker = self._call(lambda: self._ex.fetch_ticker(self._symbol(instrument)))
        bid, ask = _dec(ticker.get("bid")), _dec(ticker.get("ask"))
        if bid <= 0 or ask < bid:
            raise ExecutionError(f"{instrument}: libro inválido (bid {bid}, ask {ask})")
        return bid, ask

    def market_order(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: Decimal
    ) -> ExchangeFill:
        symbol = self._symbol(instrument)
        amount = self._round(symbol, quantity)
        self._sync_clock()
        exchange_id = exchange_order_id(client_order_id)
        self._traded.add(instrument)
        order = self._submit_once(symbol, side, amount, exchange_id)
        order = self._wait_closed(symbol, order)
        return self._fill(client_order_id, instrument, side, symbol, order)

    def cancel_all(self) -> None:
        """Cancela las órdenes abiertas de cada instrumento operado en esta sesión."""
        for instrument in sorted(self._traded, key=str):
            symbol = self._symbol(instrument)
            if self._call(partial(self._ex.fetch_open_orders, symbol)):
                self._call(partial(self._ex.cancel_all_orders, symbol))

    def positions(self, instruments: Sequence[InstrumentId]) -> dict[InstrumentId, Decimal]:
        result: dict[InstrumentId, Decimal] = {}
        spot = [i for i in instruments if not is_perp(i)]
        perps = [i for i in instruments if is_perp(i)]
        if spot:
            balances = self._call(self._ex.fetch_balance)
            for instrument in spot:
                base = self._ex.markets[self._symbol(instrument)]["base"]
                qty = _dec(balances.get(base, {}).get("total"))
                if qty:
                    result[instrument] = qty
        if perps:
            symbols = [self._symbol(i) for i in perps]
            by_symbol = {self._symbol(i): i for i in perps}
            for row in self._call(lambda: self._ex.fetch_positions(symbols)):
                contracts = _dec(row.get("contracts"))
                if contracts and row.get("symbol") in by_symbol:
                    sign = -1 if row.get("side") == "short" else 1
                    result[by_symbol[row["symbol"]]] = sign * contracts
        return result

    def funding_income(
        self, instrument: InstrumentId, since: datetime
    ) -> list[tuple[datetime, Decimal]]:
        symbol = self._symbol(instrument)
        start = int(since.timestamp() * 1000)
        rows = self._call(lambda: self._ex.fetch_funding_history(symbol, start))
        return [
            (datetime.fromtimestamp(r["timestamp"] / 1000, UTC), _dec(r["amount"])) for r in rows
        ]

    # --- internos --------------------------------------------------------------------------

    def _symbol_map(self) -> dict[InstrumentId, str]:
        """``SOLUSDT`` → ``SOL/USDT`` y ``SOLUSDT-PERP`` → ``SOL/USDT:USDT``."""
        mapping: dict[InstrumentId, str] = {}
        for market in self._ex.markets.values():
            if market.get("spot"):
                mapping[InstrumentId(market["id"], Venue.BINANCE)] = market["symbol"]
            elif market.get("swap") and market.get("linear"):
                mapping[InstrumentId(f"{market['id']}-PERP", Venue.BINANCE)] = market["symbol"]
        return mapping

    def _symbol(self, instrument: InstrumentId) -> str:
        try:
            return self._symbols[InstrumentId(instrument.symbol, Venue.BINANCE)]
        except KeyError:
            raise ExecutionError(f"Instrumento sin mercado en {self.name}: {instrument}") from None

    def _round(self, symbol: str, quantity: Decimal) -> Decimal:
        if quantity <= 0:
            raise OrderTooSmallError(f"Cantidad no positiva: {quantity}")
        try:
            amount = Decimal(self._ex.amount_to_precision(symbol, str(quantity)))
        except ccxt.InvalidOrder:  # CCXT lanza si el truncado queda por debajo del mínimo
            amount = Decimal(0)
        limits = self._ex.markets[symbol].get("limits", {})
        min_amount = _dec(limits.get("amount", {}).get("min"))
        if amount <= 0 or amount < min_amount:
            raise OrderTooSmallError(f"{symbol}: {quantity} queda en {amount} al redondear")
        min_cost = _dec(limits.get("cost", {}).get("min"))
        if min_cost:
            price = self.price(InstrumentId(self._instrument_of(symbol), Venue.BINANCE))
            if amount * price < min_cost:
                raise OrderTooSmallError(
                    f"{symbol}: nocional {amount * price:.2f} por debajo del mínimo {min_cost}"
                )
        return amount

    def _instrument_of(self, symbol: str) -> str:
        return next(i.symbol for i, s in self._symbols.items() if s == symbol)

    def _sync_clock(self) -> None:
        now = self._clock.now()
        if self._synced_at is not None and now - self._synced_at < CLOCK_RESYNC:
            return
        self._call(self._ex.load_time_difference)
        # CCXT firma con ``local - timeDifference``: sumar el margen atrasa el timestamp.
        self._ex.options["timeDifference"] = self._ex.options.get("timeDifference", 0) + (
            CLOCK_MARGIN_MS
        )
        self._synced_at = now

    def _submit_once(
        self, symbol: str, side: Side, amount: Decimal, exchange_id: str
    ) -> dict[str, Any]:
        params = {"newClientOrderId": exchange_id}
        try:
            return self._ex.create_order(
                symbol, "market", side.value.lower(), str(amount), None, params
            )
        except ccxt.NetworkError as exc:
            # No se sabe si llegó: se busca por el id antes de reenviar (idempotencia).
            log.warning("execution_retry", symbol=symbol, error=self._clean(type(exc).__name__))
            existing = self._find(symbol, exchange_id)
            if existing is not None:
                return existing
            return self._call(
                lambda: self._ex.create_order(
                    symbol, "market", side.value.lower(), str(amount), None, params
                )
            )
        except ccxt.BaseError as exc:
            raise ExecutionError(self._clean(f"{type(exc).__name__}: {exc}")) from None

    def _find(self, symbol: str, exchange_id: str) -> dict[str, Any] | None:
        try:
            return self._ex.fetch_order("", symbol, {"origClientOrderId": exchange_id})
        except ccxt.OrderNotFound:
            return None
        except ccxt.BaseError as exc:
            raise ExecutionError(self._clean(f"{type(exc).__name__}: {exc}")) from None

    def _wait_closed(self, symbol: str, order: dict[str, Any]) -> dict[str, Any]:
        """Las órdenes de futuros responden ``NEW`` (ACK): se consulta hasta verla ejecutada."""
        for _ in range(FILL_POLLS):
            if order.get("status") == "closed":
                return order
            if order.get("status") in {"canceled", "rejected", "expired"}:
                raise ExecutionError(f"{symbol}: orden {order.get('id')} {order.get('status')}")
            self._sleep(POLL_SECONDS)
            order = self._call(partial(self._ex.fetch_order, str(order["id"]), symbol))
        raise ExecutionError(f"{symbol}: la orden {order.get('id')} no se ejecutó a tiempo")

    def _fill(
        self,
        client_order_id: str,
        instrument: InstrumentId,
        side: Side,
        symbol: str,
        order: dict[str, Any],
    ) -> ExchangeFill:
        filled = _dec(order.get("filled"))
        trades: list[dict[str, Any]] = []
        for _ in range(FILL_POLLS):  # las operaciones pueden tardar unos ms en aparecer
            trades = self._call(
                lambda: self._ex.fetch_my_trades(symbol, None, None, {"orderId": order["id"]})
            )
            if sum((_dec(t["amount"]) for t in trades), Decimal(0)) >= filled > 0:
                break
            self._sleep(POLL_SECONDS)
        else:
            return self._fill_from_order(client_order_id, symbol, order)
        quantity = sum((_dec(t["amount"]) for t in trades), Decimal(0))
        cost = sum((_dec(t["amount"]) * _dec(t["price"]) for t in trades), Decimal(0))
        price = cost / quantity
        market = self._ex.markets[symbol]
        fee = Decimal(0)
        net = quantity
        for trade in trades:
            for charge in trade.get("fees") or ([trade["fee"]] if trade.get("fee") else []):
                amount, currency = _dec(charge.get("cost")), charge.get("currency")
                if currency == market.get("base"):  # comisión en el activo comprado
                    net -= amount if side is Side.BUY else Decimal(0)
                    fee += amount * price
                elif currency == market.get("quote") or currency == market.get("settle"):
                    fee += amount
                elif amount:
                    log.warning("execution_fee_unvalued", symbol=symbol, currency=currency)
        return ExchangeFill(client_order_id, str(order["id"]), net, price, fee)

    def _fill_from_order(
        self, client_order_id: str, symbol: str, order: dict[str, Any]
    ) -> ExchangeFill:
        """La orden se ejecutó pero sus operaciones no aparecen: se registra con lo que dice.

        No registrarla dejaría el libro sin una posición que sí existe en el exchange, y el
        runner la volvería a pedir. Precio medio y cantidad de la orden; la comisión, si la
        trae; si no, 0 y aviso en el log (la reconciliación lo deja a la vista).
        """
        filled, average = _dec(order.get("filled")), _dec(order.get("average"))
        if filled <= 0 or average <= 0:
            raise ExecutionError(f"{symbol}: la orden {order['id']} no informa su ejecución")
        fee = order.get("fee") or {}
        quote = self._ex.markets[symbol].get("quote")
        cost = _dec(fee.get("cost")) if fee.get("currency") == quote else Decimal(0)
        log.warning("execution_fill_from_order", symbol=symbol, order_id=str(order["id"]))
        return ExchangeFill(client_order_id, str(order["id"]), filled, average, cost)

    def _call(self, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except ccxt.BaseError as exc:
            raise ExecutionError(self._clean(f"{type(exc).__name__}: {exc}")) from None

    def _clean(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return redact_text(text)
