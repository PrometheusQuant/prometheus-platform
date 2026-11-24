"""Las órdenes pendientes cuentan en la exposición pre-trade (PQ-119).

Con un bróker asíncrono (Binance Demo, PQ-52) una orden enviada tarda en ejecutarse. Si el control
solo mirara las posiciones, dos compras seguidas podrían saltarse el límite por símbolo o el total.
"""

from decimal import Decimal

from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.portfolio_risk.risk import (
    Leg,
    PendingOrder,
    PortfolioSnapshot,
    Position,
    ProposedOrder,
    RiskLimits,
    RiskManager,
    flatten_orders,
)

D = Decimal
SOL = InstrumentId("SOLUSDT", Venue.BINANCE)
ETH = InstrumentId("ETHUSDT", Venue.BINANCE)
BTC = InstrumentId("BTCUSDT", Venue.BINANCE)
RISK = RiskManager(
    RiskLimits(
        max_notional_symbol=D(500),
        max_notional_total=D(1000),
        max_leverage=D(2),
        hard_leverage=D(3),
        max_daily_loss=D("0.02"),
        max_hedge_imbalance=D("0.15"),
        imbalance_grace_seconds=300,
    )
)


def libro(*pending: PendingOrder, positions: tuple[Position, ...] = ()) -> PortfolioSnapshot:
    return PortfolioSnapshot(D(1000), D(1000), positions, pending=pending)


def compra(instrument: InstrumentId, symbol: str, qty: str) -> ProposedOrder:
    return ProposedOrder("x", instrument, symbol, Leg.SPOT, Side.BUY, D(qty), D(100))


def pendiente(instrument: InstrumentId, symbol: str, qty: str, price: str = "100") -> PendingOrder:
    return PendingOrder(instrument, symbol, Leg.SPOT, D(qty), D(price))


def test_una_compra_pendiente_cuenta_para_el_limite_por_simbolo() -> None:
    # Sin posición, 400 USD pendientes de SOL: otra compra de 200 dejaría 600 > 500.
    decision = RISK.pre_trade(
        compra(SOL, "SOLUSDT", "2"), libro(pendiente(SOL, "SOLUSDT", "4")), kill_switch_active=False
    )
    assert (decision.approved, decision.rule) == (False, "nocional_simbolo")
    # Sin la pendiente, la misma compra se aprueba.
    assert RISK.pre_trade(compra(SOL, "SOLUSDT", "2"), libro(), kill_switch_active=False).approved


def test_las_pendientes_de_otros_simbolos_cuentan_para_el_total() -> None:
    book = libro(pendiente(SOL, "SOLUSDT", "4.5"), pendiente(ETH, "ETHUSDT", "4.5"))
    decision = RISK.pre_trade(compra(BTC, "BTCUSDT", "2"), book, kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "nocional_total")  # 900 + 200 > 1000


def test_la_pendiente_se_valora_al_precio_mas_conservador() -> None:
    # Posición de 1 SOL a 100 y pendiente de 3 a 150: comprometido 4 x 150 = 600 > 500.
    book = libro(
        pendiente(SOL, "SOLUSDT", "3", price="150"),
        positions=(Position(SOL, "SOLUSDT", Leg.SPOT, D(1), D(100)),),
    )
    assert book.committed_notional_by_symbol() == {"SOLUSDT": D(600)}
    decision = RISK.pre_trade(compra(SOL, "SOLUSDT", "0.1"), book, kill_switch_active=False)
    assert decision.rule == "nocional_simbolo"


def test_una_venta_pendiente_que_reduce_no_se_cuenta_como_exposicion_nueva() -> None:
    book = libro(
        pendiente(SOL, "SOLUSDT", "-4"),
        positions=(Position(SOL, "SOLUSDT", Leg.SPOT, D(4), D(100)),),
    )
    assert book.committed_quantity(SOL) == 0
    assert book.committed_notional_by_symbol() == {"SOLUSDT": D(0)}
    assert RISK.pre_trade(compra(BTC, "BTCUSDT", "4"), book, kill_switch_active=False).approved


def test_flatten_cierra_tambien_lo_que_solo_esta_pendiente() -> None:
    book = libro(
        pendiente(ETH, "ETHUSDT", "2", price="120"),
        positions=(Position(SOL, "SOLUSDT", Leg.SPOT, D(3), D(100)),),
    )
    orders = {o.instrument: o for o in flatten_orders(book)}
    assert set(orders) == {SOL, ETH}
    assert (orders[ETH].side, orders[ETH].quantity, orders[ETH].price) == (Side.SELL, D(2), D(120))
    assert (orders[SOL].side, orders[SOL].quantity) == (Side.SELL, D(3))
