"""``pq research budget`` (PQ-83): presupuesto de capital entre las estrategias aprobadas.

Lee los artefactos de las evaluaciones de desarrollo (``data/research/{carry,trend}/<H>/``):

- una estrategia está **aprobada** si su ``summary.json`` pasa los cuatro gates;
- de cada aprobada se toman los retornos diarios de la configuración elegida, **solo del
  desarrollo** (fechas anteriores a ``HOLDOUT_START``; ver KE-014), alineados por fecha;
- la probabilidad de quiebra de equilibrio sale del capítulo 6
  (``data/research/simulation/summary.json``).

Con eso optimiza el presupuesto (``portfolio_risk.budget``) y escribe
``data/research/budget/summary.json``, que leen el dashboard (PQ-84) y el runner. No elige ninguna
estrategia ni configuración, así que no es un ensayo: queda registrado como ejecución descriptiva.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.domain.protocol import HOLDOUT_START
from prometheus_platform.portfolio_risk.budget import (
    HURDLE,
    apply_exchange_failures,
    cvar_contributions,
    exchange_cap,
    frontier,
    joint_annual_scenarios,
    optimize_budget,
)

FAMILIES = ("carry", "trend")
EXCHANGE = "binance"  # todas las estrategias de hoy operan en Binance
CVAR_LIMIT = 0.05  # el tope del capítulo 6
ASSUMED_FAILURE = 0.02  # el escenario moderado de quiebra del capítulo 6


@dataclass(frozen=True, slots=True)
class Approved:
    name: str  # p. ej. «carry-H2»
    config: str  # la configuración elegida por CPCV
    exchange: str
    returns: pl.DataFrame  # fecha y retorno diario del desarrollo


def approved_strategies(research: Path) -> list[Approved]:
    out = []
    for family in FAMILIES:
        for summary_path in sorted((research / family).glob("*/summary.json")):
            summary: dict[str, Any] = json.loads(summary_path.read_text(encoding="utf-8"))
            if not summary.get("passed"):
                continue
            selected = str(summary["selected"])
            frame = pl.read_parquet(summary_path.parent / "daily_returns.parquet")
            dates = frame["date"].cast(pl.Utf8).str.to_datetime(time_zone="UTC")
            daily = pl.DataFrame({"date": dates, "ret": frame[selected]}).filter(
                pl.col("date") < HOLDOUT_START  # KE-014: la valoración del 01-07 es del holdout
            )
            name = f"{family}-{summary_path.parent.name}"
            out.append(Approved(name, selected, EXCHANGE, daily))
    return out


def break_even_probability(research: Path) -> float:
    path = research / "simulation" / "summary.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return float(data["probabilidad_quiebra_equilibrio"])


@dataclass(frozen=True, slots=True)
class BudgetRun:
    summary: dict[str, Any]
    # Retornos anuales simulados con quiebra, por estrategia: el dashboard calcula con ellos el
    # CVaR de la asignación que tenga el paper en cada momento (PQ-84).
    scenarios: dict[str, np.ndarray]


def run(research: Path, *, n_paths: int = 10_000) -> BudgetRun:
    strategies = approved_strategies(research)
    p_star = break_even_probability(research)
    cap = exchange_cap(
        cvar_limit=CVAR_LIMIT, assumed_probability=ASSUMED_FAILURE, break_even_probability=p_star
    )
    result: dict[str, Any] = {
        "generado": datetime.now(HOLDOUT_START.tzinfo).isoformat(timespec="seconds"),
        "estrategias_aprobadas": [s.name for s in strategies],
        "configuraciones": {s.name: s.config for s in strategies},
        "cvar_limite": CVAR_LIMIT,
        "hurdle": HURDLE,
        "quiebra_supuesta": ASSUMED_FAILURE,
        "quiebra_equilibrio": p_star,
        "tope_por_exchange": {EXCHANGE: cap},
    }
    if not strategies:
        result.update(presupuesto={}, efectivo=1.0, retorno_esperado=HURDLE, cvar95=-HURDLE)
        return BudgetRun(result, {})
    aligned = strategies[0].returns.rename({"ret": strategies[0].name})
    for s in strategies[1:]:
        aligned = aligned.join(s.returns.rename({"ret": s.name}), on="date", how="inner")
    daily = {s.name: aligned[s.name].to_numpy().astype(np.float64) for s in strategies}
    exchange_of = {s.name: s.exchange for s in strategies}
    annual = joint_annual_scenarios(daily, n_paths=n_paths)
    stressed = apply_exchange_failures(annual, exchange_of, {EXCHANGE: ASSUMED_FAILURE})
    budget = optimize_budget(stressed, exchange_of, caps={EXCHANGE: cap}, cvar_limit=CVAR_LIMIT)
    correlation = np.corrcoef(np.column_stack(list(daily.values())), rowvar=False)
    result.update(
        dias_desarrollo=aligned.height,
        periodo=[str(aligned["date"].min()), str(aligned["date"].max())],
        correlacion=np.atleast_2d(correlation).round(4).tolist(),
        presupuesto=budget.weights,
        efectivo=budget.cash,
        retorno_esperado=budget.expected_return,
        cvar95=budget.cvar95,
        contribucion_cvar=cvar_contributions(stressed, budget.weights),
        por_exchange=budget.by_exchange,
        frontera=frontier(stressed),
        sin_quiebra=asdict(
            optimize_budget(annual, exchange_of, caps={EXCHANGE: cap}, cvar_limit=CVAR_LIMIT)
        ),
    )
    return BudgetRun(result, stressed)


def write(run_result: BudgetRun, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.json"
    path.write_text(json.dumps(run_result.summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if run_result.scenarios:
        pl.DataFrame(run_result.scenarios).write_parquet(out_dir / "scenarios.parquet")
    return path
