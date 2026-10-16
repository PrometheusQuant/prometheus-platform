"""Value objects del dominio de trading.

El dominio solo usa la librería estándar: no conoce exchanges, bases de datos ni
frameworks. Los precios y cantidades son ``Decimal`` para evitar errores de redondeo
de coma flotante en dinero, y todos los instantes son ``datetime`` con zona horaria UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class DomainError(ValueError):
    """Un objeto del dominio violaría una de sus invariantes."""


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Venue(StrEnum):
    BINANCE = "BINANCE"
    POLYMARKET = "POLYMARKET"
    PAPER = "PAPER"


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise DomainError(f"{name} debe estar en UTC con zona horaria explícita: {value!r}")


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Identificador de un instrumento en un venue, p. ej. ``BTCUSDT-PERP.BINANCE``."""

    symbol: str
    venue: Venue

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip():
            raise DomainError(f"Símbolo inválido: {self.symbol!r}")

    def __str__(self) -> str:
        return f"{self.symbol}.{self.venue}"


@dataclass(frozen=True, slots=True)
class Bar:
    """Vela OHLCV. ``close_time`` es también el momento en que el dato se conoce.

    Usar ``knowledge_time`` (y no ``open_time``) en los joins evita el sesgo de
    anticipación: una vela no puede usarse antes de haber cerrado.
    """

    instrument: InstrumentId
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        _require_utc("open_time", self.open_time)
        _require_utc("close_time", self.close_time)
        if self.close_time <= self.open_time:
            raise DomainError("close_time debe ser posterior a open_time")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise DomainError("Los precios deben ser positivos")
        if self.volume < 0:
            raise DomainError("El volumen no puede ser negativo")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise DomainError("Se requiere low <= open, close <= high")

    @property
    def knowledge_time(self) -> datetime:
        return self.close_time


@dataclass(frozen=True, slots=True)
class FundingRate:
    """Pago de funding de un perpetuo, expresado como fracción por periodo (0.0001 = 0,01 %)."""

    instrument: InstrumentId
    funding_time: datetime
    rate: Decimal

    def __post_init__(self) -> None:
        _require_utc("funding_time", self.funding_time)

    @property
    def knowledge_time(self) -> datetime:
        return self.funding_time


@dataclass(frozen=True, slots=True)
class Signal:
    """Intención de una estrategia: el peso objetivo en un instrumento, en [-1, 1].

    Una señal no es una orden. El tamaño final lo deciden ``portfolio_risk`` y la
    ejecución, lo que separa la lógica de alfa del manejo del riesgo (SRP).
    """

    strategy_id: str
    instrument: InstrumentId
    generated_at: datetime
    target_weight: Decimal

    def __post_init__(self) -> None:
        _require_utc("generated_at", self.generated_at)
        if not self.strategy_id:
            raise DomainError("strategy_id es obligatorio")
        if not Decimal(-1) <= self.target_weight <= Decimal(1):
            raise DomainError(f"target_weight fuera de [-1, 1]: {self.target_weight}")
