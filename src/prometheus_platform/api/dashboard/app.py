"""Dashboard de PrometheusQuant (PQ-34). Ejecutar con ``make dashboard``.

Solo lee artefactos del lakehouse (``PQ_DATA_DIR``); en Docker el volumen se monta en solo
lectura. Nunca muestra el holdout: las evaluaciones terminan antes de 2024-07-01.

Con ``?modo=feria`` (PQ-102): tipografía grande, la página en vivo se actualiza sola y la barra
lateral guía el recorrido de 7 pasos del pitch (``tour.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import altair as alt
import polars as pl
import streamlit as st
from streamlit.navigation.page import StreamlitPage

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.dashboard import costs, portfolio, style, tour
from prometheus_platform.api.dashboard import summary as resumen
from prometheus_platform.api.dashboard.artifacts import (
    Artifacts,
    equity_curves,
    gates_table,
    load_artifacts,
    model_tables,
    performance_table,
    quality_table,
    scenario_table,
    strategy_overview,
    transition_table,
    validation_table,
)
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import (
    PaperView,
    build_view,
    read_heartbeat,
    strategy_breakdown,
)
from prometheus_platform.ops.settings import load_settings
from prometheus_platform.portfolio_risk.budget import BLOCK_DAYS
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch
from prometheus_platform.research import explain, nowcast, what_if
from prometheus_platform.research.simulation import WeeklyRegimeModel

FAIR_KEY = "modo_feria"


def _missing(art: Artifacts, name: str) -> None:
    for m in art.missing:
        if m.artifact.startswith(name):
            st.info(f"Todavía no está el dato «{m.artifact}».")
            st.caption(f"Para el equipo: se genera con `{m.command}`.")


def _tab_data(art: Artifacts) -> None:
    st.subheader("Calidad de la capa silver")
    if not art.quality:
        _missing(art, "calidad")
        return
    table = quality_table(art.quality)
    st.dataframe(table, hide_index=True, width="stretch", alt="Calidad de cada tabla silver")
    with_gaps = table.filter(table["huecos"] > 0).height
    st.caption(
        f"{table.height} tablas; {with_gaps} con huecos. Silver informa los huecos y no los "
        "imputa (ver KE-007 en los errores conocidos)."
    )


# Insignias de estado: icono propio de Streamlit (funciona sin internet) + texto + color.
# Descartar una estrategia es el protocolo funcionando, no una alerta: va en gris (hallazgo 4).
BadgeColor = Literal["green", "orange", "gray"]
BADGES: dict[str, tuple[str, BadgeColor]] = {
    "ok": (":material/check_circle:", "green"),
    "warn": (":material/schedule:", "orange"),
    "bad": (":material/block:", "gray"),
}


def _figure(column: Any, label: str, value: str, context: str) -> None:
    """Una cifra en tamaño normal, con su comparación debajo."""
    column.caption(label)
    column.markdown(f"**{value}**")
    column.caption(context)


def _bar_chart(  # noqa: PLR0913 - keyword-only salvo los datos y los ejes
    frame: pl.DataFrame,
    x: str,
    y: str,
    *,
    alt_text: str,
    horizontal: bool = False,
    fmt: str = ",.0f",
) -> None:
    """Barras finas en el color de marca, con tooltip; horizontales para etiquetas largas."""
    axis = alt.Axis(tickCount=5)  # pocas marcas: con muchas se pisan (PQ-125, hallazgo 13)
    value = (
        alt.X(f"{y}:Q", title=y, axis=axis) if horizontal else alt.Y(f"{y}:Q", title=y, axis=axis)
    )
    category = (
        alt.Y(f"{x}:N", title=None, sort=None, axis=alt.Axis(labelLimit=320))
        if horizontal
        else alt.X(f"{x}:O", title=x, sort=None)
    )
    chart = (
        alt.Chart(frame)
        .mark_bar(color=style.BRAND, cornerRadiusEnd=4)
        .encode(
            x=value if horizontal else category,
            y=category if horizontal else value,
            tooltip=[alt.Tooltip(f"{x}:N"), alt.Tooltip(f"{y}:Q", format=fmt)],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch", theme=None, alt=alt_text)


def _growth_chart(curve: pl.DataFrame, name: str) -> None:
    """Crecimiento de 1 USD: línea de la marca, ejes discretos, fechas en español."""
    chart = (
        alt.Chart(curve)
        .mark_line()
        .encode(
            x=alt.X("fecha:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y(f"{name}:Q", scale=alt.Scale(zero=False), title="Valor de 1 USD invertido"),
            color=alt.value(style.BRAND),
            tooltip=[
                alt.Tooltip("fecha:T", format="%d %b %Y"),
                alt.Tooltip(f"{name}:Q", format=".3f"),
            ],
        )
        .properties(height=260)
    )
    first, last = curve[name][0], curve[name][-1]
    text = (
        f"Valor de 1 USD invertido: de {style.number(first)} a {style.number(last)} USD "
        f"entre {curve['fecha'][0]} y {curve['fecha'][-1]}"
    )
    st.altair_chart(chart, width="stretch", theme=None, alt=text)


def _tab_home(data_dir: Path, art: Artifacts, max_age_minutes: int) -> None:
    """Portada (patrón Dashboard): ¿cómo va todo?, en diez segundos y sin jerga."""
    st.subheader("¿Cómo va?")
    st.markdown(
        "PrometheusQuant prueba estrategias de inversión en cripto con **reglas fijadas antes de "
        "ver los resultados**, y solo las lleva a operar si superan una prueba final con datos que "
        "nunca vio. Aquí está el estado de cada una.",
        width=760,  # unos 75 caracteres por línea (PQ-125, hallazgo 16)
    )
    paths = PaperPaths(data_dir / "paper")
    view = build_view(JsonlEventJournal(paths.journal).replay())
    beat = read_heartbeat(paths.heartbeat)
    now = SystemClock().now()
    theta = resumen.entry_threshold(art.carry.get("H2", {}).get("selected"))
    headline = resumen.paper_headline(view, theta, now)
    live = st.container(border=True)
    live.markdown("##### Paper trading (dinero simulado, precios reales)")
    if headline is None:
        live.info("Aún no hay paper trading.")
        live.caption("Para el equipo: se arranca con `uv run pq paper run`.")
    else:
        live.markdown(headline.sentence, width=760)
        if art.carry_holdout is not None and not art.carry_holdout.get("pasa"):
            live.caption("Es una demostración del sistema: el carry no superó la prueba final.")
        age = None if beat is None else (now - beat["at"]).total_seconds() / 60
        running = age is not None and age <= max_age_minutes and bool(beat and beat.get("ok"))
        cols = live.columns(4)
        cols[0].caption("Estado del runner")
        if running:
            cols[0].badge("En marcha", icon=":material/check_circle:", color="green")
        else:
            cols[0].badge("Detenido", icon=":material/cancel:", color="red")
        # Cifras en tamaño normal y con su comparación (hallazgo 4, Few).
        _figure(cols[1], "Capital", headline.capital, headline.change)
        _figure(cols[2], "En marcha", f"{headline.days} días", "desde el primer ciclo")
        _figure(cols[3], "Peor caída", headline.drawdown, "desde el máximo")
    st.markdown("##### Estrategias")
    overview = strategy_overview(art)
    research = data_dir / "research"
    pending = [p for p in resumen.IN_PROGRESS if not (research / p.artifact).exists()]
    if not overview and not pending:
        st.info("Aún no hay evaluaciones.")
        st.caption("Para el equipo: se generan con `uv run pq research carry` y `trend`.")
    cards = st.columns(max(len(overview) + len(pending), 1))
    for column, item in zip(cards, overview, strict=False):
        card = column.container(border=True)
        card.markdown(f"**{item.name}**")
        icon, color = BADGES[item.level]
        card.badge(item.stage, icon=icon, color=color)
        card.caption(item.summary)
    for column, todo in zip(cards[len(overview) :], pending, strict=False):
        card = column.container(border=True)
        card.markdown(f"**{todo.name}**")
        card.badge(todo.stage, icon=":material/pending:", color="blue")
        card.caption(todo.summary)
    with st.expander("¿Qué significa cada término?"):
        for term, meaning in style.GLOSSARY.items():
            st.markdown(f"**{term}.** {meaning}")


def _tab_carry(art: Artifacts) -> None:
    st.subheader("Carry de funding")
    st.caption(
        "Desarrollo: 2020 al 2024-06-30. Prueba final con datos nunca vistos: 2024-07-01 al "
        "2026-09-30, abierta una sola vez (PQ-50)."
    )
    # H2 primero: es la que llegó a la prueba final. H1 se descartó antes, en desarrollo.
    _carry_hypothesis(art, "H2", final=art.carry_holdout)
    with st.expander("H1 · descartada en desarrollo", icon=":material/history:"):
        _carry_hypothesis(art, "H1", final=None)


def _carry_hypothesis(art: Artifacts, hyp: str, *, final: dict[str, Any] | None) -> None:
    summary = art.carry.get(hyp)
    if summary is None:
        _missing(art, f"carry {hyp}")
        return
    symbols = ", ".join(summary.get("symbols", []))
    verdict = f"desarrollo: {style.status_icon(bool(summary.get('passed')))}"
    if final is not None:
        cagr = final.get("rendimiento", {}).get("cagr")
        verdict += (
            f" · prueba final: {style.status_icon(bool(final.get('pasa')))}"
            f" ({style.pct(cagr, 2)} anual)"
        )
    st.markdown(f"#### {hyp} · {symbols}")
    st.markdown(verdict)
    left, mid, right = st.columns(3)
    left.metric("Configuración elegida", summary.get("selected", "?"))
    mid.metric("PBO", style.pct(summary.get("pbo")), help=style.GLOSSARY["PBO"])
    right.metric(
        "Deflated Sharpe",
        style.number(summary.get("dsr"), 2),
        help=style.GLOSSARY["Deflated Sharpe"],
    )
    st.dataframe(
        gates_table(summary),
        hide_index=True,
        width="stretch",
        alt=f"Condiciones mínimas de {hyp} en desarrollo y si las cumple",
    )
    st.dataframe(
        performance_table(summary),
        hide_index=True,
        width="stretch",
        alt=f"Rendimiento de {hyp} frente a estar siempre invertido",
    )
    returns = art.carry_returns.get(hyp)
    if returns is not None:
        curve = equity_curves(returns, str(summary.get("selected")))
        if curve.height:
            _growth_chart(curve, str(summary.get("selected")))


def _tab_model(art: Artifacts) -> None:
    st.subheader("Modelo predictivo del funding (cap. 5)")
    if art.model is None:
        _missing(art, "modelo")
        return
    if art.model_mode != "residual":
        st.warning("Se muestra la formulación `level` (v1); la oficial del cap. 5 es `residual`.")
    regression, classification = model_tables(art.model)
    st.markdown("**Regresión** (validación walk-forward)")
    st.dataframe(regression, hide_index=True, width="stretch", alt="Error de cada modelo")
    st.markdown("**Clasificación** (¿funding alto en la próxima liquidación?)")
    st.dataframe(
        classification, hide_index=True, width="stretch", alt="Acierto de cada clasificador"
    )
    dm = art.model.get("diebold_mariano", {})
    if dm:
        st.caption(
            f"Diebold-Mariano contra persistencia: DM = {style.number(dm.get('dm', 0))}, "
            f"p = {style.number(dm.get('p_value', 1), 3)} (mejor: {dm.get('best_model', '?')})."
        )


def _tab_simulation(art: Artifacts) -> None:
    st.subheader("Simulación de Markov y Monte Carlo (cap. 6)")
    sim = art.simulation
    if sim is None:
        _missing(art, "simulación")
        return
    st.markdown("**Matriz de transición por bloques de 21 días**")
    st.dataframe(
        transition_table(sim),
        hide_index=True,
        width="stretch",
        alt="Probabilidad de pasar de un régimen de funding a otro",
    )
    st.markdown("**Validación contra la historia**: el simulador se acepta si reproduce los ciclos")
    st.dataframe(
        validation_table(sim),
        hide_index=True,
        width="stretch",
        alt="Simuladores frente a la historia real",
    )
    st.markdown("**Retorno anual simulado por escenario de quiebra del exchange**")
    st.dataframe(
        scenario_table(sim),
        hide_index=True,
        width="stretch",
        alt="Retorno anual simulado según la probabilidad de quiebra del exchange",
    )
    break_even = sim.get("probabilidad_quiebra_equilibrio")
    if break_even is not None:
        st.metric("Probabilidad de quiebra anual de equilibrio", style.pct(break_even, 2))
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
        st.info("Todavía no están los datos de H2 (SOL, BNB y XRP).")
        st.caption(
            "Para el equipo: `uv run pq silver build --symbol SOLUSDT` (y BNBUSDT, XRPUSDT)."
        )
        return
    _what_if_controls(model)


@st.fragment  # sus controles solo recalculan el simulador, no la página entera (hallazgo 3)
def _what_if_controls(model: WeeklyRegimeModel) -> None:
    left, mid, right, last = st.columns(4)
    capital = left.number_input("Capital (USD)", 100, 1_000_000, 1_000, step=100)
    years = int(
        mid.segmented_control(
            "Horizonte",
            what_if.HORIZONS_YEARS,
            default=what_if.HORIZONS_YEARS[0],
            required=True,
            format_func=lambda y: f"{y} año" if y == 1 else f"{y} años",
        )
        or what_if.HORIZONS_YEARS[0]
    )
    failure = (
        right.select_slider(  # el slider usa printf: mostraría «2.0 %» con punto
            "Quiebra del exchange (% anual)",
            options=[x / 2 for x in range(21)],
            value=2.0,
            format_func=lambda v: f"{style.number(v, 1)} %",
        )
        / 100
    )
    theta = last.selectbox(
        "Umbral θ (pre-registrado)",
        what_if.PRE_REGISTERED_THETAS,
        index=1,
        format_func=lambda v: style.pct(v, 0),
    )
    result = what_if.simulate(model, what_if.WhatIf(float(capital), years, failure, theta))
    a, b, c, d = st.columns(4)
    a.metric("Capital final mediano", style.usd(result.median, 0))
    b.metric("Stablecoin al 4 %", style.usd(result.stablecoin_capital, 0))
    c.metric("Probabilidad de perder dinero", style.pct(result.prob_loss))
    d.metric("Probabilidad de ganarle a la stablecoin", style.pct(result.prob_beats_stablecoin))
    st.markdown(
        "**Capital final si el exchange no quiebra.** Con la quiebra se pierde todo lo que está"
        f" en el exchange. Pasa en el {style.pct(result.horizon_failure_probability)} de los"
        " casos y va aparte para no aplastar el gráfico."
    )
    _what_if_histogram(result, float(capital))
    st.caption(
        f"Entre el 5 % y el 95 % de los casos, quiebra incluida: {style.usd(result.p5, 0)} a"
        f" {style.usd(result.p95, 0)}. En el peor 5 % se pierden, en promedio,"
        f" {style.usd(result.cvar95_loss, 0)}."
    )


def _what_if_histogram(result: what_if.WhatIfResult, capital: float) -> None:
    frame = resumen.histogram_frame(result.final_capital)
    if frame.is_empty():
        st.info("En todas las trayectorias quiebra el exchange.")
        return
    x_title = "capital final (USD)"
    bars = (
        alt.Chart(frame)
        .mark_bar(color=style.BRAND, opacity=0.85)
        .encode(
            x=alt.X(
                "desde:Q",
                title=x_title,
                scale=alt.Scale(zero=False),  # el rango que importa, no desde 0
                axis=alt.Axis(format=",.0f", tickCount=6),
            ),
            x2="hasta:Q",
            y=alt.Y("trayectorias:Q", title="trayectorias", axis=alt.Axis(tickCount=5)),
            y2=alt.datum(0),  # barras desde el eje, no tiras sueltas
            tooltip=[
                alt.Tooltip("desde:Q", title="desde (USD)", format=",.0f"),
                alt.Tooltip("hasta:Q", title="hasta (USD)", format=",.0f"),
                alt.Tooltip("trayectorias:Q", format=",.0f"),
            ],
        )
    )
    refs = pl.DataFrame(
        {
            "valor": [capital, result.stablecoin_capital],
            "referencia": ["capital inicial", "stablecoin al 4 %"],
        }
    )
    rules = (
        alt.Chart(refs)
        .mark_rule(color=style.NEUTRAL, strokeDash=[4, 3], strokeWidth=2)
        .encode(x="valor:Q", tooltip=["referencia:N", alt.Tooltip("valor:Q", format=",.0f")])
    )
    # Las dos referencias suelen estar juntas: una etiqueta a cada lado de su línea.
    left = (
        alt.Chart(refs.head(1))
        .mark_text(align="right", dx=-4, dy=-8, color=style.TEXT_SECONDARY, font=style.FONT)
        .encode(x="valor:Q", y=alt.value(0), text="referencia:N")
    )
    right = (
        alt.Chart(refs.tail(1))
        .mark_text(align="left", dx=4, dy=-8, color=style.TEXT_SECONDARY, font=style.FONT)
        .encode(x="valor:Q", y=alt.value(0), text="referencia:N")
    )
    st.altair_chart(
        alt.layer(bars, rules, left, right).properties(height=260),
        width="stretch",
        theme=None,
        alt=(
            f"Capital final simulado: mediana de {style.usd(result.median, 0)}, frente a"
            f" {style.usd(capital, 0)} iniciales y {style.usd(result.stablecoin_capital, 0)} con"
            " la stablecoin"
        ),
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
        st.info(f"Sin datos de hoy: {exc}.")
        st.caption(
            "Para el equipo: `uv run pq ingest --source api funding --symbol SOLUSDT` (y klines"
            " spot/um, para cada símbolo) y luego `uv run pq silver build --symbol SOLUSDT`."
        )
        return
    except (FileNotFoundError, OSError, ValueError, KeyError, pl.exceptions.PolarsError):
        st.info("Todavía no está el modelo de predicción o faltan sus datos.")
        st.caption(
            "Para el equipo: `uv run pq research funding-model --figures <dir>` y silver de los"
            " cinco símbolos."
        )
        return
    table = pl.DataFrame(
        {
            "símbolo": [r.symbol for r in result.rows],
            "liquidación (UTC)": [r.funding_time.strftime("%Y-%m-%d %H:%M") for r in result.rows],
            "funding actual anualizado": [style.pct(r.annualized_now) for r in result.rows],
            "probabilidad de funding alto": [style.pct(r.probability_high) for r in result.rows],
            "régimen previsto": [r.regime for r in result.rows],
        }
    )
    fresh = resumen.freshness(max(r.funding_time for r in result.rows), SystemClock().now())
    if fresh.stale:  # más de dos liquidaciones sin dato nuevo (hallazgo 2)
        st.warning(
            f"El último dato es de {fresh.text}: esta es la última predicción disponible, no la "
            "de hoy.",
            icon=":material/history:",
        )
        st.caption("Para el equipo: se actualiza con `uv run pq ingest --source api funding`.")
    else:
        st.badge(f"Dato de {fresh.text}", icon=":material/schedule:", color="green")
    st.markdown(resumen.nowcast_summary(result.rows))
    st.dataframe(
        table, hide_index=True, width="stretch", alt="Probabilidad de funding alto por moneda"
    )
    why = st.expander("Por qué predice esto para cada moneda", icon=":material/help:")
    for row in result.rows:
        why.markdown(
            "- "
            + explain.explain_in_words(
                row.symbol, row.probability_high, result.explanations[row.symbol]
            )
        )
    why.caption(
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
    _bar_chart(
        pl.DataFrame(
            {
                "variable": [f"{i}. {imp.label}" for i, imp in enumerate(top, start=1)],
                "caída del AUC": [imp.mean for imp in top],
            }
        ),
        "variable",
        "caída del AUC",
        alt_text=f"La variable que más importa al modelo es {top[0].label}" if top else "",
        horizontal=True,
        fmt=".3f",
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
        else:  # estado normal: insignia discreta; los recuadros quedan para los fallos
            st.badge("Runner en marcha", icon=":material/check_circle:", color="green")
            st.caption(text)
    switch = KillSwitch(paths.kill_switch, SystemClock(), JsonlEventJournal(paths.journal))
    state = switch.state()
    if state is None:
        st.badge("Kill-switch armado: se puede operar", icon=":material/shield:", color="green")
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
    long = curve.unpivot(index="hora (UTC)", variable_name="serie", value_name="capital (USD)")
    chart = (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X(
                "hora (UTC):T",
                title=None,
                axis=alt.Axis(format="%d %b", tickCount="day"),  # una marca por día
            ),
            y=alt.Y("capital (USD):Q", scale=alt.Scale(zero=False), title="Capital (USD)"),
            color=alt.Color(
                "serie:N",
                sort=["paper trading", "esperado según el backtest"],
                scale=alt.Scale(range=[style.BRAND, style.NEUTRAL]),
            ),
            strokeDash=alt.StrokeDash(
                "serie:N",
                sort=["paper trading", "esperado según el backtest"],
                scale=alt.Scale(range=[[1, 0], [5, 4]]),
            ),
            tooltip=[
                alt.Tooltip("hora (UTC):T", format="%d %b %Y %H:%M"),
                "serie:N",
                alt.Tooltip("capital (USD):Q", format=",.2f"),
            ],
        )
        .properties(height=280)
    )
    last = float(view.valuations[-1].equity)
    st.altair_chart(
        chart,
        width="stretch",
        theme=None,
        alt=f"Capital del paper: de {style.usd(float(start.equity))} a {style.usd(last)}",
    )
    if cagr is not None:
        st.caption(
            f"«Esperado» es el CAGR de la configuración elegida en el periodo de desarrollo "
            f"({style.pct(cagr, 2)} anual) aplicado al capital inicial. No es una predicción."
        )


def _live_tables(view: PaperView, theta: float) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("**Posiciones abiertas**")
        if view.positions:
            st.dataframe(
                pl.DataFrame(
                    {
                        "instrumento": [i.symbol for i in view.positions],
                        "mercado": [
                            "perpetuo" if i.symbol.endswith("-PERP") else "al contado"
                            for i in view.positions
                        ],
                        "cantidad": [style.number(float(q), 6) for q in view.positions.values()],
                    }
                ),
                hide_index=True,
                width="stretch",
                alt="Posiciones abiertas del paper",
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
                        "precio": [style.number(float(f.price), 4) for f in recent],
                        "comisión": [style.usd(float(f.fee), 4) for f in recent],
                        "slippage": [style.usd(float(f.slippage), 4) for f in recent],
                    }
                ),
                hide_index=True,
                width="stretch",
                alt="Últimas órdenes ejecutadas por el paper",
            )
        else:
            st.caption("Aún no hay órdenes.")
    st.markdown("**Liquidaciones y decisiones**")
    st.markdown(resumen.settlements_summary(view.settlements, theta))
    decisions = view.settlements[-12:][::-1]
    st.expander("Ver las últimas 12 liquidaciones", icon=":material/table:").dataframe(
        pl.DataFrame(
            {
                "liquidación (UTC)": [d.funding_time.strftime("%Y-%m-%d %H:%M") for d in decisions],
                "símbolo": [d.symbol for d in decisions],
                "tasa": [style.number(float(d.rate), 6) for d in decisions],
                "señal anualizada": [
                    style.pct(float(d.s_k)) if d.s_k else "n/d" for d in decisions
                ],
                "decisión": [d.action for d in decisions],
                "estado deseado": ["dentro" if d.target_open else "fuera" for d in decisions],
                "funding cobrado": [style.usd(float(d.amount), 4) for d in decisions],
            }
        ),
        hide_index=True,
        width="stretch",
        alt="Últimas liquidaciones de funding y la decisión del carry en cada una",
    )


def _tab_live(
    data_dir: Path, art: Artifacts, max_age_minutes: int, *, auto_refresh: bool = False
) -> None:
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
    if art.carry_holdout is not None and not art.carry_holdout.get("pasa"):
        st.warning(
            "**Demostración del sistema, no una estrategia aprobada.** El carry H2 no superó la "
            "prueba final con datos nunca vistos (PQ-50). El paper trading sigue para mostrar el "
            "circuito completo: datos, señal, riesgo, ejecución y monitoreo.",
            icon=":material/info:",
        )
    if view.broker == "simulado":
        st.caption(
            "Bróker **simulado** sobre precios y funding reales de Binance: no es Binance Demo "
            "ni dinero real."
        )
    equity, initial = view.equity or 0, view.initial_equity or 0
    cols = st.columns(5)
    cols[0].metric("Capital", style.usd(float(equity)))
    cols[1].metric("Ganancia acumulada", style.usd(float(equity - initial), signed=True))
    cols[2].metric("Funding cobrado", style.usd(float(view.funding), signed=True))
    cols[3].metric(
        "Comisiones y slippage",
        style.usd(float(view.costs)),
        help=f"Comisiones {style.usd(float(view.fees), 4)} + slippage "
        f"{style.usd(float(view.slippage), 4)}",
    )
    cols[4].metric("Peor caída", style.pct(float(view.drawdown), 2))
    _live_status(paths, max_age_minutes)
    _live_curve(view, _expected_cagr(art))
    _live_tables(view, resumen.entry_threshold(art.carry.get("H2", {}).get("selected")))
    _live_costs(art)
    if auto_refresh:
        st.caption(f"Se actualiza sola cada {tour.LIVE_REFRESH.seconds} s.")
    else:
        st.caption("Recarga la página para ver el último ciclo.")


def _live_costs(art: Artifacts) -> None:
    """Slippage y comisiones de fills reales frente a lo que suponen los backtests (PQ-95)."""
    st.markdown("**Costes reales frente a los supuestos**")
    if not art.costs:
        st.caption("Todavía no hay costes medidos.")
        st.caption("Para el equipo: `uv run pq paper costes` (y `pq paper muestreo-costes`).")
        return
    st.markdown(costs.headline(art.costs))
    st.dataframe(
        costs.legs_table(art.costs),
        hide_index=True,
        width="stretch",
        alt="Slippage y comisión medidos frente a los supuestos, por fuente y pata",
    )
    frame = costs.orders_frame(art.costs)
    if frame.is_empty():
        return
    y = alt.Y("serie:N", title=None, axis=alt.Axis(labelLimit=320))
    points = (
        alt.Chart(frame)
        .mark_circle(size=60, opacity=0.6, color=style.BRAND)
        .encode(
            x=alt.X("slippage (pb):Q", title="slippage por orden (pb; positivo es coste)"),
            y=y,
            tooltip=[
                "símbolo:N",
                alt.Tooltip("slippage (pb):Q", format=",.2f"),
                alt.Tooltip("supuesto (pb):Q", format=",.0f"),
            ],
        )
    )
    assumed = (
        alt.Chart(frame)
        .mark_tick(color=style.NEUTRAL, thickness=3, size=26)
        .encode(x="max(supuesto (pb)):Q", y=y, tooltip=["max(supuesto (pb)):Q"])
    )
    st.altair_chart(
        alt.layer(points, assumed).properties(height=max(90, 46 * frame["serie"].n_unique())),
        width="stretch",
        theme=None,
        alt=costs.headline(art.costs),
    )
    st.caption(
        "Cada punto es una orden. La marca gris es el slippage que suponen los backtests (2 pb en "
        "BTC y ETH, 5 pb en las altcoins). Lo medido solo cambia los backtests siguientes."
    )


def _tab_portfolio(data_dir: Path, art: Artifacts) -> None:
    st.subheader("Cartera multiestrategia: capital, PnL y riesgo")
    view = build_view(JsonlEventJournal(PaperPaths(data_dir / "paper").journal).replay())
    equity = view.equity or Decimal(0)
    rows = strategy_breakdown(view)
    current = portfolio.paper_weights(rows, equity)

    st.markdown("**Presupuesto recomendado frente al paper**")
    if art.budget is None:
        _missing(art, "presupuesto")
    else:
        st.dataframe(
            portfolio.allocation_table(art.budget, current),
            hide_index=True,
            width="stretch",
            alt="Presupuesto recomendado frente al reparto actual del paper",
        )
        caps = art.budget.get("tope_por_exchange", {})
        cols = st.columns(3)
        cols[0].metric(
            "Tope por exchange",
            ", ".join(f"{k}: {style.pct(float(v))}" for k, v in caps.items()),
        )
        cols[1].metric(
            "CVaR95 recomendado",
            style.pct(float(art.budget.get("cvar95", 0)), 2),
            help="Pérdida media en el peor 5 % de los años simulados. Negativo: aun en esos años"
            " se gana.",
        )
        cols[2].metric(
            "Retorno esperado", style.pct(float(art.budget.get("retorno_esperado", 0)), 2)
        )
        st.caption(
            "El presupuesto (pq research budget) maximiza el retorno esperado con un CVaR95 ≤ 5 %"
            " y una quiebra del exchange del 2 % anual. El paper es una demostración y no lo aplica"
            " solo (decisión del titular, 21-nov-2026)."
        )
    st.markdown("**Capital y PnL por estrategia y exchange (paper)**")
    if not rows:
        st.info("Aún no hay operaciones en el paper trading: `uv run pq paper run`.")
    else:
        st.dataframe(
            portfolio.strategy_table(rows, equity),
            hide_index=True,
            width="stretch",
            alt="Capital y ganancia del paper por estrategia y exchange",
        )
        by_exchange = (
            pl.DataFrame(
                {
                    "exchange": [r.exchange.lower() for r in rows],
                    "capital": [float(r.exposure) for r in rows],
                }
            )
            .group_by("exchange")
            .agg(pl.col("capital").sum())
        )
        if by_exchange["capital"].sum() > 0:  # sin posiciones el gráfico sería un bloque vacío
            frame = by_exchange.rename({"capital": "capital (USD)"})
            _bar_chart(
                frame, "exchange", "capital (USD)", alt_text="Capital del paper por exchange"
            )
    st.markdown("**Contribución al riesgo de cola (CVaR95, un año)**")
    if art.budget is not None and art.budget_scenarios is not None:
        st.dataframe(
            portfolio.cvar_table(art.budget, art.budget_scenarios, current),
            hide_index=True,
            width="stretch",
            alt="Contribución de cada parte al riesgo de cola de la cartera",
        )
        st.caption(
            "Contribución de Euler: cuánto pierde en promedio cada parte en el peor 5 % de los"
            " años simulados. Las partes suman el CVaR95 de la cartera. Un valor negativo es una"
            " ganancia: el efectivo rinde el 4 % incluso en esos años."
        )
    elif art.budget is not None:  # sin presupuesto ya se avisó arriba
        st.info(
            "Faltan los escenarios del presupuesto: vuelve a correr `uv run pq research budget`."
        )
    _portfolio_bands(view, art)


def _portfolio_bands(view: PaperView, art: Artifacts) -> None:
    st.markdown("**Paper frente a lo que esperaba el backtest (bandas del Monte Carlo)**")
    summary, returns = art.carry.get("H2"), art.carry_returns.get("H2")
    paper = portfolio.daily_paper_equity(view.valuations)
    if summary is None or returns is None or paper.height < 2:
        st.info("Hacen falta al menos dos días de paper y la evaluación de H2 para las bandas.")
        return
    daily = portfolio.development_returns(returns, str(summary.get("selected")))
    if daily.size < BLOCK_DAYS:
        st.info("La evaluación de H2 tiene muy pocos días para remuestrear las bandas.")
        return
    st.altair_chart(
        _bands_chart(portfolio.bands_frame(paper, daily)),
        width="stretch",
        theme=None,
        alt="El paper frente a la banda del 5 % al 95 % que esperaba el backtest",
    )
    st.caption(
        "Azul: el paper. Gris: la banda del 5 % al 95 % y la mediana (discontinua) al"
        " remuestrear por bloques de 21 días los retornos diarios del desarrollo de H2 (la"
        " configuración elegida). Si el paper sale de la banda, algo es distinto del backtest."
    )


def _bands_chart(frame: pl.DataFrame) -> alt.LayerChart | alt.FacetChart:
    """Banda del 5 % al 95 % sombreada, la mediana y el paper. El eje no fuerza el cero."""
    axis = alt.Axis(format="d", tickMinStep=1)  # días enteros
    base = alt.Chart(frame.to_pandas()).encode(x=alt.X("día:Q", title="días de paper", axis=axis))
    scale = alt.Scale(zero=False)
    band = base.mark_area(opacity=0.25, color=style.NEUTRAL).encode(
        y=alt.Y("backtest p5:Q", scale=scale, title="capital (inicio = 1)"),
        y2="backtest p95:Q",
    )
    median = base.mark_line(color=style.NEUTRAL, strokeDash=[4, 4]).encode(
        y=alt.Y("backtest mediana:Q", scale=scale)
    )
    # Con puntos: los días sin runner (laptop apagada) quedan como huecos reales, no se inventan.
    paper = base.mark_line(
        color=style.BRAND, strokeWidth=2, point=alt.OverlayMarkDef(color=style.BRAND, size=40)
    ).encode(y=alt.Y("paper:Q", scale=scale))
    return alt.layer(band, median, paper)


def _move(delta: int) -> None:
    st.session_state["paso"] = tour.clamp(int(st.session_state.get("paso", 0)) + delta)


def _sidebar_tour(pages: dict[str, StreamlitPage]) -> None:
    """Recorrido de la feria: qué página abrir, qué decir y qué señalar en cada paso."""
    step = tour.clamp(int(st.session_state.get("paso", 0)))
    current, total = tour.STEPS[step], len(tour.STEPS)
    with st.sidebar:
        st.markdown(f"### Recorrido de la feria · paso {step + 1} de {total}")
        st.progress((step + 1) / total)
        st.subheader(current.title)
        if current.tab is not None:
            st.markdown(f"**Abre:** {current.tab}")
            if current.tab in pages:
                st.page_link(pages[current.tab], label="Ir a esa página", icon=":material/east:")
        st.markdown(f"**Di:** {current.say}")
        st.markdown(f"**Señala:** {current.show}")
        back, forward = st.columns(2)
        back.button(
            "Anterior",
            icon=":material/arrow_back:",
            disabled=step == 0,
            on_click=_move,
            args=(-1,),
            width="stretch",
        )
        forward.button(
            "Siguiente",
            icon=":material/arrow_forward:",
            disabled=step == total - 1,
            on_click=_move,
            args=(1,),
            width="stretch",
        )


# --- Páginas (PQ-127) --------------------------------------------------------------------------
# Con st.navigation solo se ejecuta la página visible. Con st.tabs se calculaban las 9 en cada
# rerun (hallazgo 3 de PQ-125).


@dataclass(frozen=True)
class _Context:
    data_dir: Path
    art: Artifacts
    max_age: int
    fair: bool


def _context() -> _Context:
    settings = load_settings()
    return _Context(
        settings.data_dir,
        load_artifacts(settings.data_dir),
        settings.paper_heartbeat_max_age_minutes,
        bool(st.session_state.get(FAIR_KEY)),
    )


def _page_home() -> None:
    ctx = _context()
    _tab_home(ctx.data_dir, ctx.art, ctx.max_age)


def _page_carry() -> None:
    _tab_carry(_context().art)


def _page_model() -> None:
    _tab_model(_context().art)


def _page_simulation() -> None:
    _tab_simulation(_context().art)


def _page_what_if() -> None:
    _tab_what_if(_context().data_dir)


def _page_nowcast() -> None:
    _tab_nowcast(_context().data_dir)


def _page_live() -> None:
    ctx = _context()
    if ctx.fair:  # se redibuja sola, sin recargar el resto del tablero
        st.fragment(run_every=tour.LIVE_REFRESH)(_tab_live)(
            ctx.data_dir, ctx.art, ctx.max_age, auto_refresh=True
        )
    else:
        _tab_live(ctx.data_dir, ctx.art, ctx.max_age)


def _page_portfolio() -> None:
    ctx = _context()
    _tab_portfolio(ctx.data_dir, ctx.art)


def _page_data() -> None:
    ctx = _context()
    _tab_data(ctx.art)
    st.caption(f"Para el equipo: artefactos leídos de `{ctx.data_dir}` (solo lectura).")


@dataclass(frozen=True)
class PageSpec:
    label: str
    render: Callable[[], None]
    icon: str
    url_path: str
    section: str


# Patrón F de storytelling: cada página responde una pregunta del jurado, en orden.
PAGES: tuple[PageSpec, ...] = (
    PageSpec("Inicio: ¿cómo va?", _page_home, ":material/home:", "inicio", "Resultados"),
    PageSpec(
        "¿Funciona? Carry y gates", _page_carry, ":material/fact_check:", "carry", "Resultados"
    ),
    PageSpec(
        "¿Qué predice? Modelo", _page_model, ":material/model_training:", "modelo", "Resultados"
    ),
    PageSpec(
        "¿Qué riesgo hay? Simulación",
        _page_simulation,
        ":material/casino:",
        "simulacion",
        "Resultados",
    ),
    PageSpec(
        "¿Y si invierto? Simula tu inversión",
        _page_what_if,
        ":material/calculate:",
        "simula-tu-inversion",
        "Para ti",
    ),
    PageSpec(
        "¿Qué predice hoy? Funding en vivo",
        _page_nowcast,
        ":material/online_prediction:",
        "funding-hoy",
        "Para ti",
    ),
    PageSpec(
        "¿Cómo va en vivo? Paper trading",
        _page_live,
        ":material/monitor_heart:",
        "paper-trading",
        "En vivo",
    ),
    PageSpec(
        "¿Cómo se reparte? Cartera", _page_portfolio, ":material/pie_chart:", "cartera", "En vivo"
    ),
    PageSpec("Datos y calidad (técnico)", _page_data, ":material/database:", "datos", "Técnico"),
)
LABELS = [p.label for p in PAGES]


def render_page(url_path: str) -> None:
    """Dibuja una sola página, sin navegación. Lo usan los tests (AppTest no navega a funciones)."""
    style.enable_altair_theme()
    next(p for p in PAGES if p.url_path == url_path).render()


def main() -> None:
    st.set_page_config(
        page_title="PrometheusQuant", page_icon=":material/monitoring:", layout="wide"
    )
    style.enable_altair_theme()
    if tour.is_fair_mode(st.query_params.to_dict()):
        st.session_state[FAIR_KEY] = True  # la navegación limpia la URL: se recuerda en la sesión
    fair = bool(st.session_state.get(FAIR_KEY))
    sections: dict[str, list[StreamlitPage]] = {}
    by_label: dict[str, StreamlitPage] = {}
    for spec in PAGES:
        page = st.Page(
            spec.render,
            title=spec.label,
            icon=spec.icon,
            url_path=spec.url_path,
            default=spec.url_path == "inicio",
        )
        sections.setdefault(spec.section, []).append(page)
        by_label[spec.label] = page
    current = st.navigation(sections, expanded=True)
    st.markdown(style.RESPONSIVE_CSS, unsafe_allow_html=True)  # solo CSS local, sin red
    if fair:
        st.query_params["modo"] = tour.FAIR_MODE
        st.markdown(tour.FAIR_CSS, unsafe_allow_html=True)
        _sidebar_tour(by_label)
    st.title("PrometheusQuant")  # corto: a 375 px el título largo se partía (hallazgo 11)
    st.caption("Estrategias de cripto probadas con reglas fijadas antes de ver los resultados.")
    current.run()


if __name__ == "__main__":
    main()
