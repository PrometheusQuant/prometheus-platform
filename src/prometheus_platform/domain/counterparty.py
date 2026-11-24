"""Lectura de las señales públicas de riesgo de contraparte del exchange (PQ-96).

Cada campo es ``None`` si la fuente no respondió: «no se sabe» no es lo mismo que «todo bien».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CounterpartyReading:
    at: datetime
    # ¿El exchange informa operación normal? (``/sapi/v1/system/status`` de Binance)
    system_normal: bool | None = None
    # Prima de USDT frente a USDC: 1 / precio(USDCUSDT) - 1. Negativa = USDT con descuento.
    usdt_premium: float | None = None
    # Mark del perpetuo BTCUSDT de Binance frente a la mediana de otros exchanges, menos 1.
    perp_spread: float | None = None
    sources: dict[str, str] = field(default_factory=dict)  # qué falló y por qué
