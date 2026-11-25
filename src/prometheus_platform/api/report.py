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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.adapters.trial_ledger import counts
from prometheus_platform.api.dashboard.artifacts import (
    Artifacts,
    gates_table,
    load_artifacts,
    quality_table,
    scenario_table,
    validation_table,
)
from prometheus_platform.api.paper.report import PaperView, build_view

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


def _read_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _stats_values(stats: dict[str, Any] | None) -> dict[str, str]:
    """Pruebas de hipótesis del cap. 7.4 (``pq research stats``)."""
    keys = ("he1_exceso", "he1_p", "he1_veredicto", "he2_media", "he2_p", "he2_veredicto")
    if stats is None:
        return dict.fromkeys((*keys, "he3_p", "he3_w"), NA)
    values: dict[str, str] = {}
    for name in ("he1", "he2"):
        test = stats.get(name, {})
        values[f"{name}_p"] = num(test.get("p_hac"), 3)
        rejected = test.get("reject_h0")
        values[f"{name}_veredicto"] = (
            NA if rejected is None else ("se rechaza" if rejected else "no se rechaza")
        )
    values["he1_exceso"] = pct(stats.get("he1", {}).get("mean_annualized"), 2)
    values["he2_media"] = pct(stats.get("he2", {}).get("mean_annualized"), 2)
    he3 = stats.get("he3", {})
    p_friedman = he3.get("friedman_p")
    values["he3_p"] = NA if p_friedman is None else f"{float(p_friedman):.1e}"
    values["he3_w"] = num(he3.get("kendall_w"), 3)
    return values


def _finance_values(finance: dict[str, Any] | None) -> dict[str, str]:
    """VAN y capital de equilibrio del cap. 8.3 a 8.4 (``pq research finance``).

    La referencia es la del informe de PQ-49: Oracle Always Free, 1.000 USD, 3 años, sin quiebra.
    """
    keys = ("van_1000_3a", "equilibrio", "van_negativo")
    if finance is None:
        return dict.fromkeys(keys, NA)
    base = next(iter(finance.get("escenarios", {})), None)
    rows = finance.get("evaluaciones", [])
    ref = next(
        (
            e
            for e in rows
            if e["escenario"] == base
            and str(e["infraestructura"]).startswith("Oracle")
            and e["capital"] == 1_000
            and e["anios"] == 3
        ),
        None,
    )
    equilibrium = ref.get("capital_equilibrio") if ref else None
    negatives = sum(1 for e in rows if e["van"] < 0)
    return {
        "van_1000_3a": NA if ref is None else f"{num(ref['van'], 0)} USD",
        "equilibrio": (
            NA
            if ref is None
            else "no existe"
            if equilibrium is None
            else f"{num(equilibrium, 0)} USD"
        ),
        "van_negativo": (
            NA
            if not rows
            else "en todos los casos evaluados"
            if negatives == len(rows)
            else f"en {negatives} de {len(rows)} casos"
        ),
    }


def _holdout_values(summary: dict[str, Any] | None) -> dict[str, str]:
    """La prueba final (holdout) de una estrategia: rendimiento y veredicto."""
    if summary is None:
        return dict.fromkeys(("cagr", "sharpe", "max_dd", "veredicto", "config"), NA)
    perf = summary.get("rendimiento", {})
    return {
        "cagr": pct(perf.get("cagr"), 2),
        "sharpe": num(perf.get("sharpe")),
        "max_dd": pct(perf.get("max_drawdown")),
        "veredicto": "pasa" if summary.get("pasa") else "descartada",
        "config": str(summary.get("seleccionada", NA)),
    }


def _ledger_values(ledger_dir: Path) -> dict[str, str]:
    """N del registro de ensayos compartido (PQ-112): lo que cuenta en el Deflated Sharpe."""
    if not any(ledger_dir.glob("*.jsonl")):
        return dict.fromkeys(("total", "carry", "modelo", "tendencia", "otras"), NA)
    n = counts(ledger_dir)
    named = {"carry", "modelo-funding", "tendencia"}
    return {
        "total": str(n["total"]),
        "carry": str(n.get("carry", 0)),
        "modelo": str(n.get("modelo-funding", 0)),
        "tendencia": str(n.get("tendencia", 0)),
        # El resto de familias (Polymarket, ML...): así el desglose siempre suma el total.
        "otras": str(sum(v for k, v in n.items() if k not in named and k != "total")),
    }


