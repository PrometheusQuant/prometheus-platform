"""Dashboard de PrometheusQuant (PQ-34). Ejecutar con ``make dashboard``.

Solo lee artefactos del lakehouse (``PQ_DATA_DIR``); en Docker el volumen se monta en solo
lectura. Nunca muestra el holdout: las evaluaciones terminan antes de 2024-07-01.
"""

from __future__ import annotations

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

# Patrón F de storytelling: cada pestaña responde una pregunta del jurado, en orden.
LABELS = [
    "¿Qué pasó? Datos y calidad",
    "¿Funciona? Carry y gates",
    "¿Qué predice? Modelo",
    "¿Qué riesgo hay? Simulación",
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


def main() -> None:
    st.set_page_config(page_title="PrometheusQuant", layout="wide")
    st.title("PrometheusQuant: tablero de investigación")
    data_dir = load_settings().data_dir
    art = load_artifacts(data_dir)
    st.caption(f"Artefactos leídos de `{data_dir}` (solo lectura).")
    tabs = st.tabs(LABELS)
    for tab, render in zip(tabs, (_tab_data, _tab_carry, _tab_model, _tab_simulation), strict=True):
        with tab:
            render(art)


main()
