"""Riesgo de contraparte del exchange: de las señales públicas a un nivel y una acción (PQ-96).

El capítulo 6 muestra que la quiebra del exchange es el riesgo que domina al carry. Esto no lo
simula: lo **vigila**, con tres señales públicas y gratuitas:

- **Estado del sistema** (mantenimiento o congelamiento de operaciones): si no es normal, alerta.
  No escala sola a crítico.
- **Prima de USDT frente a USDC** (huida de la stablecoin de margen): alerta desde ±0,5 % y crítico
  desde ±2 %.
- **Spread del perpetuo de BTC frente a Bybit y OKX** (un precio propio del exchange en apuros, como
  FTX en 2022): alerta desde ±0,5 % y crítico desde ±2 %.

- **Alerta:** aviso y **reducción de la exposición a la mitad** (``EXPOSURE_ON_ALERT``). No cierra
  todo.
- **Crítico:** activa el kill-switch, que cierra todas las posiciones. Es el único cierre total
  automático.
- Una señal que no responde no cambia el nivel, pero queda en el informe: «no se sabe» no es «todo
  bien».

Los umbrales son **iniciales y conservadores**. En condiciones normales, USDC/USDT y el spread entre
exchanges se mueven en décimas de punto básico. Calibrarlos con episodios históricos queda
**por verificar** (runbook de insolvencia del exchange).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from prometheus_platform.domain.counterparty import CounterpartyReading

EXPOSURE_ON_ALERT = 0.5


class Level(StrEnum):
    NORMAL = "normal"
    ALERTA = "alerta"
    CRITICO = "critico"


_ORDER = {Level.NORMAL: 0, Level.ALERTA: 1, Level.CRITICO: 2}


@dataclass(frozen=True, slots=True)
class Thresholds:
    usdt_alert: float = 0.005
    usdt_critical: float = 0.02
    spread_alert: float = 0.005
    spread_critical: float = 0.02

    def __post_init__(self) -> None:
        if not 0 < self.usdt_alert < self.usdt_critical:
            raise ValueError("Umbrales de USDT: 0 < alerta < crítico")
        if not 0 < self.spread_alert < self.spread_critical:
            raise ValueError("Umbrales de spread: 0 < alerta < crítico")


@dataclass(frozen=True, slots=True)
class Assessment:
    level: Level
    reasons: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def exposure_scale(self) -> float:
        """Fracción de la exposición normal que se permite (el crítico cierra todo aparte)."""
        return 1.0 if self.level is Level.NORMAL else EXPOSURE_ON_ALERT


def _band(value: float, alert: float, critical: float) -> Level:
    size = abs(value)
    if size >= critical:
        return Level.CRITICO
    if size >= alert:
        return Level.ALERTA
    return Level.NORMAL


def assess(reading: CounterpartyReading, thresholds: Thresholds | None = None) -> Assessment:
    """El peor nivel de las señales disponibles, con el motivo de cada una."""
    t = thresholds or Thresholds()
    level, reasons, unknown = Level.NORMAL, [], []

    def worse(candidate: Level, reason: str) -> None:
        nonlocal level
        if candidate is not Level.NORMAL:
            reasons.append(reason)
        if _ORDER[candidate] > _ORDER[level]:
            level = candidate

    if reading.system_normal is None:
        unknown.append("estado del sistema")
    elif not reading.system_normal:
        worse(Level.ALERTA, "el exchange no informa operación normal")
    if reading.usdt_premium is None:
        unknown.append("prima de USDT")
    else:
        worse(
            _band(reading.usdt_premium, t.usdt_alert, t.usdt_critical),
            f"USDT frente a USDC: {reading.usdt_premium:+.2%}",
        )
    if reading.perp_spread is None:
        unknown.append("spread del perpetuo")
    else:
        worse(
            _band(reading.perp_spread, t.spread_alert, t.spread_critical),
            f"perpetuo de BTC frente a otros exchanges: {reading.perp_spread:+.2%}",
        )
    return Assessment(level, reasons, unknown)