def build_report_inputs(data_dir: Path, repo_root: Path, out_dir: Path) -> list[str]:
    """Escribe las entradas del informe. Devuelve los artefactos que faltaban."""
    art = load_artifacts(data_dir)
    research = data_dir / "research"
    values = {
        "datos": _data_values(art),
        "h1": _carry_values(art.carry.get("H1")),
        "h2": _carry_values(art.carry.get("H2")),
        "modelo": _model_values(art.model),
        "sim": _simulation_values(art.simulation),
        "stats": _stats_values(_read_summary(research / "stats" / "summary.json")),
        "finanzas": _finance_values(_read_summary(research / "finance" / "summary.json")),
        "ensayos": _ledger_values(repo_root / "docs" / "estrategias" / "ensayos"),
        "final_carry": _holdout_values(
            _read_summary(research / "carry" / "holdout" / "summary.json")
        ),
        "final_tendencia": _holdout_values(
            _read_summary(research / "trend" / "holdout" / "summary.json")
        ),
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
            to_markdown(gates_table(summary))  # la tabla ya viene formateada (PQ-124)
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
        to_markdown(scenario_table(sim))  # ya viene en formato español (PQ-126)
        if sim
        else pending.format("simulación"),
        encoding="utf-8",
    )
    (tables / "validacion.md").write_text(
        to_markdown(validation_table(sim))  # ya viene en formato español (PQ-126)
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


# --- Página pública de resultados (PQ-89) -----------------------------------------------------

DISCLAIMER = (
    '!!! warning "No es asesoramiento financiero"\n'
    "    Proyecto universitario de investigación. Los resultados son del periodo de\n"
    "    desarrollo y de **paper trading con dinero simulado**; rentabilidades pasadas no\n"
    "    garantizan las futuras. Nada de esta página es una recomendación de inversión.\n"
)
PAPER_DAYS_SHOWN = 14


def paper_daily(view: PaperView) -> pl.DataFrame:
    """Un renglón por día UTC con valoración: equity al cierre, funding, costes y órdenes."""
    days = sorted({v.occurred_at.date() for v in view.valuations})
    rows = []
    for day in days:
        closing = [v.equity for v in view.valuations if v.occurred_at.date() == day][-1]
        rows.append(
            {
                "día (UTC)": day.isoformat(),
                "equity (USD)": float(closing),
                "funding (USD)": float(
                    sum((s.amount for s in view.settlements if s.funding_time.date() == day), 0)
                ),
                "costes (USD)": float(sum((f.cost for f in view.fills if f.at.date() == day), 0)),
                "órdenes": sum(1 for f in view.fills if f.at.date() == day),
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _max_drawdown(view: PaperView) -> float | None:
    peak, worst = None, 0.0
    for v in view.valuations:
        equity = float(v.equity)
        peak = equity if peak is None else max(peak, equity)
        if peak > 0:
            worst = max(worst, 1 - equity / peak)
    return None if peak is None else worst


def _paper_section(paper_dir: Path) -> str:
    journal = paper_dir / "diario.jsonl"
    if not journal.exists():
        return "*Todavía no hay historial de paper trading.*\n"
    view = build_view(JsonlEventJournal(journal).replay())
    if not view.valuations:
        return "*El paper trading aún no registró valoraciones.*\n"
    first, last = view.valuations[0], view.valuations[-1]
    change = float(last.equity / first.equity - 1) if first.equity > 0 else None
    summary = pl.DataFrame(
        [
            {"medida": "Desde", "valor": first.occurred_at.date().isoformat()},
            {"medida": "Capital inicial (simulado)", "valor": f"{num(first.equity)} USD"},
            {"medida": "Capital actual (simulado)", "valor": f"{num(last.equity)} USD"},
            {"medida": "Variación", "valor": pct(change, 3)},
            {"medida": "Caída máxima", "valor": pct(_max_drawdown(view), 3)},
            {"medida": "Funding cobrado", "valor": f"{num(view.funding, 4)} USD"},
            {"medida": "Comisiones y slippage", "valor": f"{num(view.costs, 4)} USD"},
            {"medida": "Órdenes ejecutadas", "valor": str(len(view.fills))},
            {"medida": "Activaciones del kill-switch", "valor": str(len(view.kill_events))},
        ]
    )
    daily = paper_daily(view).tail(PAPER_DAYS_SHOWN)
    note = (
        "\nTodavía no hubo operaciones: la regla de entrada del carry H2 no dio señal en este "
        "periodo, así que el capital sigue en efectivo.\n"
        if not view.fills and not view.breaches
        else ""
    )
    formats = {"equity (USD)": "num", "funding (USD)": "num", "costes (USD)": "num"}
    return (
        to_markdown(summary)
        + note
        + f"\n**Últimos {PAPER_DAYS_SHOWN} días con actividad**\n\n"
        + to_markdown(daily, formats)
    )


def build_public_page(data_dir: Path, repo_root: Path, now: datetime) -> str:
    """Markdown de ``docs/resultados.md``: solo agregados, sin claves ni identificadores."""
    art = load_artifacts(data_dir)
    research = data_dir / "research"
    h1, h2 = _carry_values(art.carry.get("H1")), _carry_values(art.carry.get("H2"))
    stats = _stats_values(_read_summary(research / "stats" / "summary.json"))
    sim = _simulation_values(art.simulation)
    ledger = _ledger_values(repo_root / "docs" / "estrategias" / "ensayos")
    carry = pl.DataFrame(
        [
            {
                "hipótesis": f"{name} ({v['simbolos']})",
                "retorno anual": v["cagr"],
                "siempre invertido": v["b1_cagr"],
                "caída máx.": v["max_dd"],
                "PBO": v["pbo"],
                "DSR": v["dsr"],
                "veredicto": v["veredicto"],
            }
            for name, v in (("H1", h1), ("H2", h2))
        ]
    )
    h2_summary = art.carry.get("H2")
    gates = to_markdown(gates_table(h2_summary)) if h2_summary else "*Artefacto no disponible.*\n"
    finals = pl.DataFrame(
        [
            {
                "estrategia": name,
                "configuración": v["config"],
                "retorno anual": v["cagr"],
                "Sharpe": v["sharpe"],
                "caída máx.": v["max_dd"],
                "veredicto": v["veredicto"],
            }
            for name, v in (
                (
                    "Carry H2",
                    _holdout_values(_read_summary(research / "carry/holdout/summary.json")),
                ),
                (
                    "Tendencia T1",
                    _holdout_values(_read_summary(research / "trend/holdout/summary.json")),
                ),
            )
        ]
    )
    tests = pl.DataFrame(
        [
            {
                "prueba": "HE1: H2 rinde más que estar siempre invertido",
                "resultado": f"{stats['he1_exceso']} al año; p = {stats['he1_p']}",
                "H0": stats["he1_veredicto"],
            },
            {
                "prueba": "HE2: H2 rinde más que una stablecoin al 4 %",
                "resultado": f"{stats['he2_media']} al año; p = {stats['he2_p']}",
                "H0": stats["he2_veredicto"],
            },
            {
                "prueba": "HE3: las configuraciones difieren (Friedman)",
                "resultado": f"p = {stats['he3_p']}; W de Kendall = {stats['he3_w']}",
                "H0": NA if stats["he3_p"] == NA else "se rechaza",
            },
        ]
    )
    return "\n".join(
        [
            "# Resultados",
            "",
            "<!-- Generado con `uv run pq report public`: no lo edites a mano. -->",
            "",
            DISCLAIMER,
            f"*Actualizado: {now.astimezone(UTC):%Y-%m-%d %H:%M} UTC. Cada cifra sale de un "
            "artefacto del repositorio; nada se copia a mano.*",
            "",
            "## ¿Funciona? El carry de funding en el periodo de desarrollo",
            "",
            "Neto de comisiones VIP 0 y slippage, de enero de 2020 a junio de 2024. La prueba "
            "final, con datos nunca vistos (julio de 2024 a septiembre de 2026), va en la sección "
            "siguiente.",
            "",
            to_markdown(carry),
            "**Gates de H2**",
            "",
            gates,
            "## La prueba final: datos nunca vistos, una sola vez",
            "",
            "Cada estrategia que pasa sus condiciones en el desarrollo se prueba una sola vez con "
            "julio de 2024 a septiembre de 2026, sin ajustar nada. Se exige más de un 4 % anual "
            "neto de costes.",
            "",
            to_markdown(finals),
            "Las dos pasaron en el desarrollo y fallaron con datos nunca vistos, así que ninguna "
            "opera con dinero real. El paper trading del carry sigue como demostración del "
            "sistema completo.",
            "",
            "## ¿Es significativo? Validación estadística",
            "",
            to_markdown(tests),
            "## ¿Qué riesgo hay? Simulación",
            "",
            f"- Retorno medio simulado del carry H2: **{sim['media']}** "
            f"(mediana {sim['mediana']}).",
            f"- Años por debajo del 4 %: **{sim['p_bajo_4']}**; años con pérdida: "
            f"**{sim['p_perdida']}**.",
            f"- Con un 2 % anual de probabilidad de quiebra del exchange, el retorno medio cae a "
            f"**{sim['media_p2']}**. Por encima de **{sim['quiebra_equilibrio']}** anual conviene "
            "la stablecoin.",
            "",
            "## ¿Cómo va en vivo? Paper trading del carry H2",
            "",
            "Dinero simulado sobre precios reales de Binance, con kill-switch y alertas. Solo "
            "agregados: sin claves ni identificadores de cuenta.",
            "",
            _paper_section(data_dir / "paper"),
            "## Cuántas veces probamos",
            "",
            f"Ensayos registrados: **{ledger['total']}** (carry {ledger['carry']}, tendencia "
            f"{ledger['tendencia']}, modelo del funding {ledger['modelo']} y otras "
            f"{ledger['otras']}). Ninguna ejecución se descarta: cada una queda en el "
            "[registro de ensayos](estrategias/registro-de-ensayos.md). El Deflated Sharpe de cada "
            "estrategia descuenta los ensayos de su familia (el N del gate G1).",
            "",
            "En evaluación con el mismo protocolo: el momentum transversal en perpetuos y el sesgo "
            "favorito-longshot en Polymarket.",
            "",
        ]
    )
