"""Estilo común del dashboard (PQ-124): paleta, tema de Altair, formato de cifras y lenguaje simple.

La paleta categórica es la de referencia de la skill *dataviz*: los tres primeros colores pasan el
validador de contraste y daltonismo en modo claro y oscuro. Las series van siempre en el mismo
orden. Los colores de estado (bien, atención, mal) no se reutilizan como series y siempre van con
un icono y un texto, nunca solo con el color.
"""

from __future__ import annotations

import math
from typing import Any, cast

import altair as alt

BRAND = "#2a78d6"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # 1 azul, 2 naranja, 3 aguamarina
NEUTRAL = "#8a8985"  # referencias y benchmarks: gris, para no competir con la serie principal
GRID = "#e6e5e1"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
FONT = "Source Sans Pro, Segoe UI, Helvetica, Arial, sans-serif"

OK, WARN, BAD = "✅", "⚠️", "❌"

# Locale de Vega en español para fechas y números de los ejes (sin depender del navegador).
_LOCALE = {
    "number": {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " USD"]},
    "time": {
        "dateTime": "%A, %e de %B de %Y, %X",
        "date": "%d/%m/%Y",
        "time": "%H:%M:%S",
        "periods": ["AM", "PM"],
        "days": ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"],
        "shortDays": ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"],
        "months": [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ],
        "shortMonths": [
            "ene",
            "feb",
            "mar",
            "abr",
            "may",
            "jun",
            "jul",
            "ago",
            "sep",
            "oct",
            "nov",
            "dic",
        ],
    },
}


def altair_theme() -> dict[str, Any]:
    """Ejes y rejilla discretos, líneas de 2 px, paleta fija y fechas en español."""
    return {
        "config": {
            "locale": _LOCALE,
            "font": FONT,
            "background": "transparent",
            "view": {"stroke": None},
            "range": {"category": list(SERIES)},
            "axis": {
                "gridColor": GRID,
                "domain": False,
                "tickColor": GRID,
                "labelColor": TEXT_SECONDARY,
                "titleColor": TEXT_SECONDARY,
                "titleFontWeight": "normal",
                "labelFontSize": 12,
                "titleFontSize": 12,
            },
            "axisX": {"grid": False},
            "legend": {"orient": "top", "labelColor": TEXT_SECONDARY, "title": None},
            "line": {"strokeWidth": 2},
            "title": {"anchor": "start", "color": TEXT, "fontSize": 15, "fontWeight": 600},
        }
    }


def enable_altair_theme() -> None:
    @alt.theme.register("prometheus", enable=True)
    def _theme() -> alt.theme.ThemeConfig:
        return cast("alt.theme.ThemeConfig", altair_theme())  # dict de configuración de Vega-Lite


# --- Cifras en formato español -----------------------------------------------------------------


def _es(text: str) -> str:
    """1,234.56 → 1.234,56."""
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fmt(value: float | None, decimals: int, *, signed: bool = False, scale: float = 1.0) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    sign = "+" if signed and value > 0 else ""
    return sign + _es(f"{value * scale:,.{decimals}f}")


def number(value: float | None, decimals: int = 2) -> str:
    return _fmt(value, decimals)


def usd(value: float | None, decimals: int = 2, *, signed: bool = False) -> str:
    text = _fmt(value, decimals, signed=signed)
    return text if text == "—" else f"{text} USD"


def pct(value: float | None, decimals: int = 1, *, signed: bool = False) -> str:
    text = _fmt(value, decimals, signed=signed, scale=100.0)
    return text if text == "—" else f"{text} %"


def status(passed: bool) -> str:
    return f"{OK} pasa" if passed else f"{BAD} no pasa"


# --- Lenguaje simple ---------------------------------------------------------------------------

METRICS: dict[str, tuple[str, str]] = {
    # clave: (etiqueta visible, ayuda)
    "sharpe": (
        "Sharpe",
        "Rentabilidad por unidad de riesgo. Más de 1 es bueno; menos de 0,5, débil.",
    ),
    "cagr": ("Crecimiento anual (CAGR)", "Cuánto creció el capital por año, en promedio."),
    "max_drawdown": ("Peor caída", "La mayor caída desde un máximo hasta un mínimo."),
    "calmar": ("Calmar", "Crecimiento anual dividido por la peor caída. Más alto es mejor."),
    "t_stat": (
        "Estadístico t",
        "Qué tan improbable es el resultado si en realidad no hubiera ventaja. Se exige más de 3.",
    ),
}

GLOSSARY: dict[str, str] = {
    "Carry de funding": (
        "Comprar una cripto en spot y venderla a la vez en el perpetuo. El precio se cancela y se "
        "cobra el *funding*, el pago periódico entre largos y cortos."
    ),
    "Gate": "Una condición mínima, fijada antes de ver resultados, que la estrategia debe cumplir.",
    "Holdout": (
        "Un periodo de datos guardado sin mirar. Se usa una sola vez, al final, para comprobar que "
        "el resultado no fue suerte."
    ),
    "Paper trading": "Operar con precios reales pero dinero simulado, para validar sin riesgo.",
    "Deflated Sharpe": (
        "El Sharpe corregido por el número de intentos: cuantas más pruebas, más exigente."
    ),
    "PBO": (
        "Probabilidad de que la configuración elegida sea un sobreajuste. Se exige menos de 0,5."
    ),
    "Kill-switch": (
        "El freno de emergencia: detiene toda la operación hasta que una persona lo rearme."
    ),
}


def metric_label(key: str) -> str:
    return METRICS.get(key, (key, ""))[0]


def metric_value(key: str, value: float | None) -> str:
    if key in {"cagr", "max_drawdown"}:
        return pct(value)
    return number(value)
