"""Gestión de riesgo pre-trade y monitoreo de la cartera (PQ-53).

Ninguna orden llega al exchange sin pasar por ``RiskManager.pre_trade``. Las reglas son puras:
reciben la orden, la cartera (con las órdenes pendientes) y los límites, y devuelven una decisión
con la regla que la bloqueó.

Principios:
- **Reducir exposición siempre está permitido.** Es la forma de volver dentro de los límites y lo
  que hace el kill-switch al cerrar posiciones. «Reducir» se mide contando las órdenes pendientes:
  dos cierres seguidos no pueden terminar abriendo un corto.
- **Fallar en voz alta.** Precios no positivos o no finitos, equity no positiva y desbalances sin
  información de antigüedad se tratan como lo peor posible: no se interpretan.
- **Precio conservador.** La exposición nueva se valora al mayor entre el precio de la orden y el
  mark de la cartera: un precio subestimado no puede colar una orden grande.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from prometheus_platform.domain.model import InstrumentId, Side
from prometheus_platform.ops.settings import Settings

ZERO = Decimal(0)


def _require_positive_finite(name: str, value: Decimal) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} debe ser positivo y finito: {value}")


class Leg(StrEnum):
    SPOT = "spot"
    PERP = "perp"


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_notional_symbol: Decimal
    max_notional_total: Decimal
    max_leverage: Decimal
    hard_leverage: Decimal
    max_daily_loss: Decimal
    max_hedge_imbalance: Decimal
    imbalance_grace_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> RiskLimits:
        return cls(
            max_notional_symbol=Decimal(str(settings.risk_max_notional_symbol_usd)),
            max_notional_total=Decimal(str(settings.risk_max_notional_total_usd)),
            max_leverage=Decimal(str(settings.risk_max_leverage)),
            hard_leverage=Decimal(str(settings.risk_hard_leverage)),
            max_daily_loss=Decimal(str(settings.risk_max_daily_loss)),
            max_hedge_imbalance=Decimal(str(settings.risk_max_hedge_imbalance)),
            imbalance_grace_seconds=settings.risk_imbalance_grace_seconds,
        )


@dataclass(frozen=True, slots=True)
class Position:
    """Posición de una pata. ``quantity`` es con signo: negativa en un corto."""

    instrument: InstrumentId
    symbol: str
    leg: Leg
    quantity: Decimal
    mark_price: Decimal

    def __post_init__(self) -> None:
        if not self.quantity.is_finite():
            raise ValueError(f"Cantidad no finita en {self.instrument}: {self.quantity}")
        _require_positive_finite(f"mark_price de {self.instrument}", self.mark_price)

    @property
    def notional(self) -> Decimal:
        return abs(self.quantity) * self.mark_price

    @property
    def signed_notional(self) -> Decimal:
        return self.quantity * self.mark_price


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    equity: Decimal
    start_of_day_equity: Decimal
    positions: Sequence[Position] = ()
    # Cantidad con signo de las órdenes enviadas y todavía no ejecutadas, por instrumento.
    pending: Mapping[InstrumentId, Decimal] = field(default_factory=dict)
    # Segundos que lleva cada símbolo con las patas desbalanceadas (lo mide quien ejecuta).
    imbalance_age_seconds: Mapping[str, float] = field(default_factory=dict)

    def notional_by_symbol(self) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for p in self.positions:
            totals[p.symbol] = totals.get(p.symbol, ZERO) + p.notional
        return totals

    @property
    def gross_notional(self) -> Decimal:
        return sum((p.notional for p in self.positions), ZERO)

    def position(self, instrument: InstrumentId) -> Position | None:
        return next((p for p in self.positions if p.instrument == instrument), None)

    def committed_quantity(self, instrument: InstrumentId) -> Decimal:
        """Posición más órdenes pendientes: lo que quedará si todo se ejecuta."""
        current = self.position(instrument)
        return (current.quantity if current else ZERO) + self.pending.get(instrument, ZERO)


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    strategy_id: str
    instrument: InstrumentId
    symbol: str
    leg: Leg
    side: Side
    quantity: Decimal
    price: Decimal  # estimación para el control pre-trade (último precio conocido)

    def __post_init__(self) -> None:
        _require_positive_finite("La cantidad de la orden", self.quantity)
        _require_positive_finite("El precio de la orden", self.price)

    @property
    def signed_quantity(self) -> Decimal:
        return self.quantity if self.side is Side.BUY else -self.quantity


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    rule: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Breach:
    rule: str
    detail: str
    trips_kill_switch: bool


APPROVED = RiskDecision(approved=True)


def _reduces(before: Decimal, after: Decimal) -> bool:
    """Hacia cero sin cruzar al lado contrario."""
    return abs(after) <= abs(before) and (after == 0 or (after > 0) == (before > 0))


class RiskManager:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def pre_trade(
        self, order: ProposedOrder, book: PortfolioSnapshot, *, kill_switch_active: bool
    ) -> RiskDecision:
        held = book.position(order.instrument)
        if held is not None and held.symbol != order.symbol:
            return RiskDecision(
                False,
                "simbolo_inconsistente",
                f"{order.instrument} es {held.symbol} en la cartera, no {order.symbol}",
            )
        before = book.committed_quantity(order.instrument)
        after = before + order.signed_quantity
        if _reduces(before, after):
            return APPROVED  # cerrar o reducir nunca se bloquea
        if kill_switch_active:
            return RiskDecision(
                False, "kill_switch", "activado: solo se permiten órdenes que reducen"
            )
        if book.equity <= 0:
            return RiskDecision(False, "equity", f"equity no positiva: {book.equity}")
        price = max(order.price, held.mark_price) if held else order.price
        return self._exposure_check(order, book, (abs(after) - abs(before)) * price)

    def _exposure_check(
        self, order: ProposedOrder, book: PortfolioSnapshot, added: Decimal
    ) -> RiskDecision:
        """Nocional por símbolo, nocional total y apalancamiento, después de la orden."""
        symbol_after = book.notional_by_symbol().get(order.symbol, ZERO) + added
        gross_after = book.gross_notional + added
        leverage_after = gross_after / book.equity
        checks = (
            (
                symbol_after > self.limits.max_notional_symbol,
                "nocional_simbolo",
                f"{order.symbol}: {symbol_after:.2f} > {self.limits.max_notional_symbol}",
            ),
            (
                gross_after > self.limits.max_notional_total,
                "nocional_total",
                f"{gross_after:.2f} > {self.limits.max_notional_total}",
            ),
            (
                leverage_after > self.limits.max_leverage,
                "apalancamiento",
                f"{leverage_after:.3f}x > {self.limits.max_leverage}x",
            ),
        )
        for failed, rule, detail in checks:
            if failed:
                return RiskDecision(False, rule, detail)
        return APPROVED

    def monitor(self, book: PortfolioSnapshot) -> list[Breach]:
        """Violaciones del estado actual. Las graves activan el kill-switch."""
        if book.equity <= 0:
            return [Breach("equity", f"equity no positiva: {book.equity}", trips_kill_switch=True)]
        breaches: list[Breach] = []
        if book.start_of_day_equity <= 0:
            breaches.append(
                Breach(
                    "equity_inicio_dia",
                    f"sin referencia válida para la pérdida diaria: {book.start_of_day_equity}",
                    trips_kill_switch=True,
                )
            )
        else:
            change = book.equity / book.start_of_day_equity - 1
            if change < -self.limits.max_daily_loss:
                breaches.append(
                    Breach(
                        "perdida_diaria",
                        f"{change:.2%} < -{self.limits.max_daily_loss:.2%}",
                        trips_kill_switch=True,
                    )
                )
        leverage = book.gross_notional / book.equity
        if leverage > self.limits.hard_leverage:
            breaches.append(
                Breach(
                    "apalancamiento_duro",
                    f"{leverage:.3f}x > {self.limits.hard_leverage}x",
                    trips_kill_switch=True,
                )
            )
        elif leverage > self.limits.max_leverage:
            breaches.append(
                Breach(
                    "apalancamiento",
                    f"{leverage:.3f}x > {self.limits.max_leverage}x",
                    trips_kill_switch=False,
                )
            )
        breaches += self._hedge_breaches(book)
        return breaches

    def _hedge_breaches(self, book: PortfolioSnapshot) -> list[Breach]:
        breaches = []
        for symbol, imbalance in sorted(hedge_imbalances(book.positions).items()):
            if imbalance <= self.limits.max_hedge_imbalance:
                continue
            # Sin dato de antigüedad se asume lo peor: la gracia ya pasó.
            age = book.imbalance_age_seconds.get(symbol, math.inf)
            breaches.append(
                Breach(
                    "pata_sin_cubrir",
                    f"{symbol}: desbalance neto {imbalance:.1%} durante {age:.0f} s",
                    trips_kill_switch=age > self.limits.imbalance_grace_seconds,
                )
            )
        return breaches


def hedge_imbalances(positions: Sequence[Position]) -> dict[str, Decimal]:
    """Desbalance de la cobertura del carry por símbolo: |spot + perp| / max(|spot|, |perp|).

    Se mide la exposición **neta** con signo: dos largos (un error de signo en la ejecución)
    aparecen como un desbalance del 200 % y no como una cobertura perfecta. Quien ejecuta lo usa
    para medir desde cuándo dura un desbalance (``imbalance_age_seconds``).
    """
    legs: dict[str, dict[Leg, Decimal]] = {}
    for p in positions:
        by_leg = legs.setdefault(p.symbol, {})
        by_leg[p.leg] = by_leg.get(p.leg, ZERO) + p.signed_notional
    result = {}
    for symbol, by_leg in legs.items():
        spot, perp = by_leg.get(Leg.SPOT, ZERO), by_leg.get(Leg.PERP, ZERO)
        larger = max(abs(spot), abs(perp))
        if larger:
            result[symbol] = abs(spot + perp) / larger
    return result


def flatten_orders(
    book: PortfolioSnapshot, strategy_id: str = "kill-switch"
) -> list[ProposedOrder]:
    """Órdenes de cierre de todas las posiciones (incluidas las pendientes) para el runner."""
    orders = []
    for p in book.positions:
        target = book.committed_quantity(p.instrument)
        if target == 0:
            continue
        orders.append(
            ProposedOrder(
                strategy_id=strategy_id,
                instrument=p.instrument,
                symbol=p.symbol,
                leg=p.leg,
                side=Side.SELL if target > 0 else Side.BUY,
                quantity=abs(target),
                price=p.mark_price,
            )
        )
    return orders
