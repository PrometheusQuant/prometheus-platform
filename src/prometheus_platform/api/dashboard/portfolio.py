"""Vista de cartera multiestrategia del dashboard (PQ-84), sin Streamlit para poder testearla.

Junta tres fuentes de solo lectura:

- el **diario del paper trading**: capital y PnL por estrategia y exchange
  (``report.strategy_breakdown``);
- el **presupuesto recomendado** de ``pq research budget`` (PQ-83): pesos, efectivo y escenarios
  con quiebra del exchange, con los que se calcula la contribución de cada estrategia al CVaR, tanto
  con el presupuesto como con lo que el paper tiene ahora;
- los **retornos diarios del desarrollo** del carry H2, que remuestreados dan las bandas de lo que
  esperaba el backtest para los días que lleva el paper.

Los nombres del presupuesto (``carry-H2``) y del paper (``carry-h2``) se emparejan sin distinguir
mayúsculas.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.api.dashboard import style
from prometheus_platform.api.paper.report import UNASSIGNED, StrategyRow
from prometheus_platform.domain.events import PortfolioValued
from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.portfolio_risk.budget import bootstrap_bands, cvar_contributions

CASH = "efectivo"


def strategy_table(rows: Sequence[StrategyRow], equity: Decimal) -> pl.DataFrame:
    """Capital y PnL de cada estrategia en cada exchange, en USD y en % de la equity."""
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(
        {
            "estrategia": [r.strategy for r in rows],
            "exchange": [r.exchange.lower() for r in rows],
            "capital": [style.usd(float(r.exposure)) for r in rows],
            "% del capital": [
                style.pct(float(r.exposure / equity)) if equity > 0 else "n/d" for r in rows
            ],
            "ganancia": [style.usd(float(r.pnl), signed=True) for r in rows],
            "funding": [style.usd(float(r.funding), signed=True) for r in rows],
            "costes": [style.usd(float(r.costs)) for r in rows],
            "precio usado": [
                "aproximado (última orden)"
                if r.approximate
                else "precio de referencia del exchange"
                for r in rows
            ],
        }
    )


def paper_weights(rows: Sequence[StrategyRow], equity: Decimal) -> dict[str, float]:
    """Peso de cada estrategia en el paper: su capital bruto entre la equity.

    El carry tiene dos patas de igual nocional, así que su peso económico es la mitad del bruto
    (spot largo cubierto con el perpetuo corto). Así se compara con el presupuesto, que mide
    fracción del capital.
    """
    if equity <= 0:
        return {}
    weights: dict[str, float] = {}
    for r in rows:
        if r.strategy == UNASSIGNED:
            continue
        gross = float(r.exposure / equity)
        share = gross / 2 if r.strategy.lower().startswith("carry") else gross
        weights[r.strategy.lower()] = weights.get(r.strategy.lower(), 0.0) + share
    return weights


def allocation_table(budget: Mapping[str, Any], current: Mapping[str, float]) -> pl.DataFrame:
    """Presupuesto recomendado frente a lo que el paper tiene ahora."""
    recommended = {str(k).lower(): float(v) for k, v in budget.get("presupuesto", {}).items()}
    names = sorted(set(recommended) | set(current))
    rec_cash = float(budget.get("efectivo", 1.0))
    cur_cash = max(0.0, 1 - sum(current.values()))
    return pl.DataFrame(
        {
            "estrategia": [*names, CASH],
            "recomendado": [style.pct(recommended.get(n, 0.0), 0) for n in names]
            + [style.pct(rec_cash, 0)],
            "en paper ahora": [style.pct(current.get(n, 0.0), 0) for n in names]
            + [style.pct(cur_cash, 0)],
        }
    )


def cvar_table(
    budget: Mapping[str, Any], scenarios: pl.DataFrame, current: Mapping[str, float]
) -> pl.DataFrame:
    """Contribución al CVaR95 con el presupuesto y con la asignación actual del paper."""
    columns = {c.lower(): scenarios[c].to_numpy() for c in scenarios.columns}
    hurdle = float(budget.get("hurdle", 0.04))
    recommended = {str(k).lower(): float(v) for k, v in budget.get("presupuesto", {}).items()}
    usable = {n: w for n, w in current.items() if n in columns}
    rec = cvar_contributions(columns, {n: recommended.get(n, 0.0) for n in columns}, hurdle=hurdle)
    now = cvar_contributions(columns, {n: usable.get(n, 0.0) for n in columns}, hurdle=hurdle)
    names = sorted(set(rec) | set(now))
    return pl.DataFrame(
        {
            "parte": [*names, "total (CVaR95)"],
            "con el presupuesto": [_pct(rec.get(n, 0.0)) for n in names]
            + [_pct(sum(rec.values()))],
            "con el paper ahora": [_pct(now.get(n, 0.0)) for n in names]
            + [_pct(sum(now.values()))],
        }
    )


def _pct(value: float) -> str:
    return style.pct(value + 0.0, 2)  # + 0.0 convierte -0.0 en 0.0: «-0,00 %» confunde


def daily_paper_equity(valuations: Sequence[PortfolioValued]) -> pl.DataFrame:
    """Capital del paper al final de cada día UTC, con el inicio en 1."""
    if not valuations:
        return pl.DataFrame(schema={"día": pl.Int64, "paper": pl.Float64})
    start = valuations[0]
    by_day: dict[int, float] = {0: 1.0}
    for v in valuations:
        day = (v.occurred_at.date() - start.occurred_at.date()).days
        by_day[day] = float(v.equity / start.equity)
    days = sorted(by_day)
    return pl.DataFrame({"día": days, "paper": [by_day[d] for d in days]})


def development_returns(returns: pl.DataFrame, selected: str) -> np.ndarray:
    """Retornos diarios del desarrollo de la configuración elegida, sin el día del holdout."""
    dates = returns["date"].cast(pl.Utf8).str.to_datetime(time_zone="UTC")
    mask = (dates < HOLDOUT_START).to_numpy()
    return np.asarray(returns[selected].to_numpy()[mask], dtype=np.float64)


def bands_frame(paper: pl.DataFrame, daily: np.ndarray) -> pl.DataFrame:
    """El paper frente a las bandas del 5 %, la mediana y el 95 % que esperaba el backtest."""
    horizon = int(paper["día"].to_list()[-1]) if paper.height else 0  # ordenado por día
    if horizon < 1:
        return pl.DataFrame()
    q05, q50, q95 = bootstrap_bands(daily, horizon)
    frame = pl.DataFrame(
        {
            "día": list(range(horizon + 1)),
            "backtest p5": [1.0, *q05.tolist()],
            "backtest mediana": [1.0, *q50.tolist()],
            "backtest p95": [1.0, *q95.tolist()],
        }
    )
    return frame.join(paper, on="día", how="left")
