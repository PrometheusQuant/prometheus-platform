"""Archivos históricos de datos de mercado: qué se descarga y qué garantías trae.

Un ``ArchiveRef`` identifica un archivo publicado por un proveedor (p. ej. las velas de 1h de
BTCUSDT de enero de 2024). Un ``RawArchive`` es su contenido, ya verificado contra el checksum
del proveedor. El dominio no sabe de URLs ni de formatos de archivo: eso lo resuelven los
adaptadores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from prometheus_platform.domain.model import DomainError

_SYMBOL = re.compile(r"^[A-Z0-9]{2,30}$")
_INTERVAL = re.compile(r"^[1-9][0-9]*[smhdwM]$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Market(StrEnum):
    SPOT = "spot"
    USDM = "um"  # futuros USDⓈ-M (perpetuos con margen en USDT/USDC)


class DatasetKind(StrEnum):
    KLINES = "klines"
    FUNDING_RATE = "fundingRate"


class Granularity(StrEnum):
    MONTHLY = "monthly"
    DAILY = "daily"


@dataclass(frozen=True, slots=True)
class ArchiveRef:
    """Un archivo publicado. ``period`` es el día 1 del mes en los archivos mensuales."""

    market: Market
    dataset: DatasetKind
    symbol: str
    period: date
    interval: str | None = None
    granularity: Granularity = Granularity.MONTHLY

    def __post_init__(self) -> None:
        if not _SYMBOL.match(self.symbol):
            raise DomainError(f"Símbolo inválido: {self.symbol!r}")
        if self.dataset is DatasetKind.KLINES:
            if self.interval is None or not _INTERVAL.match(self.interval):
                raise DomainError(f"Las velas requieren un intervalo válido: {self.interval!r}")
        elif self.interval is not None:
            raise DomainError(f"{self.dataset} no tiene intervalo")
        if self.dataset is DatasetKind.FUNDING_RATE and self.market is not Market.USDM:
            raise DomainError("El funding rate solo existe en futuros perpetuos")
        if self.granularity is Granularity.MONTHLY and self.period.day != 1:
            raise DomainError(f"Un archivo mensual empieza el día 1: {self.period}")

    def __str__(self) -> str:
        parts = [self.market, self.dataset, self.symbol, self.interval, self.period.isoformat()]
        return "/".join(p for p in parts if p)


@dataclass(frozen=True, slots=True)
class RawArchive:
    """Contenido de un archivo cuyo SHA-256 ya coincidió con el publicado por el proveedor."""

    ref: ArchiveRef
    payload: bytes = field(repr=False)
    sha256: str

    def __post_init__(self) -> None:
        if not _SHA256.match(self.sha256):
            raise DomainError(f"SHA-256 inválido: {self.sha256!r}")


class DataSourceError(Exception):
    """El proveedor no pudo entregar un archivo válido."""

    def __init__(self, ref: ArchiveRef, message: str) -> None:
        super().__init__(f"{ref}: {message}")
        self.ref = ref


class ArchiveNotFoundError(DataSourceError):
    """El archivo no existe: periodo aún no publicado o anterior al listado del símbolo."""


class ChecksumMismatchError(DataSourceError):
    """El contenido descargado no coincide con el checksum publicado."""

    def __init__(self, ref: ArchiveRef, expected: str, actual: str) -> None:
        super().__init__(ref, f"checksum esperado {expected}, obtenido {actual}")
        self.expected = expected
        self.actual = actual
