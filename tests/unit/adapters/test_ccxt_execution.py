"""Adaptador de ejecución sobre CCXT (PQ-52) contra un doble en memoria del exchange."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import ccxt
import pytest

from prometheus_platform.adapters.ccxt_execution import (
    CLOCK_MARGIN_MS,
    CcxtExecution,
    ExecutionError,
    OrderTooSmallError,
    exchange_order_id,
    require_test_endpoints,
)
from prometheus_platform.domain.model import Side
from prometheus_platform.strategies.carry import perp_instrument, spot_instrument

T0 = datetime(2026, 11, 24, 12, tzinfo=UTC)
SPOT, PERP = spot_instrument("SOLUSDT"), perp_instrument("SOLUSDT")
SECRET = "s3cr3t-" + "valor-de-prueba"  # concatenado: el hook no lo toma por un secreto real


class FakeExchange:
    """Lo mínimo de CCXT/Binance: filtros, órdenes de mercado, operaciones y comisiones."""

    def __init__(self) -> None:
        base = {"id": "SOLUSDT", "base": "SOL", "quote": "USDT"}
        self.markets: dict[str, Any] = {
            "SOL/USDT": {
                **base,
                "symbol": "SOL/USDT",
                "spot": True,
                "step": "0.001",
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5}},
            },
            "SOL/USDT:USDT": {
                **base,
                "symbol": "SOL/USDT:USDT",
                "swap": True,
                "linear": True,
                "settle": "USDT",
                "step": "0.01",
                "limits": {"amount": {"min": 0.01}, "cost": {"min": 5}},
            },
        }
        self.options: dict[str, Any] = {}
        self.last = 100.0
        self.orders: dict[str, dict[str, Any]] = {}
        self.by_client: dict[str, str] = {}
        self.trades: dict[str, list[dict[str, Any]]] = {}
        self.creates = 0
        self.syncs = 0
        self.ack_perp = False
        self.lose_response: Exception | None = None  # la orden llega, la respuesta no
        self.fail_before: Exception | None = None  # la orden no llega
        self.open: dict[str, list[dict[str, Any]]] = {}
        self.cancelled: list[str] = []

    def load_markets(self) -> Any:
        return self.markets

    def load_time_difference(self) -> Any:
        self.syncs += 1
        self.options["timeDifference"] = -1200  # reloj local 1,2 s atrasado
        return -1200

    def amount_to_precision(self, symbol: str, amount: Any) -> str:
        step = Decimal(self.markets[symbol]["step"])
        rounded = (Decimal(str(amount)) // step) * step
        if rounded == 0:
            raise ccxt.InvalidOrder("amount must be greater than minimum amount precision")
        return str(rounded)

    def create_order(  # noqa: PLR0913, PLR0917 - firma de CCXT
        self,
        symbol: str,
        type: str,
        side: str,
        amount: Any,
        price: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.fail_before is not None:
            exc, self.fail_before = self.fail_before, None
            raise exc
        self.creates += 1
        client_id = (params or {})["newClientOrderId"]
        if client_id in self.by_client:
            raise ccxt.InvalidOrder("Duplicate order sent.")
        oid = str(len(self.orders) + 1)
        qty = float(amount)
        market = self.markets[symbol]
        if market.get("spot") and side == "buy":
            fee = {"cost": qty * 0.001, "currency": "SOL"}
        else:
            rate = 0.001 if market.get("spot") else 0.0005
            fee = {"cost": qty * self.last * rate, "currency": "USDT"}
        self.trades[oid] = [{"amount": qty, "price": self.last, "fee": fee}]
        status = "open" if self.ack_perp and not market.get("spot") else "closed"
        self.orders[oid] = {"id": oid, "status": status, "filled": qty}
        self.by_client[client_id] = oid
        if self.lose_response is not None:
            exc, self.lose_response = self.lose_response, None
            raise exc
        return dict(self.orders[oid])

    def fetch_order(
        self,
        id: str,
        symbol: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client_id = (params or {}).get("origClientOrderId")
        oid = self.by_client.get(client_id, "") if client_id else id
        if oid not in self.orders:
            raise ccxt.OrderNotFound("Order does not exist.")
        self.orders[oid]["status"] = "closed"
        return dict(self.orders[oid])

    def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.trades.get((params or {})["orderId"], [])

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if (params or {}).get("type") == "future":
            return {"USDT": {"free": 4800.0, "total": 5000.0}}
        return {"USDT": {"free": 5000.0, "total": 5000.0}, "SOL": {"free": 1.5, "total": 1.5}}

    def fetch_positions(
        self, symbols: list[str] | None = None, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return [{"symbol": "SOL/USDT:USDT", "contracts": 1.5, "side": "short"}]

    def fetch_ticker(self, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"last": self.last}

    def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.open.get(symbol or "", [])

    def cancel_all_orders(
        self, symbol: str | None = None, params: dict[str, Any] | None = None
    ) -> Any:
        self.cancelled.append(symbol or "")

    def fetch_funding_history(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [{"timestamp": int(T0.timestamp() * 1000), "amount": 0.125}]


class Clock:
    def __init__(self) -> None:
        self.t = T0

    def now(self) -> datetime:
        return self.t


def make(fake: FakeExchange, clock: Clock | None = None) -> CcxtExecution:
    return CcxtExecution(
        fake, name="binance-demo", clock=clock or Clock(), secrets=(SECRET,), sleep=lambda _: None
    )


def test_client_order_ids_fit_the_exchange_and_stay_deterministic() -> None:
    assert exchange_order_id("carry-20261124T120000-SOLUSDT") == "carry-20261124T120000-SOLUSDT"
    long_id = "carry-h2-rebalance-20261124T120000-SOLUSDT-PERP"
    hashed = exchange_order_id(long_id)
    assert hashed == exchange_order_id(long_id)  # un reintento usa el mismo id
    assert len(hashed) <= 36
    assert hashed.startswith("pq-")
    assert exchange_order_id("con espacio") != "con espacio"


def test_only_test_endpoints_are_accepted() -> None:
    require_test_endpoints({"private": "https://demo-api.binance.com/api/v3"}, "://demo-")
    with pytest.raises(ExecutionError, match="fuera del entorno"):
        require_test_endpoints(
            {"private": "https://demo-api.binance.com/api/v3", "sapi": "https://api.binance.com"},
            "://demo-",
        )
    with pytest.raises(ExecutionError):
        require_test_endpoints({}, "://demo-")


def test_binance_demo_points_only_at_demo_hosts() -> None:
    """El constructor real activa el Demo Trading: ninguna URL de la API apunta a producción."""
    exchange = ccxt.binance()
    exchange.enable_demo_trading(True)
    require_test_endpoints(exchange.urls["api"], "://demo-")


def test_spot_buy_nets_the_fee_charged_in_the_bought_asset() -> None:
    fill = make(FakeExchange()).market_order("c1", SPOT, Side.BUY, Decimal("0.2"))
    assert fill.quantity == Decimal("0.2") - Decimal("0.0002")  # 0,1 % cobrado en SOL
    assert fill.price == Decimal(100)
    assert fill.fee == Decimal("0.0002") * 100  # valorada en USDT al precio medio
    assert fill.client_order_id == "c1"


def test_perp_sell_waits_for_the_fill_and_charges_fee_in_usdt() -> None:
    fake = FakeExchange()
    fake.ack_perp = True  # futuros responden NEW y hay que consultar
    fill = make(fake).market_order("c2", PERP, Side.SELL, Decimal("0.129"))
    assert fill.quantity == Decimal("0.12")  # truncada al paso de 0,01
    assert fill.fee == Decimal("0.12") * 100 * Decimal("0.0005")


def test_orders_below_the_exchange_minimums_are_refused() -> None:
    gateway = make(FakeExchange())
    with pytest.raises(OrderTooSmallError, match="redondear"):
        gateway.market_order("c3", PERP, Side.SELL, Decimal("0.004"))
    with pytest.raises(OrderTooSmallError, match="nocional"):
        gateway.market_order("c4", SPOT, Side.BUY, Decimal("0.04"))  # 4 USDT < 5
    with pytest.raises(OrderTooSmallError):
        gateway.market_order("c5", SPOT, Side.BUY, Decimal(0))


def test_a_lost_response_does_not_duplicate_the_order() -> None:
    fake = FakeExchange()
    fake.lose_response = ccxt.RequestTimeout("timeout")
    fill = make(fake).market_order("c6", SPOT, Side.BUY, Decimal("0.2"))
    assert fake.creates == 1  # se encontró por el id, no se reenvió
    assert fill.exchange_order_id == "1"


def test_an_order_that_never_arrived_is_sent_again() -> None:
    fake = FakeExchange()
    fake.fail_before = ccxt.NetworkError("connection reset")
    make(fake).market_order("c7", SPOT, Side.BUY, Decimal("0.2"))
    assert fake.creates == 1
    assert len(fake.orders) == 1


def test_errors_leave_the_adapter_without_secrets() -> None:
    fake = FakeExchange()
    fake.fail_before = ccxt.AuthenticationError(f"invalid api key {SECRET}")
    with pytest.raises(ExecutionError) as caught:
        make(fake).market_order("c8", SPOT, Side.BUY, Decimal("0.2"))
    assert SECRET not in str(caught.value)
    assert "AuthenticationError" in str(caught.value)


def test_clock_is_synced_with_a_margin_and_resynced_every_ten_minutes() -> None:
    fake, clock = FakeExchange(), Clock()
    gateway = make(fake, clock)
    gateway.market_order("c9", SPOT, Side.BUY, Decimal("0.2"))
    assert fake.options["timeDifference"] == -1200 + CLOCK_MARGIN_MS  # firma 1 s por detrás
    clock.t += timedelta(minutes=5)
    gateway.market_order("c10", SPOT, Side.SELL, Decimal("0.1"))
    assert fake.syncs == 1
    clock.t += timedelta(minutes=10)
    gateway.market_order("c11", SPOT, Side.SELL, Decimal("0.1"))
    assert fake.syncs == 2


def test_positions_balances_and_funding_come_from_the_exchange() -> None:
    gateway = make(FakeExchange())
    assert gateway.positions([SPOT, PERP]) == {SPOT: Decimal("1.5"), PERP: Decimal("-1.5")}
    assert gateway.balance("USDT", perp=True) == Decimal(4800)
    assert gateway.balance("USDT", perp=False) == Decimal(5000)
    assert gateway.price(SPOT) == Decimal(100)
    assert gateway.funding_income(PERP, T0 - timedelta(days=1)) == [(T0, Decimal("0.125"))]


def test_unknown_instruments_are_refused() -> None:
    with pytest.raises(ExecutionError, match="sin mercado"):
        make(FakeExchange()).price(spot_instrument("DOGEUSDT"))


def test_cancel_all_touches_only_traded_symbols_with_open_orders() -> None:
    fake = FakeExchange()
    gateway = make(fake)
    gateway.market_order("c12", SPOT, Side.BUY, Decimal("0.2"))
    gateway.market_order("c13", PERP, Side.SELL, Decimal("0.2"))
    fake.open["SOL/USDT:USDT"] = [{"id": "9"}]
    gateway.cancel_all()
    assert fake.cancelled == ["SOL/USDT:USDT"]
