"""Reglas del carry de funding, compartidas por el backtest y el paper trading (PQ-54).

Es la regla pre-registrada (``docs/estrategias/01-carry/pre-registro.md`` §4 y enmienda 2) en una
función pura, sin estado ni infraestructura. El backtest (``research/backtest.py``) y la estrategia
en vivo (``strategies/carry.py``) llaman a **esta misma** función: así la paridad entre backtest y
paper no depende de mantener dos copias iguales.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

REBALANCE_DRIFT = 0.10  # enmienda 2: cada pata vale capital/2; se reajusta si se desvía > 10 %
HOURS_PER_YEAR = 8760


class CarryAction(StrEnum):
    ENTRAR = "entrada"
    SALIR = "salida"
    MANTENER = "mantener"


@dataclass(frozen=True, slots=True)
class CarryParams:
    k: int
    theta: float
    always_on: bool = False  # benchmark B1

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k debe ser ≥ 1: {self.k}")


def decide(
    *, is_open: bool, s_k: float | None, last_rate: float, params: CarryParams
) -> CarryAction:
    """Histéresis del §4: entra si ``S_k ≥ θ``; sale si ``S_k < θ/2`` o la última tasa es negativa.

    ``s_k`` es ``None`` mientras no hay ``k`` liquidaciones (ventana inicial de la señal).
    """
    if s_k is None:
        return CarryAction.MANTENER
    if not is_open and (params.always_on or s_k >= params.theta):
        return CarryAction.ENTRAR
    if is_open and not params.always_on and (s_k < params.theta / 2 or last_rate < 0):
        return CarryAction.SALIR
    return CarryAction.MANTENER


def needs_rebalance(spot_value: float, perp_value: float, target: float) -> bool:
    """Enmienda 2: alguna pata se desvía más de un 10 % del objetivo capital/2."""
    if target <= 0:
        return False
    drift = max(abs(spot_value - target), abs(perp_value - target)) / target
    return drift > REBALANCE_DRIFT


def annualize(rate: float, interval_hours: float) -> float:
    """Tasa por liquidación → anual, con el intervalo de **esa** liquidación (auditoría PQ-19)."""
    return rate * HOURS_PER_YEAR / interval_hours


def signal(annualized_rates: Sequence[float], k: int) -> float | None:
    """``S_k``: media de las últimas ``k`` tasas anualizadas; ``None`` si aún no hay ``k``."""
    if len(annualized_rates) < k:
        return None
    window = annualized_rates[-k:]
    return sum(window) / k
