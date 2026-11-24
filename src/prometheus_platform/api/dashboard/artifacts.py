"""Lectura de los artefactos que muestra el dashboard (sin Streamlit, para poder testearla).

El dashboard es de **solo lectura**: no recalcula ni descarga nada. Si un artefacto no existe,
se informa qué comando lo genera (degradación elegante) en vez de fallar.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from prometheus_platform.api.dashboard import style

HYPOTHESES = ("H1", "H2")
MODEL_MODES = ("residual", "level")


@dataclass(frozen=True)
class Missing:
    artifact: str
    command: str


@dataclass
class Artifacts:
    quality: list[dict[str, Any]] = field(default_factory=list)
    carry: dict[str, dict[str, Any]] = field(default_factory=dict)
    carry_returns: dict[str, pl.DataFrame] = field(default_factory=dict)
    model: dict[str, Any] | None = None
    model_mode: str | None = None
    simulation: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None  # PQ-83: presupuesto recomendado
    budget_scenarios: pl.DataFrame | None = None
    trend: dict[str, dict[str, Any]] = field(default_factory=dict)  # T1, T2 y holdout (PQ-68)
    carry_holdout: dict[str, Any] | None = None  # holdout de H2 (PQ-50)
    missing: list[Missing] = field(default_factory=list)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_artifacts(data_dir: Path) -> Artifacts:
    art = Artifacts()
    quality_dir = data_dir / "silver" / "_quality"
    art.quality = [
        q for p in sorted(quality_dir.glob("*.json")) if (q := _read_json(p)) is not None
    ]
    if not art.quality:
        art.missing.append(Missing("calidad de silver", "uv run pq silver build --symbol <S>"))

    for hyp in HYPOTHESES:
        folder = data_dir / "research" / "carry" / hyp
        summary = _read_json(folder / "summary.json")
        if summary is None:
            art.missing.append(
                Missing(f"carry {hyp}", f"uv run pq research carry --hypothesis {hyp} --figures …")
            )
            continue
        art.carry[hyp] = summary
        returns = folder / "daily_returns.parquet"
        if returns.exists():
            art.carry_returns[hyp] = pl.read_parquet(returns)

    # La formulación oficial del cap. 5 es la residual (v2); level (v1) queda como respaldo.
    for mode in MODEL_MODES:
        art.model = _read_json(data_dir / "research" / "funding_model" / mode / "summary.json")
        if art.model is not None:
            art.model_mode = mode
            break
    if art.model is None:
        art.missing.append(
            Missing("modelo de funding", "uv run pq research funding-model --figures …")
        )
    art.simulation = _read_json(data_dir / "research" / "simulation" / "summary.json")
    if art.simulation is None:
        art.missing.append(Missing("simulación", "uv run pq research simulate --figures …"))
    art.carry_holdout = _read_json(data_dir / "research" / "carry" / "holdout" / "summary.json")
    for name in ("T1", "T2", "holdout"):
        trend = _read_json(data_dir / "research" / "trend" / name / "summary.json")
        if trend is not None:
            art.trend[name] = trend
    budget_dir = data_dir / "research" / "budget"
    art.budget = _read_json(budget_dir / "summary.json")
    if art.budget is None:
        art.missing.append(Missing("presupuesto de capital", "uv run pq research budget"))
    elif (budget_dir / "scenarios.parquet").exists():
        art.budget_scenarios = pl.read_parquet(budget_dir / "scenarios.parquet")
    return art


@dataclass(frozen=True)
class StrategyStatus:
    """Una estrategia en una línea, para la portada: dónde está y qué significa."""

    name: str
    level: str  # "ok", "warn" o "bad"
    stage: str
    summary: str


def strategy_overview(art: Artifacts) -> list[StrategyStatus]:
    """Estado de cada estrategia según sus artefactos, en lenguaje simple (PQ-124)."""
    out: list[StrategyStatus] = []
    h2 = art.carry.get("H2")
    if art.carry_holdout is not None:
        perf = art.carry_holdout.get("rendimiento", {})
        passed = bool(art.carry_holdout.get("pasa"))
        failed_text = (
            f"Con datos nunca vistos ganó {style.pct(perf.get('cagr'), 2)} anual (se exigía más "
            "de 4 %): desde 2025 el funding nunca llegó al umbral de entrada. El paper trading "
            "sigue como demostración del sistema, no como estrategia aprobada."
        )
        out.append(
            StrategyStatus(
                "Carry de funding",
                "ok" if passed else "bad",
                "Aprobada en la prueba final" if passed else "Descartada en la prueba final",
                "Superó la prueba final con datos nunca vistos." if passed else failed_text,
            )
        )
    elif h2 is not None:
        perf = h2.get("selected_performance", {})
        if h2.get("passed"):
            out.append(
                StrategyStatus(
                    "Carry de funding",
                    "warn",
                    "Aprobada en desarrollo · prueba final pendiente",
                    f"Pasó las 4 condiciones mínimas con {style.pct(perf.get('cagr'))} anual y "
                    f"una peor caída de {style.pct(perf.get('max_drawdown'))}. Corre en paper "
                    "trading mientras espera la prueba final con datos nunca vistos.",
                )
            )
        else:
            out.append(
                StrategyStatus(
                    "Carry de funding",
                    "bad",
                    "Descartada en desarrollo",
                    "No cumplió las condiciones mínimas fijadas de antemano.",
                )
            )
    holdout, t1 = art.trend.get("holdout"), art.trend.get("T1")
    if holdout is not None:
        perf = holdout.get("rendimiento", {})
        if holdout.get("pasa"):
            stage, level = "Aprobada en la prueba final", "ok"
            text = "Superó la prueba final con datos nunca vistos."
        else:
            stage, level = "Descartada en la prueba final", "bad"
            text = (
                f"Parecía buena en desarrollo, pero con datos nunca vistos ganó "
                f"{style.pct(perf.get('cagr'))} anual (se exigía más de 4 %). Controló el riesgo "
                f"(peor caída {style.pct(perf.get('max_drawdown'))}) pero no dio retorno."
            )
        out.append(StrategyStatus("Tendencia", level, stage, text))
    elif t1 is not None:
        level, stage = (
            ("warn", "Aprobada en desarrollo · prueba final pendiente")
            if t1.get("passed")
            else ("bad", "Descartada en desarrollo")
        )
        out.append(StrategyStatus("Tendencia", level, stage, "Ver la evaluación de tendencia."))
    return out


def quality_table(quality: list[dict[str, Any]]) -> pl.DataFrame:
    rows = [
        {
            "tabla": q.get("table", "?"),
            "filas": q.get("rows", 0),
            "huecos": q.get("gaps", 0),
            "periodos faltantes": q.get("missing_periods", 0),
            "hueco mayor (h)": q.get("largest_gap_hours", 0.0),
            "outliers": q.get("outliers", 0),
            "desde": str(q.get("first", ""))[:10],
            "hasta": str(q.get("last", ""))[:10],
        }
        for q in quality
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def gates_table(summary: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "condición": g["name"],
                "criterio": g["criterion"],
                "valor": style.number(float(g["value"]), 3),
                "resultado": style.status(bool(g["passed"])),
            }
            for g in summary.get("gates", [])
        ]
    )


def performance_table(summary: dict[str, Any]) -> pl.DataFrame:
    selected = summary.get("selected_performance", {})
    bench = summary.get("benchmark_B1", {})
    metrics = ("sharpe", "cagr", "max_drawdown", "calmar", "t_stat")
    return pl.DataFrame(
        {
            "métrica": [style.metric_label(m) for m in metrics],
            f"estrategia ({summary.get('selected', '?')})": [
                style.metric_value(m, _num(selected.get(m))) for m in metrics
            ],
            "referencia: siempre invertido": [
                style.metric_value(m, _num(bench.get(m))) for m in metrics
            ],
            "qué significa": [style.METRICS[m][1] for m in metrics],
        }
    )


def equity_curves(returns: pl.DataFrame, selected: str) -> pl.DataFrame:
    """Crecimiento de 1 USD con la configuración seleccionada (la elegida por CPCV)."""
    if selected not in returns.columns:
        return pl.DataFrame()
    return returns.select(
        pl.col("date").str.slice(0, 10).str.to_date().alias("fecha"),
        (1 + pl.col(selected)).cum_prod().alias(selected),
    )


def model_tables(model: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    regression = pl.DataFrame(
        [
            {
                "modelo": r["name"] + (" (ajustado)" if r.get("tuned") else ""),
                "RMSE": _num(r.get("rmse")),
                "MAE": _num(r.get("mae")),
                "R²": _num(r.get("r2")),
            }
            for r in model.get("regression", [])
        ]
    )
    classification = pl.DataFrame(
        [
            {
                "modelo": c["name"] + (" (ajustado)" if c.get("tuned") else ""),
                "AUC": _num(c.get("auc")),
                "F1": _num(c.get("f1")),
            }
            for c in model.get("classification", [])
        ]
    )
    return regression, classification


def scenario_table(simulation: dict[str, Any]) -> pl.DataFrame:
    rows = [
        {
            "escenario": name,
            "media": _num(s.get("media")),
            "mediana": _num(s.get("mediana")),
            "P(< 4 %)": _num(s.get("prob_bajo_hurdle")),
            "P(pérdida)": _num(s.get("prob_perdida")),
            "CVaR 95 %": _num(s.get("cvar95")),
        }
        for name, s in simulation.get("escenarios", {}).items()
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def validation_table(simulation: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "modelo": v["model"],
                "ciclos/año": _num(v.get("cycles")),
                "retorno medio": _num(v.get("mean_return")),
                "tiempo invertido": _num(v.get("invested")),
            }
            for v in simulation.get("validacion", [])
        ]
    )


def transition_table(simulation: dict[str, Any]) -> pl.DataFrame:
    chain = simulation.get("markov_bloques") or simulation.get("markov_1er_orden") or {}
    states = simulation.get("markov_1er_orden", {}).get("estados", ["negativo", "base", "alto"])
    matrix = chain.get("transicion", [])
    if not matrix:
        return pl.DataFrame()
    return pl.DataFrame(
        {
            "desde \\ hacia": states,
            **{s: [_num(r[j]) for r in matrix] for j, s in enumerate(states)},
        }
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else round(number, 4)
