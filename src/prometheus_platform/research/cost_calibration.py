"""Calibración del modelo de costes con fills reales (PQ-95).

Lee un diario del paper (``OrderSubmitted`` y ``OrderFilled``) y mide, por orden:

- **slippage** frente al precio de decisión, en puntos básicos y con signo (positivo es coste).
  El precio de decisión se reconstruye del propio fill: ``slippage = cantidad_con_signo *
  (precio - referencia)``, que es como lo registran los brókers;
- **comisión efectiva**, como fracción del nocional ejecutado.

Después compara cada pata (spot y perp) con el supuesto del backtest: ``CostModel`` del símbolo,
con 2 pb de slippage para BTC y ETH y 5 pb para SOL, BNB y XRP.

**Lo medido solo sirve para los backtests siguientes.** Los ya evaluados no se tocan. Si lo medido
es peor, se abre un ticket de enmienda.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from prometheus_platform.domain.events import DomainEvent, OrderFilled, OrderSubmitted
from prometheus_platform.domain.model import InstrumentId, Side
from prometheus_platform.research.backtest import CostModel

BP = Decimal(10_000)
PERP_SUFFIX = "-PERP"
# La comisión spot se cobra en el activo comprado y se pasa a USDT al precio del fill: el
# redondeo deja la tasa medida en 0,10005 % frente al 0,1 % de la tarifa. Menos de un 1 % relativo
# por encima no es una comisión peor, es ruido de la conversión.
FEE_TOLERANCE = 1.01


@dataclass(frozen=True, slots=True)
class OrderCost:
    client_order_id: str
    occurred_at: datetime
    instrument: InstrumentId
    side: Side
    quantity: Decimal
    reference: Decimal
    fill_price: Decimal
    slippage_bp: float
    fee_rate: float
    assumed_slippage_bp: float
    assumed_fee_rate: float

    @property
    def leg(self) -> str:
        return "perp" if self.instrument.symbol.endswith(PERP_SUFFIX) else "spot"

    @property
    def symbol(self) -> str:
        return self.instrument.symbol.removesuffix(PERP_SUFFIX)


@dataclass(frozen=True, slots=True)
class LegSummary:
    """Resumen de una pata frente a lo supuesto. ``worse`` compara la mediana con el supuesto."""

    leg: str
    orders: int
    slippage_bp_median: float
    slippage_bp_mean: float
    slippage_bp_p90: float
    fee_rate_mean: float
    assumed_slippage_bp: float
    assumed_fee_rate: float

    @property
    def slippage_worse(self) -> bool:
        return self.slippage_bp_median > self.assumed_slippage_bp

    @property
    def fee_worse(self) -> bool:
        return self.fee_rate_mean > self.assumed_fee_rate * FEE_TOLERANCE


def order_costs(
    events: Iterable[DomainEvent], costs_for: Callable[[str], CostModel]
) -> list[OrderCost]:
    """Un ``OrderCost`` por fill con su orden en el diario; los fills huérfanos se ignoran."""
    submitted: dict[str, OrderSubmitted] = {}
    result: list[OrderCost] = []
    for event in events:
        if isinstance(event, OrderSubmitted):
            submitted[event.client_order_id] = event
        elif isinstance(event, OrderFilled) and event.client_order_id in submitted:
            order = submitted[event.client_order_id]
            qty = event.fill_quantity
            if qty <= 0 or event.fill_price <= 0:
                continue
            signed = qty if order.side is Side.BUY else -qty
            reference = event.fill_price - event.slippage / signed
            symbol = order.instrument.symbol.removesuffix(PERP_SUFFIX)
            model = costs_for(symbol)
            perp = order.instrument.symbol.endswith(PERP_SUFFIX)
            result.append(
                OrderCost(
                    client_order_id=order.client_order_id,
                    occurred_at=event.occurred_at,
                    instrument=order.instrument,
                    side=order.side,
                    quantity=qty,
                    reference=reference,
                    fill_price=event.fill_price,
                    slippage_bp=float(event.slippage / (qty * reference) * BP),
                    fee_rate=float(event.fee / (qty * event.fill_price)),
                    assumed_slippage_bp=model.slippage * 10_000,
                    assumed_fee_rate=model.perp_fee if perp else model.spot_fee,
                )
            )
    return result


def summarize(orders: Sequence[OrderCost]) -> list[LegSummary]:
    """Una fila por pata y supuesto de slippage: ``spot`` y luego ``perp``, de menor a mayor.

    BTC y ETH suponen 2 pb y las altcoins 5 pb: mezclarlos en una fila compararía la mediana de
    todos con el supuesto más laxo.
    """
    rows = []
    for leg in ("spot", "perp"):
        for assumed in sorted({o.assumed_slippage_bp for o in orders if o.leg == leg}):
            chosen = [o for o in orders if o.leg == leg and o.assumed_slippage_bp == assumed]
            rows.append(_leg_summary(leg, chosen))
    return rows


def _leg_summary(leg: str, chosen: Sequence[OrderCost]) -> LegSummary:
    slips = sorted(o.slippage_bp for o in chosen)
    return LegSummary(
        leg=leg,
        orders=len(chosen),
        slippage_bp_median=statistics.median(slips),
        slippage_bp_mean=statistics.fmean(slips),
        slippage_bp_p90=_quantile(slips, 0.9),
        fee_rate_mean=statistics.fmean(o.fee_rate for o in chosen),
        assumed_slippage_bp=chosen[0].assumed_slippage_bp,
        assumed_fee_rate=max(o.assumed_fee_rate for o in chosen),
    )


def _quantile(ordered: Sequence[float], q: float) -> float:
    """Cuantil con interpolación lineal sobre una lista ya ordenada."""
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def to_json(source: str, orders: Sequence[OrderCost], legs: Sequence[LegSummary]) -> dict[str, Any]:
    """Artefacto para el dashboard (``data/research/costes/<fuente>.json``)."""
    return {
        "source": source,
        "legs": [
            {**asdict(leg), "slippage_worse": leg.slippage_worse, "fee_worse": leg.fee_worse}
            for leg in legs
        ],
        "orders": [
            {
                "client_order_id": o.client_order_id,
                "occurred_at": o.occurred_at.isoformat(),
                "symbol": o.symbol,
                "leg": o.leg,
                "side": o.side.value,
                "quantity": str(o.quantity),
                "reference": str(o.reference),
                "fill_price": str(o.fill_price),
                "slippage_bp": o.slippage_bp,
                "fee_rate": o.fee_rate,
                "assumed_slippage_bp": o.assumed_slippage_bp,
            }
            for o in orders
        ],
    }


def render_markdown(source: str, legs: Sequence[LegSummary]) -> str:
    """Tabla de una fuente: lo medido frente a lo supuesto, pata por pata."""
    if not legs:
        return f"### {source}\n\nSin fills en el diario.\n"
    lines = [
        f"### {source}",
        "",
        "| Pata | Órdenes | Slippage mediano | p90 | Supuesto "
        "| Comisión media | Supuesta | ¿Peor? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for leg in legs:
        worse = [
            w for w, flag in (("slippage", leg.slippage_worse), ("comisión", leg.fee_worse)) if flag
        ]
        lines.append(
            f"| {leg.leg} | {leg.orders} | {leg.slippage_bp_median:.2f} pb "
            f"| {leg.slippage_bp_p90:.2f} pb | {leg.assumed_slippage_bp:.0f} pb "
            f"| {leg.fee_rate_mean * 100:.3f} % | {leg.assumed_fee_rate * 100:.3f} % "
            f"| {', '.join(worse) or 'no'} |"
        )
    return "\n".join(lines) + "\n"
