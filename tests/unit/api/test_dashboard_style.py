"""Formato en español, lenguaje simple y resumen de estrategias de la portada (PQ-124)."""

import math

import altair as alt
import pytest

from prometheus_platform.api.dashboard import style
from prometheus_platform.api.dashboard.artifacts import Artifacts, strategy_overview


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1234.5, "1.234,50 USD"), (-0.5, "-0,50 USD"), (None, "—"), (math.nan, "—")],
)
def test_usd_en_formato_espanol(value: float | None, expected: str) -> None:
    assert style.usd(value) == expected


def test_porcentajes_signos_y_numeros() -> None:
    assert style.pct(0.0503) == "5,0 %"
    assert style.pct(0.0503, 2, signed=True) == "+5,03 %"
    assert style.pct(-0.1455, 2) == "-14,55 %"
    assert style.usd(0.0, signed=True) == "0,00 USD"  # el cero no lleva signo
    assert style.number(16.3182, 3) == "16,318"
    assert style.status(True) == "✅ pasa"
    assert style.status(False) == "❌ no pasa"


def test_metricas_con_etiqueta_y_ayuda() -> None:
    assert style.metric_label("max_drawdown") == "Peor caída"
    assert style.metric_value("max_drawdown", -0.12) == "-12,0 %"
    assert style.metric_value("sharpe", 1.726) == "1,73"
    assert style.metric_label("desconocida") == "desconocida"
    assert all(help_text for _, help_text in style.METRICS.values())


def test_tema_de_altair_paleta_fija_y_fechas_en_espanol() -> None:
    style.enable_altair_theme()
    assert alt.theme.active == "prometheus"
    config = style.altair_theme()["config"]
    assert config["range"]["category"] == list(style.SERIES)
    assert config["locale"]["time"]["shortMonths"][0] == "ene"
    assert config["locale"]["number"]["decimal"] == ","


def test_resumen_de_estrategias_segun_sus_artefactos() -> None:
    assert strategy_overview(Artifacts()) == []
    art = Artifacts(
        carry={
            "H2": {"passed": True, "selected_performance": {"cagr": 0.05, "max_drawdown": -0.004}}
        },
        trend={
            "T1": {"passed": True},
            "holdout": {"pasa": False, "rendimiento": {"cagr": 0.0276, "max_drawdown": -0.1455}},
        },
    )
    carry, trend = strategy_overview(art)
    assert (carry.name, carry.level) == ("Carry de funding", "warn")
    assert "5,0 %" in carry.summary
    assert (trend.name, trend.level, trend.stage) == (
        "Tendencia",
        "bad",
        "Descartada en la prueba final",
    )
    assert "2,8 %" in trend.summary


def test_tendencia_sin_holdout_y_carry_descartado() -> None:
    art = Artifacts(carry={"H2": {"passed": False}}, trend={"T1": {"passed": True}})
    carry, trend = strategy_overview(art)
    assert (carry.level, carry.stage) == ("bad", "Descartada en desarrollo")
    assert trend.level == "warn"
    holdout_ok = Artifacts(trend={"holdout": {"pasa": True, "rendimiento": {}}})
    assert strategy_overview(holdout_ok)[0].level == "ok"
