"""Dashboard de PrometheusQuant (PQ-34). Ejecutar con ``make dashboard``.

Solo lee artefactos del lakehouse (``PQ_DATA_DIR``); en Docker el volumen se monta en solo
lectura. Nunca muestra el holdout: las evaluaciones terminan antes de 2024-07-01.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import streamlit as st

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
from prometheus_platform.ops.settings import load_settings
from prometheus_platform.research import nowcast, what_if
from prometheus_platform.research.simulation import WeeklyRegimeModel

# Patrón F de storytelling: cada pestaña responde una pregunta del jurado, en orden.
LABELS = [
    "¿Qué pasó? Datos y calidad",
    "¿Funciona? Carry y gates",
    "¿Qué predice? Modelo",
    "¿Qué riesgo hay? Simulación",
    "¿Y si invierto? Simula tu inversión",
    "¿Qué predice hoy? Funding en vivo",
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
    st.markdown("**Qué variables pesan más en el modelo** (importancia por impureza)")
    top = result.importance[:5]
    st.bar_chart(
        # El número delante conserva el orden por importancia (el gráfico ordena por nombre).
        pl.DataFrame(
            {
                "variable": [f"{i}. {n}" for i, (n, _) in enumerate(top, start=1)],
                "importancia": [v for _, v in top],
            }
        ),
        x="variable",
        y="importancia",
    )
    st.caption("Es una predicción estadística, no una recomendación de inversión.")


def main() -> None:
    st.set_page_config(page_title="PrometheusQuant", layout="wide")
    st.title("PrometheusQuant: tablero de investigación")
    data_dir = load_settings().data_dir
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


main()
