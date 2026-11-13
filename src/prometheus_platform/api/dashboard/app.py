"""Dashboard de PrometheusQuant (PQ-34). Ejecutar con ``make dashboard``.

Solo lee artefactos del lakehouse (``PQ_DATA_DIR``); en Docker el volumen se monta en solo
lectura. Nunca muestra el holdout: las evaluaciones terminan antes de 2024-07-01.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import streamlit as st

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.dashboard.artifacts import (
    Artifacts,
    equity_curves,
    gates_table,
    load_artifacts,
    model_tables,
    performance_table,
    quality_table,
    scenario_table,
    transition_table,
    validation_table,
)
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import PaperView, build_view, read_heartbeat
from prometheus_platform.ops.settings import load_settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.research import explain, nowcast, what_if
from prometheus_platform.research.simulation import WeeklyRegimeModel

# Patrón F de storytelling: cada pestaña responde una pregunta del jurado, en orden.
LABELS = [
    "¿Qué pasó? Datos y calidad",
    "¿Funciona? Carry y gates",
    "¿Qué predice? Modelo",
    "¿Qué riesgo hay? Simulación",
    "¿Y si invierto? Simula tu inversión",
    "¿Qué predice hoy? Funding en vivo",
    "¿Cómo va en vivo? Paper trading",
]


def _missing(art: Artifacts, name: str) -> None:
    for m in art.missing:
        if m.artifact.startswith(name):
            st.info(f"Falta el artefacto **{m.artifact}**. Se genera con `{m.command}`.")


def _tab_data(art: Artifacts) -> None:
    st.subheader("Calidad de la capa silver")
    if not art.quality:
        _missing(art, "calidad")
        return
    table = quality_table(art.quality)
    st.dataframe(table, hide_index=True, width="stretch")
    with_gaps = table.filter(table["huecos"] > 0).height
    st.caption(
        f"{table.height} tablas; {with_gaps} con huecos. Silver informa los huecos y no los "
        "imputa (ver KE-007 en los errores conocidos)."
    )


def _tab_carry(art: Artifacts) -> None:
    st.subheader("Carry de funding: periodo de desarrollo")
    st.caption("El holdout (2024-07-01 → 2026-09-30) sigue cerrado hasta verificar comisiones.")
    for hyp in ("H1", "H2"):
        summary = art.carry.get(hyp)
        if summary is None:
            _missing(art, f"carry {hyp}")
            continue
        verdict = "pasa los 4 gates" if summary.get("passed") else "no pasa todos los gates"
        st.markdown(f"#### {hyp}: {', '.join(summary.get('symbols', []))}: **{verdict}**")
        left, mid, right = st.columns(3)
        left.metric("Configuración elegida (CPCV)", summary.get("selected", "?"))
        mid.metric("PBO", f"{summary.get('pbo', float('nan')):.1%}")
        right.metric("Deflated Sharpe", f"{summary.get('dsr', float('nan')):.3f}")
        st.dataframe(gates_table(summary), hide_index=True, width="stretch")
        st.dataframe(performance_table(summary), hide_index=True, width="stretch")
        returns = art.carry_returns.get(hyp)
        if returns is not None:
            curve = equity_curves(returns, str(summary.get("selected")))
            if curve.height:
                st.line_chart(curve, x="fecha", y=str(summary.get("selected")))


def _tab_model(art: Artifacts) -> None:
    st.subheader("Modelo predictivo del funding (cap. 5)")
    if art.model is None:
        _missing(art, "modelo")
        return
    if art.model_mode != "residual":
        st.warning("Se muestra la formulación `level` (v1); la oficial del cap. 5 es `residual`.")
    regression, classification = model_tables(art.model)
    st.markdown("**Regresión** (validación walk-forward)")
    st.dataframe(regression, hide_index=True, width="stretch")
    st.markdown("**Clasificación** (¿funding alto en la próxima liquidación?)")
    st.dataframe(classification, hide_index=True, width="stretch")
    dm = art.model.get("diebold_mariano", {})
    if dm:
        st.caption(
            f"Diebold-Mariano contra persistencia: DM = {dm.get('dm', 0):.2f}, "
            f"p = {dm.get('p_value', 1):.3f} (mejor: {dm.get('best_model', '?')})."
        )


def _tab_simulation(art: Artifacts) -> None:
    st.subheader("Simulación de Markov y Monte Carlo (cap. 6)")
    sim = art.simulation
    if sim is None:
        _missing(art, "simulación")
        return
    st.markdown("**Matriz de transición por bloques de 21 días**")
    st.dataframe(transition_table(sim), hide_index=True, width="stretch")
    st.markdown("**Validación contra la historia**: el simulador se acepta si reproduce los ciclos")
    st.dataframe(validation_table(sim), hide_index=True, width="stretch")
    st.markdown("**Retorno anual simulado por escenario de quiebra del exchange**")
    st.dataframe(scenario_table(sim), hide_index=True, width="stretch")
    break_even = sim.get("probabilidad_quiebra_equilibrio")
    if break_even is not None:
        st.metric("Probabilidad de quiebra anual de equilibrio", f"{break_even:.2%}")
        st.caption(
            "Por encima de esta probabilidad, el carry rinde menos que una stablecoin al 4 %."
        )


@st.cache_resource(show_spinner="Ajustando el modelo del cap. 6 con el periodo de desarrollo…")
def _what_if_model(data_dir: str) -> WeeklyRegimeModel:
    return what_if.fit_model(what_if.development_rate_sequences(Path(data_dir)))


def _tab_what_if(data_dir: Path) -> None:
    st.subheader("Simula tu inversión en el carry (H2)")
    st.caption(
        "Monte Carlo del capítulo 6, ajustado solo con el periodo de desarrollo. Cambia tu"
        " situación, no el modelo: θ solo admite los umbrales pre-registrados, y nada de esto"
        " cuenta como ensayo. No es asesoramiento financiero."
    )
    try:
        model = _what_if_model(str(data_dir))
    except (FileNotFoundError, OSError, ValueError, pl.exceptions.PolarsError):
        st.info(
            "Faltan los datos silver de H2 (SOL, BNB y XRP). Se generan con"
            " `uv run pq silver build --symbol SOLUSDT` (y BNBUSDT, XRPUSDT)."
        )
        return
    left, mid, right, last = st.columns(4)
    capital = left.number_input("Capital (USD)", 100, 1_000_000, 1_000, step=100)
    years = int(mid.radio("Horizonte (años)", what_if.HORIZONS_YEARS, horizontal=True))
    failure = right.slider("Quiebra del exchange (% anual)", 0.0, 10.0, 2.0, 0.5) / 100
    theta = last.selectbox(
        "Umbral θ (pre-registrado)",
        what_if.PRE_REGISTERED_THETAS,
        index=1,
        format_func=lambda v: f"{v:.0%}",
    )
    result = what_if.simulate(model, what_if.WhatIf(float(capital), years, failure, theta))
    a, b, c, d = st.columns(4)
    a.metric("Capital final mediano", f"{result.median:,.0f} USD")
    b.metric("Stablecoin al 4 %", f"{result.stablecoin_capital:,.0f} USD")
    c.metric("P(perder dinero)", f"{result.prob_loss:.1%}")
    d.metric("P(ganarle a la stablecoin)", f"{result.prob_beats_stablecoin:.1%}")
    counts, centers = what_if.histogram(result.final_capital)
    st.bar_chart(
        pl.DataFrame({"capital final (USD)": centers.round(0), "trayectorias": counts}),
        x="capital final (USD)",
        y="trayectorias",
    )
    st.caption(
        f"Entre el 5 % y el 95 % de los casos: {result.p5:,.0f} a {result.p95:,.0f} USD."
        f" En el peor 5 % se pierden, en promedio, {result.cvar95_loss:,.0f} USD."
        f" Probabilidad de quiebra en el horizonte: {result.horizon_failure_probability:.1%}"
        " (se pierde todo lo que está en el exchange)."
    )


@st.cache_resource(show_spinner="Entrenando el clasificador del cap. 5 con el desarrollo…")
def _nowcast_model(data_dir: str) -> nowcast.TrainedModel:
    params = nowcast.tuned_params(Path(data_dir))
    return nowcast.train(nowcast.development_panel(Path(data_dir)), params)


def _tab_nowcast(data_dir: Path) -> None:
    st.subheader("¿Habrá funding alto en la próxima liquidación?")
    st.caption(
        "Clasificador del capítulo 5 (bosque aleatorio con los hiperparámetros de GridSearch),"
        " entrenado solo con el periodo de desarrollo. Predice si la próxima liquidación anualizada"
        " superará el 20 %, el umbral de entrada de H2."
    )
    try:
        result = nowcast.forecast(_nowcast_model(str(data_dir)), nowcast.latest_rows(data_dir))
    except nowcast.StaleDataError as exc:
        st.info(
            f"Sin datos de hoy: {exc}. Tráelos con la API pública de Binance:"
            " `uv run pq ingest --source api funding --symbol SOLUSDT` (y klines spot/um, para"
            " cada símbolo) y luego `uv run pq silver build --symbol SOLUSDT`."
        )
        return
    except (FileNotFoundError, OSError, ValueError, KeyError, pl.exceptions.PolarsError):
        st.info(
            "Falta el modelo o los datos: `uv run pq research funding-model --figures <dir>` y"
            " silver de los cinco símbolos."
        )
        return
    table = pl.DataFrame(
        {
            "símbolo": [r.symbol for r in result.rows],
            "liquidación (UTC)": [r.funding_time.strftime("%Y-%m-%d %H:%M") for r in result.rows],
            "funding actual anualizado": [f"{r.annualized_now:.1%}" for r in result.rows],
            "P(funding alto)": [f"{r.probability_high:.1%}" for r in result.rows],
            "régimen previsto": [r.regime for r in result.rows],
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")
    st.markdown("**Por qué predice esto hoy**")
    for row in result.rows:
        st.markdown(
            "- "
            + explain.explain_in_words(
                row.symbol, row.probability_high, result.explanations[row.symbol]
            )
        )
    st.caption(
        "Para cada símbolo se prueba qué pasaría si una variable tuviera su valor habitual (la"
        " mediana del periodo de desarrollo) y todo lo demás quedara igual."
    )
    _nowcast_importance(data_dir)
    st.caption("Es una predicción estadística, no una recomendación de inversión.")


@st.cache_resource(show_spinner="Calculando la importancia en validación (walk-forward)…")
def _validation_importance(data_dir: str) -> list[explain.FeatureImportance]:
    params = nowcast.tuned_params(Path(data_dir))
    return explain.validation_importance(nowcast.development_panel(Path(data_dir)), params)


def _nowcast_importance(data_dir: Path) -> None:
    st.markdown("**Qué variables importan de verdad al modelo** (fuera de muestra)")
    try:
        ranked = _validation_importance(str(data_dir))
    except (ValueError, OSError, KeyError, pl.exceptions.PolarsError):
        st.info("No se pudo calcular la importancia en validación con los datos disponibles.")
        return
    top = ranked[:5]
    st.bar_chart(
        # El número delante conserva el orden por importancia (el gráfico ordena por nombre).
        pl.DataFrame(
            {
                "variable": [f"{i}. {imp.label}" for i, imp in enumerate(top, start=1)],
                "caída del AUC": [imp.mean for imp in top],
            }
        ),
        x="variable",
        y="caída del AUC",
    )
    st.caption(
        "Importancia por permutación en los pliegues de validación del walk-forward, nunca en el"
        " entrenamiento: cuánto empeora el acierto fuera de muestra (AUC) si se baraja la variable."
    )


def _expected_cagr(art: Artifacts) -> float | None:
    """CAGR de la configuración elegida de H2 en el periodo de desarrollo (no es una predicción)."""
    cagr = art.carry.get("H2", {}).get("selected_performance", {}).get("cagr")
    return float(cagr) if isinstance(cagr, int | float) else None


def _live_status(paths: PaperPaths, max_age_minutes: int) -> None:
    beat = read_heartbeat(paths.heartbeat)
    if beat is None:
        st.warning("Sin heartbeat: el runner no se ha ejecutado aún en esta carpeta.")
    else:
        age = (SystemClock().now() - beat["at"]).total_seconds() / 60
        text = f"Último ciclo hace {age:.0f} min ({beat['at']:%Y-%m-%d %H:%M} UTC)."
        if age > max_age_minutes:
            st.error(f"Runner caído o detenido. {text}")
        elif not beat.get("ok", False):
            st.warning(f"Último ciclo con fallos: {beat.get('detail', '')}. {text}")
        else:
            st.success(f"Runner en marcha. {text}")
    switch = KillSwitch(paths.kill_switch, SystemClock(), JsonlEventJournal(paths.journal))
    state = switch.state()
    if state is None:
        st.success("Kill-switch armado: la operación está permitida.")
    else:
        st.error(
            f"Kill-switch ACTIVADO: {state.get('reason', '')} (vía {state.get('source', '')})."
        )


def _live_curve(view: PaperView, cagr: float | None) -> None:
    start = view.valuations[0]
    curve = pl.DataFrame(
        {
            "hora (UTC)": [v.occurred_at for v in view.valuations],
            "paper trading": [float(v.equity) for v in view.valuations],
        }
    )
    if cagr is not None:
        days = [
            (v.occurred_at - start.occurred_at).total_seconds() / 86_400 for v in view.valuations
        ]
        curve = curve.with_columns(
            pl.Series(
                "esperado según el backtest",
                [float(start.equity) * (1 + cagr) ** (d / 365.25) for d in days],
            )
        )
    st.line_chart(curve, x="hora (UTC)")
    if cagr is not None:
        st.caption(
            f"«Esperado» es el CAGR de la configuración elegida en el periodo de desarrollo "
            f"({cagr:.2%} anual) aplicado al capital inicial. No es una predicción."
        )


def _live_tables(view: PaperView) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("**Posiciones por pata**")
        if view.positions:
            st.dataframe(
                pl.DataFrame(
                    {
                        "instrumento": [i.symbol for i in view.positions],
                        "pata": [
                            "perpetuo" if i.symbol.endswith("-PERP") else "spot"
                            for i in view.positions
                        ],
                        "cantidad": [str(q) for q in view.positions.values()],
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("Sin posiciones abiertas.")
    with right:
        st.markdown("**Últimas órdenes ejecutadas**")
        recent = view.fills[-10:][::-1]
        if recent:
            st.dataframe(
                pl.DataFrame(
                    {
                        "hora (UTC)": [f.at.strftime("%Y-%m-%d %H:%M") for f in recent],
                        "tipo": [f.label for f in recent],
                        "instrumento": [f.instrument.symbol for f in recent],
                        "lado": [f.side.value for f in recent],
                        "precio": [f"{f.price:.4f}" for f in recent],
                        "comisión": [f"{f.fee:.4f}" for f in recent],
                        "slippage": [f"{f.slippage:.4f}" for f in recent],
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("Aún no hay órdenes.")
    st.markdown("**Últimas liquidaciones y decisiones**")
    decisions = view.settlements[-12:][::-1]
    st.dataframe(
        pl.DataFrame(
            {
                "liquidación (UTC)": [d.funding_time.strftime("%Y-%m-%d %H:%M") for d in decisions],
                "símbolo": [d.symbol for d in decisions],
                "tasa": [f"{d.rate:.6f}" for d in decisions],
                "S_k anualizada": [f"{float(d.s_k):.1%}" if d.s_k else "n/d" for d in decisions],
                "decisión": [d.action for d in decisions],
                "estado deseado": ["dentro" if d.target_open else "fuera" for d in decisions],
                "funding (USD)": [f"{d.amount:.4f}" for d in decisions],
            }
        ),
        hide_index=True,
        width="stretch",
    )


def _tab_live(data_dir: Path, art: Artifacts, max_age_minutes: int) -> None:
    st.subheader("Paper trading del carry H2 en vivo")
    paths = PaperPaths(data_dir / "paper")
    view = build_view(JsonlEventJournal(paths.journal).replay())
    if not view.valuations:
        st.info(
            "Aún no hay paper trading en esta carpeta. Se arranca con `uv run pq paper run` "
            "(runbook de paper trading)."
        )
        _live_status(paths, max_age_minutes)
        return
    if view.broker == "simulado":
        st.caption(
            "Bróker **simulado** sobre precios y funding reales de Binance: no es Binance Demo "
            "ni dinero real."
        )
    equity, initial = view.equity or 0, view.initial_equity or 0
    cols = st.columns(5)
    cols[0].metric("Equity", f"{equity:,.2f} USD")
    cols[1].metric("PnL acumulado", f"{equity - initial:+,.2f} USD")
    cols[2].metric("Funding neto", f"{view.funding:+,.4f} USD")
    cols[3].metric(
        "Comisiones y slippage",
        f"{view.costs:,.4f} USD",
        help=f"Comisiones {view.fees:,.4f} USD + slippage {view.slippage:,.4f} USD",
    )
    cols[4].metric("Drawdown", f"{view.drawdown:.2%}")
    _live_status(paths, max_age_minutes)
    _live_curve(view, _expected_cagr(art))
    _live_tables(view)
    st.caption("Recarga la página para ver el último ciclo.")


def main() -> None:
    st.set_page_config(page_title="PrometheusQuant", layout="wide")
    st.title("PrometheusQuant: tablero de investigación")
    settings = load_settings()
    data_dir = settings.data_dir
    art = load_artifacts(data_dir)
    st.caption(f"Artefactos leídos de `{data_dir}` (solo lectura).")
    tabs = st.tabs(LABELS)
    for tab, render in zip(
        tabs[:4], (_tab_data, _tab_carry, _tab_model, _tab_simulation), strict=True
    ):
        with tab:
            render(art)
    with tabs[4]:
        _tab_what_if(data_dir)
    with tabs[5]:
        _tab_nowcast(data_dir)
    with tabs[6]:
        _tab_live(data_dir, art, settings.paper_heartbeat_max_age_minutes)


main()
