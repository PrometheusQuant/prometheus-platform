"""Datos crudos de un mercado de predicción (Polymarket, PQ-92).

El dominio no sabe de URLs ni de JSON concretos: un ``RawPage`` es una respuesta de la API ya
decodificada, con la petición que la produjo, para que bronze guarde el linaje completo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RawPage:
    """Una página de la API tal como llegó: ``rows`` son los registros y ``request`` la URL."""

    request: str
    rows: Sequence[Mapping[str, Any]] = field(repr=False)


class PredictionMarketError(Exception):
    """La API del mercado de predicción no devolvió una respuesta válida."""
