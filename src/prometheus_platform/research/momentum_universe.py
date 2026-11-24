"""Universo del momentum transversal (PQ-114, pre-registro §3), fijado antes de verlo.

Reglas del pre-registro:

1. Candidatos: perpetuos USDⓈ-M de Binance listados antes del 2021-01-01, sin stablecoins ni
   tokens apalancados. Un símbolo cuenta como listado antes de 2021 si Data Vision publica su
   archivo diario de **diciembre de 2020**. La lista sale del bucket completo, que incluye los
   deslistados: así no hay sesgo de supervivencia.
2. Se eligen los 15 de mayor volumen negociado en USDT en diciembre de 2020.
3. La lista queda fija para todo el estudio.

Este módulo no hace I/O: recibe los símbolos y los volúmenes y devuelve la selección.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

UNIVERSE_SIZE = 15
SMALLEST = 5  # los 5 de menor volumen pagan 10 pb de slippage en vez de 5 (pre-registro §6)
QUOTE = "USDT"

# Fijadas antes de mirar volúmenes (2026-11-24). Bases que son stablecoins o monedas fiat.
STABLE_BASES = frozenset(
    {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDD", "UST", "EUR", "GBP", "AUD"}
)
# Tokens apalancados de Binance: sufijos UP/DOWN/BULL/BEAR sobre la base (p. ej. BTCUPUSDT).
_LEVERAGED = re.compile(r"^[A-Z0-9]+(UP|DOWN|BULL|BEAR)USDT$")


def is_candidate(symbol: str) -> bool:
    """Perpetuo lineal en USDT, sin stablecoins ni tokens apalancados."""
    if not symbol.endswith(QUOTE) or "_" in symbol:  # los trimestrales llevan _YYMMDD
        return False
    base = symbol.removesuffix(QUOTE)
    if not base or base in STABLE_BASES:
        return False
    return not _LEVERAGED.match(symbol)


@dataclass(frozen=True)
class Universe:
    symbols: tuple[str, ...]  # por volumen de diciembre de 2020, de mayor a menor
    smallest: tuple[str, ...]  # los SMALLEST de menor volumen dentro del universo
    volumes: dict[str, float]  # volumen en USDT de diciembre de 2020 de cada candidato con datos
    candidates: int  # candidatos con archivo de diciembre de 2020


def select_universe(
    volumes: Mapping[str, float], *, size: int = UNIVERSE_SIZE, smallest: int = SMALLEST
) -> Universe:
    """Los ``size`` de mayor volumen; los empates se resuelven por símbolo (determinista)."""
    eligible = {s: v for s, v in volumes.items() if is_candidate(s) and v > 0}
    if len(eligible) < size:
        raise ValueError(f"Solo hay {len(eligible)} candidatos con volumen; se necesitan {size}")
    ranked = sorted(eligible, key=lambda s: (-eligible[s], s))
    chosen = tuple(ranked[:size])
    return Universe(
        symbols=chosen,
        smallest=tuple(sorted(chosen[-smallest:])),
        volumes=dict(eligible),
        candidates=len(eligible),
    )


def candidates(symbols: Iterable[str]) -> list[str]:
    return sorted({s for s in symbols if is_candidate(s)})
