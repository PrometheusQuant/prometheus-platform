"""Calibración de costes con fills reales (PQ-95): slippage y comisión por orden y por pata."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from prometheus_platform.domain.events import OrderFilled, OrderSubmitted
from prometheus_platform.domain.model import InstrumentId, Side, Venue
from prometheus_platform.research.backtest import CostModel
from prometheus_platform.research.cost_calibration import (
    order_costs,
    render_markdown,
    summarize,
    to_json,
)

T0 = datetime(2026, 11, 25, 12, tzinfo=UTC)
SPOT = InstrumentId("SOLUSDT", Venue.BINANCE)
PERP = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
ALT = CostModel(spot_fee=0.001, perp_fee=0.0005, slippage=0.0005)


def costs_for(symbol: str) -> CostModel:
    assert symbol == "SOLUSDT"  # el sufijo -PERP se quita antes de pedir el modelo
    return ALT


def order(cid: str, instrument: InstrumentId, side: Side, qty: str) -> OrderSubmitted:
    return OrderSubmitted(
        occurred_at=T0, client_order_id=cid, instrument=instrument, side=side, quantity=Decimal(qty)
    )


def fill(cid: str, price: str, qty: str, fee: str, slippage: str) -> OrderFilled:
    return OrderFilled(
        occurred_at=T0,
        client_order_id=cid,
        fill_price=Decimal(price),
        fill_quantity=Decimal(qty),
        fee=Decimal(fee),
        slippage=Decimal(slippage),
    )


def journal() -> list[OrderSubmitted | OrderFilled]:
    return [
        # Compra spot de 2 a 100,10 con referencia 100: slippage +0,20 USD = 10 pb de coste.
        order("a", SPOT, Side.BUY, "2"),
        fill("a", "100.10", "2", "0.2002", "0.20"),
        # Venta perp de 1 a 99,98 con referencia 100: vender más barato también es coste (+2 pb).
        order("b", PERP, Side.SELL, "1"),
        fill("b", "99.98", "1", "0.04999", "0.02"),
        # Venta perp a 100,03: mejor que la referencia, slippage negativo (-3 pb).
        order("c", PERP, Side.SELL, "1"),
        fill("c", "100.03", "1", "0.050015", "-0.03"),
        fill("huerfano", "100", "1", "0.05", "0"),  # sin su OrderSubmitted: se ignora
        order("d", PERP, Side.BUY, "1"),
        fill("d", "100", "0", "0", "0"),  # cantidad cero: se ignora
    ]


def test_each_fill_recovers_its_decision_price_and_cost_in_basis_points() -> None:
    costs = {c.client_order_id: c for c in order_costs(journal(), costs_for)}
    assert set(costs) == {"a", "b", "c"}
    assert costs["a"].reference == Decimal(100)
    assert costs["a"].slippage_bp == pytest.approx(10.0)
    assert costs["a"].fee_rate == pytest.approx(0.001)
    assert costs["a"].leg == "spot"
    assert costs["a"].assumed_slippage_bp == pytest.approx(5.0)
    assert costs["a"].assumed_fee_rate == pytest.approx(0.001)
    assert costs["b"].reference == Decimal(100)
    assert costs["b"].slippage_bp == pytest.approx(2.0)
    assert costs["b"].leg == "perp"
    assert costs["b"].symbol == "SOLUSDT"
    assert costs["b"].assumed_fee_rate == pytest.approx(0.0005)
    assert costs["c"].slippage_bp == pytest.approx(-3.0)


def test_legs_compare_the_median_with_the_assumption() -> None:
    spot, perp = summarize(order_costs(journal(), costs_for))
    assert (spot.leg, spot.orders) == ("spot", 1)
    assert spot.slippage_bp_median == pytest.approx(10.0)
    assert spot.slippage_worse  # 10 pb > 5 pb supuestos
    assert not spot.fee_worse
    assert (perp.leg, perp.orders) == ("perp", 2)
    assert perp.slippage_bp_median == pytest.approx(-0.5)
    assert perp.slippage_bp_p90 == pytest.approx(1.5)  # interpolado entre -3 y 2
    assert not perp.slippage_worse
    assert perp.fee_rate_mean == pytest.approx(0.0005, rel=1e-3)


def test_report_and_artifact_say_what_is_worse() -> None:
    orders = order_costs(journal(), costs_for)
    legs = summarize(orders)
    text = render_markdown("binance-demo/muestreo", legs)
    assert "| spot | 1 | 10.00 pb" in text
    assert "| slippage |" in text  # spot es peor en slippage
    assert render_markdown("vacío", []).endswith("Sin fills en el diario.\n")
    artifact = to_json("binance-demo/muestreo", orders, legs)
    assert artifact["legs"][0]["slippage_worse"] is True
    assert {o["leg"] for o in artifact["orders"]} == {"spot", "perp"}
    assert Decimal(artifact["orders"][0]["reference"]) == 100
    assert summarize([]) == []
