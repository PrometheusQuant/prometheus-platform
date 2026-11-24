"""Frases de contexto del dashboard (PQ-127), sin Streamlit para poder testearlas.

Siguen a Stephen Few: cada cifra con su comparación, y mostrar las excepciones en lugar de filas
que repiten que no pasa nada. Hallazgos 2, 4, 9 y 10 de la segunda opinión de UX (PQ-125).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.api.dashboard import style
from prometheus_platform.api.paper.report import PaperView
from prometheus_platform.domain.events import FundingSettled

# Más de dos liquidaciones (cada 8 h) sin dato nuevo: la predicción ya no es «de hoy».
STALE_AFTER = timedelta(hours=16)
HALF_CENT = 0.005  # por debajo, el capital no cambió
DEFAULT_THETA = 0.20  # umbral de entrada de H2 (k9-theta20) si el artefacto no lo dice


def entry_threshold(selected: object) -> float:
    """θ de la configuración elegida: «k9-theta20» → 0,20."""
    found = re.search(r"theta(\d+)", str(selected or ""))
    return int(found.group(1)) / 100 if found else DEFAULT_THETA


@dataclass(frozen=True, slots=True)
class PaperHeadline:
    """La frase de la portada y las cifras con su comparación."""

    sentence: str
    days: int
    capital: str
    change: str
    drawdown: str


def paper_headline(view: PaperView, theta: float, now: datetime) -> PaperHeadline | None:
    """Qué está haciendo el paper, en una frase, y sus cifras con contexto."""
    if not view.valuations:
        return None
    equity, initial = float(view.equity or 0), float(view.initial_equity or 0)
    start = view.started_at or view.valuations[0].occurred_at
    days = max(0, (now - start).days)
    invested = any(q != 0 for q in view.positions.values())
    if invested:
        sentence = (
            f"El paper tiene una posición abierta: el funding superó el umbral de entrada del "
            f"{style.pct(theta, 0)} anual y cobra en cada liquidación."
        )
    else:
        best = _highest_signal(view.settlements)
        tail = "" if best is None else f" La señal más alta fue {style.pct(best[1])} en {best[0]}."
        sentence = (
            f"El paper está en efectivo: en sus {days} días el funding no llegó al umbral de "
            f"entrada del {style.pct(theta, 0)} anual, así que la regla manda esperar.{tail}"
        )
    change = equity - initial
    if abs(change) < HALF_CENT:
        change_text = "igual que al empezar"
    else:
        share = f" ({style.pct(change / initial, 2, signed=True)})" if initial else ""
        change_text = f"{style.usd(change, signed=True)} desde el inicio{share}"
    return PaperHeadline(
        sentence=sentence,
        days=days,
        capital=style.usd(equity),
        change=change_text,
        drawdown=style.pct(float(view.drawdown), 2),
    )


def _highest_signal(settlements: Sequence[FundingSettled]) -> tuple[str, float] | None:
    signals = [(s.symbol, float(s.s_k)) for s in settlements if s.s_k]  # vacía al arrancar
    return max(signals, key=lambda x: x[1]) if signals else None


def settlements_summary(settlements: Sequence[FundingSettled], theta: float) -> str:
    """Las excepciones de las liquidaciones: cuántas cruzaron el umbral y cuál fue la más alta."""
    if not settlements:
        return "Aún no hay liquidaciones."
    total = len(settlements)
    above = [s for s in settlements if s.s_k and float(s.s_k) >= theta]
    actions = {s.action for s in settlements}
    best = _highest_signal(settlements)
    best_text = "" if best is None else f"; la más alta fue {style.pct(best[1])} en {best[0]}"
    if not above:
        verdict = f"Ninguna de las {total} liquidaciones superó el {style.pct(theta, 0)}{best_text}"
    else:
        verdict = (
            f"{len(above)} de {total} liquidaciones superaron el {style.pct(theta, 0)}{best_text}"
        )
    if len(actions) == 1:
        verdict += f". Decisión en todas: «{next(iter(actions))}»"
    return verdict + "."


@dataclass(frozen=True, slots=True)
class Freshness:
    hours: float
    stale: bool

    @property
    def text(self) -> str:
        if self.hours < 1:
            return "hace menos de una hora"
        if self.hours < 48:
            return f"hace {self.hours:.0f} h"
        return f"hace {self.hours / 24:.0f} días"


def freshness(latest: datetime, now: datetime) -> Freshness:
    hours = max(0.0, (now - latest).total_seconds() / 3600)
    return Freshness(hours, now - latest > STALE_AFTER)


def nowcast_summary(rows: Sequence[Any]) -> str:
    """Una frase con lo que importa de la predicción: qué monedas cruzan y cuál está más cerca."""
    if not rows:
        return "Sin predicciones."
    high = [r.symbol for r in rows if r.probability_high >= 0.5]
    top = max(rows, key=lambda r: r.probability_high)
    if high:
        return (
            f"Funding alto probable en {', '.join(high)}. La probabilidad más alta es "
            f"{style.pct(top.probability_high)} en {top.symbol}."
        )
    return (
        f"Ninguna de las {len(rows)} monedas tiene funding alto probable. La más cercana es "
        f"{top.symbol}, con {style.pct(top.probability_high)}."
    )


def histogram_frame(final_capital: np.ndarray, bins: int = 30) -> pl.DataFrame:
    """Histograma con eje numérico de los casos sin quiebra (la quiebra va como cifra aparte)."""
    alive = final_capital[final_capital > 0]
    if alive.size == 0:
        return pl.DataFrame({"desde": [], "hasta": [], "trayectorias": []})
    counts, edges = np.histogram(alive, bins=bins)
    return pl.DataFrame(
        {"desde": edges[:-1], "hasta": edges[1:], "trayectorias": counts.astype(np.int64)}
    )


@dataclass(frozen=True, slots=True)
class InProgress:
    """Estrategia en curso para la portada: su etapa y dónde mirar su resultado."""

    name: str
    stage: str
    summary: str
    artifact: str  # ruta relativa a ``research/`` que aparece cuando hay evaluación


IN_PROGRESS: tuple[InProgress, ...] = (
    InProgress(
        "Momentum transversal",
        "En evaluación",
        "Largo en el tercio de perpetuos que más subió y corto en el que menos, cada semana.",
        "momentum",
    ),
    InProgress(
        "Polymarket",
        "En evaluación",
        "Apuesta por el favorito de mercados de predicción con precio de 0,80 a 0,95.",
        "polymarket",
    ),
)
