"""Del peso objetivo de una ``Signal`` a la cantidad objetivo (PQ-116, ADR-0011).

Reglas puras del ejecutor genérico de señales: no conocen el bróker, el riesgo ni la red. El runner
las usa para operar en paper cualquier estrategia que cumpla el puerto ``Strategy``.

- **Asignación de capital.** Cada estrategia recibe una fracción de la equity (``capital_share``).
  Sus pesos se leen sobre esa fracción: un peso 1 con una asignación del 20 % es un nocional del
  20 % de la cuenta.
- **Latencia.** Una señal generada en *t* rige desde *t* + ``execution_delay``. Por defecto es 1 h,
  la misma latencia que el backtest de la tendencia (PQ-67) y que la enmienda 1.1 del carry.
- **Banda de no operación.** Solo se opera si la posición se aleja del objetivo más que
  ``rebalance_band``, medido como fracción del capital asignado. Es la banda fija del 10 % del
  pre-registro de la tendencia: con ella, el paper y el backtest operan en los mismos momentos.
- **Decisión por vela horaria.** El ejecutor decide en cada cierre de vela de 1 h, con un pequeño
  margen (``data_delay``) para que la API ya publique la vela.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from prometheus_platform.domain.model import InstrumentId, Signal
from prometheus_platform.domain.ports import Strategy

ZERO = Decimal(0)
HOUR = timedelta(hours=1)
DEFAULT_BAND = Decimal("0.10")
DEFAULT_DELAY = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class StrategyAllocation:
    """Una estrategia conectada al runner, con su parte del capital y su política de ejecución."""

    strategy: Strategy
    capital_share: Decimal
    rebalance_band: Decimal = DEFAULT_BAND
    execution_delay: timedelta = DEFAULT_DELAY

    def __post_init__(self) -> None:
        if not self.capital_share.is_finite() or not ZERO < self.capital_share <= 1:
            raise ValueError(
                f"{self.strategy.strategy_id}: capital_share debe estar en (0, 1], "
                f"no {self.capital_share}"
            )
        if not self.rebalance_band.is_finite() or not ZERO <= self.rebalance_band < 1:
            raise ValueError(f"{self.strategy.strategy_id}: rebalance_band debe estar en [0, 1)")
        if self.execution_delay < timedelta(0):
            raise ValueError(f"{self.strategy.strategy_id}: execution_delay no puede ser negativo")
        if not self.strategy.instruments:
            raise ValueError(f"{self.strategy.strategy_id}: no declara instrumentos")
        if self.strategy.lookback <= timedelta(0):
            raise ValueError(f"{self.strategy.strategy_id}: lookback debe ser positivo")

    @property
    def strategy_id(self) -> str:
        return self.strategy.strategy_id

    def describe(self) -> str:
        return (
            f"{self.strategy_id}[share={self.capital_share} band={self.rebalance_band} "
            f"delay={self.execution_delay} lookback={self.strategy.lookback}]"
        )


def validate_allocations(allocations: Sequence[StrategyAllocation]) -> Decimal:
    """Ids únicos, cada instrumento con un solo dueño y asignaciones que suman como mucho 1.

    Devuelve la suma de las asignaciones.
    """
    ids = [a.strategy_id for a in allocations]
    if len(set(ids)) != len(ids):
        raise ValueError(f"strategy_id repetido: {ids}")
    owner: dict[InstrumentId, str] = {}
    for a in allocations:
        for instrument in a.strategy.instruments:
            if instrument in owner:
                raise ValueError(
                    f"{instrument} lo declaran {owner[instrument]} y {a.strategy_id}: cada "
                    "instrumento tiene una sola estrategia, o sus órdenes se pisarían"
                )
            owner[instrument] = a.strategy_id
    total = sum((a.capital_share for a in allocations), ZERO)
    if total > 1:
        raise ValueError(f"Las asignaciones suman {total} > 1")
    return total


def decision_time(now: datetime, data_delay: timedelta) -> datetime:
    """Último cierre de vela horaria cuyos datos ya deberían estar publicados."""
    return (now - data_delay).replace(minute=0, second=0, microsecond=0)


def effective_weight(
    history: Sequence[Signal], now: datetime, delay: timedelta
) -> tuple[Signal | None, Signal | None]:
    """La señal vigente en ``now`` y la siguiente pendiente de la latencia, si hay.

    ``history`` va en orden de generación. Una señal nueva sustituye a la anterior aunque esta no
    haya llegado a regir, igual que en el backtest (cada decisión cancela la orden pendiente).
    """
    current: Signal | None = None
    pending: Signal | None = None
    for signal in history:
        if signal.generated_at + delay <= now:
            current, pending = signal, None
        else:
            pending = signal
    return current, pending


def target_quantity(
    weight: Decimal, budget: Decimal, price: Decimal, max_notional: Decimal
) -> Decimal:
    """Cantidad con signo: ``weight`` del capital asignado, acotada por el nocional máximo."""
    if not price.is_finite() or price <= 0:
        raise ValueError(f"Precio inválido: {price}")
    if budget <= 0 or weight == 0:
        return ZERO
    notional = min(abs(weight) * budget, max_notional)
    quantity = notional / price
    return quantity if weight > 0 else -quantity


def outside_band(
    held: Decimal, target: Decimal, price: Decimal, budget: Decimal, band: Decimal
) -> bool:
    """La posición se aleja del objetivo más que la banda (fracción del capital asignado)."""
    if held == target:
        return False
    if budget <= 0:  # sin capital asignado solo se puede reducir: cualquier resto sobra
        return True
    return abs(target - held) * price / budget > band
