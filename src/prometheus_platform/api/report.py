"""Entradas del informe ejecutivo en Quarto (PQ-39).

Ningún número del informe se copia a mano: este módulo lee los artefactos de ``data/`` y escribe
``_resultados.yml`` (cifras ya formateadas, que el ``.qmd`` usa con ``{{< meta r.… >}}``),
tablas en Markdown (``_tablas/``) y las figuras (``_img/``). Si falta un artefacto, sus cifras
quedan como «n/d» y la tabla lo dice; el informe se genera igual.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import polars as pl

from prometheus_platform.api.dashboard.artifacts import (
    Artifacts,
    gates_table,
    load_artifacts,
    quality_table,
    scenario_table,
    validation_table,
)

NA = "n/d"
# nombre -> (ruta en el repo, pie de figura)
FIGURES: Mapping[str, tuple[str, str]] = {
    "h2-curvas": (
        "docs/estrategias/01-carry/img/h2-curvas.png",
        "Capital de 1 USD con el carry H2 frente al benchmark siempre activo (desarrollo).",
    ),
    "roc-funding": (
        "docs/investigacion/img/roc-funding.png",
        "Curvas ROC: ¿la próxima tasa superará el 20 % anual?",
    ),
    "markov-transiciones": (
        "docs/investigacion/img/markov-transiciones.png",
        "Probabilidad de pasar de un régimen de funding a otro.",
    ),
    "montecarlo-retornos": (
        "docs/investigacion/img/montecarlo-retornos.png",
        "Retorno anual simulado del carry H2 (10.000 trayectorias).",
    ),
    "asignacion-frontera": (
        "docs/investigacion/img/asignacion-frontera.png",
        "Retorno esperado y CVaR según la fracción del capital en el carry.",
    ),
}


def pct(value: Any, decimals: int = 1) -> str:
    """0.0503 -> «5,0 %» (formato español)."""
    if value is None:
        return NA
    return f"{float(value) * 100:.{decimals}f}".replace(".", ",") + " %"


def num(value: Any, decimals: int = 2) -> str:
    if value is None:
        return NA
    return f"{float(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def to_markdown(frame: pl.DataFrame, formats: Mapping[str, str] | None = None) -> str:
    """Tabla pipe de Markdown. ``formats`` indica por columna «pct», «pct2», «num» o «int»."""
    if frame.is_empty():
        return "*Sin datos.*\n"
    formats = formats or {}
    header = "| " + " | ".join(frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    rows = []
    for row in frame.iter_rows(named=True):
        cells = []
        for col, value in row.items():
            kind = formats.get(col)
            if kind == "pct":
                cells.append(pct(value))
            elif kind == "pct2":
                cells.append(pct(value, 2))
            elif kind == "num":
                cells.append(num(value))
            elif kind == "int":
                cells.append(num(value, 0))
            else:
                cells.append(NA if value is None else str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, rule, *rows]) + "\n"


def _carry_values(summary: dict[str, Any] | None) -> dict[str, str]:
    if summary is None:
        return dict.fromkeys(
            (
                "simbolos",
                "config",
                "cagr",
                "sharpe",
                "max_dd",
                "b1_cagr",
                "b1_sharpe",
                "pbo",
                "dsr",
                "veredicto",
                "fallidos",
            ),
            NA,
        )
    sel, b1 = summary.get("selected_performance", {}), summary.get("benchmark_B1", {})
    failed = [g["name"] for g in summary.get("gates", []) if not g["passed"]]
    return {
        "simbolos": ", ".join(summary.get("symbols", [])),
        "config": str(summary.get("selected", NA)),
        "cagr": pct(sel.get("cagr")),
        "sharpe": num(sel.get("sharpe")),
        "max_dd": pct(sel.get("max_drawdown"), 2),
        "b1_cagr": pct(b1.get("cagr")),
        "b1_sharpe": num(b1.get("sharpe")),
        "pbo": pct(summary.get("pbo")),
        "dsr": num(summary.get("dsr"), 3),
        "veredicto": "pasa los cuatro gates" if not failed else f"no pasa {', '.join(failed)}",
        "fallidos": ", ".join(failed) if failed else "ninguno",
    }


def _model_values(model: dict[str, Any] | None) -> dict[str, str]:
    if model is None:
        return dict.fromkeys(("r2_mejor", "r2_persistencia", "dm", "dm_p", "auc", "mejor"), NA)
    regression = model.get("regression", [])
    persistence = next((r for r in regression if r["name"] == "persistencia"), None)
    best = max(regression, key=lambda r: r.get("r2", float("-inf")), default=None)
    classifiers = model.get("classification", [])
    best_clf = max(classifiers, key=lambda c: c.get("auc", 0.0), default=None)
    dm = model.get("diebold_mariano", {})
    return {
        "r2_mejor": num(best.get("r2") if best else None, 3),
        "r2_persistencia": num(persistence.get("r2") if persistence else None, 3),
        "mejor": str(dm.get("best_model", NA)),
        "dm": num(dm.get("dm")),
        "dm_p": num(dm.get("p_value"), 3),
        "auc": num(best_clf.get("auc") if best_clf else None, 3),
    }


def _simulation_values(sim: dict[str, Any] | None) -> dict[str, str]:
    keys = (
        "media",
        "mediana",
        "p_bajo_4",
        "p_perdida",
        "media_p2",
        "media_p5",
        "quiebra_equilibrio",
        "max_carry_cvar",
        "ciclos_hist",
        "ciclos_sim",
    )
    if sim is None:
        return dict.fromkeys(keys, NA)
    scenarios = list(sim.get("escenarios", {}).values())
    base = scenarios[0] if scenarios else {}
    frontier = sim.get("frontera", [])
    allowed = [f["w_carry"] for f in frontier if f.get("cumple")]
    validation = sim.get("validacion", [])
    return {
        "media": pct(base.get("media"), 2),
        "mediana": pct(base.get("mediana"), 2),
        "p_bajo_4": pct(base.get("prob_bajo_hurdle"), 0),
        "p_perdida": pct(base.get("prob_perdida"), 0),
        "media_p2": pct(scenarios[1].get("media") if len(scenarios) > 1 else None, 2),
        "media_p5": pct(scenarios[2].get("media") if len(scenarios) > 2 else None, 2),
        "quiebra_equilibrio": pct(sim.get("probabilidad_quiebra_equilibrio"), 2),
        "max_carry_cvar": pct(max(allowed) if allowed else None, 0),
        "ciclos_hist": num(validation[0].get("cycles") if validation else None, 1),
        "ciclos_sim": num(validation[-1].get("cycles") if validation else None, 1),
    }


def _data_values(art: Artifacts) -> dict[str, str]:
    if not art.quality:
        return dict.fromkeys(("tablas", "filas", "con_huecos", "desde"), NA)
    table = quality_table(art.quality)
    return {
        "tablas": str(table.height),
        "filas": num(table["filas"].sum(), 0),
        "con_huecos": str(table.filter(pl.col("huecos") > 0).height),
        "desde": str(table["desde"].min()),
    }


def build_report_inputs(data_dir: Path, repo_root: Path, out_dir: Path) -> list[str]:
    """Escribe las entradas del informe. Devuelve los artefactos que faltaban."""
    art = load_artifacts(data_dir)
    values = {
        "datos": _data_values(art),
        "h1": _carry_values(art.carry.get("H1")),
        "h2": _carry_values(art.carry.get("H2")),
        "modelo": _model_values(art.model),
        "sim": _simulation_values(art.simulation),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    # JSON es YAML válido: así no hace falta otra dependencia.
    (out_dir / "_resultados.yml").write_text(
        json.dumps({"r": values}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tables = out_dir / "_tablas"
    tables.mkdir(exist_ok=True)
    pending = "*Artefacto no disponible: {}.*\n"
    for hyp in ("H1", "H2"):
        summary = art.carry.get(hyp)
        text = (
            to_markdown(gates_table(summary), {"valor": "num"})
            if summary
            else pending.format(f"carry {hyp}")
        )
        (tables / f"gates-{hyp.lower()}.md").write_text(text, encoding="utf-8")
    quality = quality_table(art.quality)
    (tables / "calidad.md").write_text(
        to_markdown(quality.select("tabla", "filas", "huecos", "desde", "hasta"), {"filas": "int"})
        if not quality.is_empty()
        else pending.format("calidad de silver"),
        encoding="utf-8",
    )
    sim = art.simulation
    (tables / "escenarios.md").write_text(
        to_markdown(
            scenario_table(sim),
            {
                "media": "pct2",
                "mediana": "pct2",
                "P(< 4 %)": "pct",
                "P(pérdida)": "pct",
                "CVaR 95 %": "pct",
            },
        )
        if sim
        else pending.format("simulación"),
        encoding="utf-8",
    )
    (tables / "validacion.md").write_text(
        to_markdown(
            validation_table(sim),
            {"ciclos/año": "num", "retorno medio": "pct", "tiempo invertido": "pct"},
        )
        if sim
        else pending.format("simulación"),
        encoding="utf-8",
    )

    images = out_dir / "_img"
    images.mkdir(exist_ok=True)
    figures = out_dir / "_figuras"
    figures.mkdir(exist_ok=True)
    for name, (source, caption) in FIGURES.items():
        if (repo_root / source).exists():
            shutil.copyfile(repo_root / source, images / f"{name}.png")
            snippet = f"![{caption}](_img/{name}.png){{width=90%}}\n"
        else:
            snippet = f"*Figura no disponible ({source}).*\n"
        (figures / f"{name}.md").write_text(snippet, encoding="utf-8")
    return [m.artifact for m in art.missing]
