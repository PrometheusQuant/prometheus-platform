"""Modo feria del dashboard (PQ-102): tipografía grande, autorefresco y recorrido guiado.

Se activa con ``?modo=feria`` en la URL. El recorrido tiene 7 pasos, uno por sección del pitch
de 7 minutos (PQ-60): problema → por qué fallan los minoristas → nuestra respuesta → evidencia →
demo en vivo → viabilidad → cierre. Cada paso dice qué página abrir, qué señalar y qué decir.

**Para ajustar el guion** basta con editar ``STEPS``. Los textos no llevan cifras a propósito: las
muestra el dashboard desde los artefactos y así nunca quedan desactualizadas.

Todo es local: no pide nada a internet (plan B de PQ-63). El CSS no carga fuentes externas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

FAIR_MODE = "feria"
# La página en vivo se redibuja sola cada minuto en el modo feria: el runner cicla cada 60 s.
LIVE_REFRESH = timedelta(seconds=60)

# Tipografía para una pantalla grande vista a 2-3 metros. Solo fuentes del sistema.
FAIR_CSS = """
<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 22px; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"] { font-size: 1.15rem; line-height: 1.5; }
h1 { font-size: 3rem !important; }
h2, h3 { font-size: 2.1rem !important; }
[data-testid="stMetricValue"] { font-size: 2.6rem; }
[data-testid="stMetricLabel"] p { font-size: 1.2rem; }
button[data-baseweb="tab"] p { font-size: 1.15rem; }
[data-testid="stSidebar"] { min-width: 26rem; }
</style>
"""


@dataclass(frozen=True, slots=True)
class TourStep:
    title: str  # sección del pitch (PQ-60)
    tab: str | None  # página que se abre (su título); None si no hace falta
    say: str  # la frase para el público
    show: str  # qué señalar en la pantalla


STEPS: tuple[TourStep, ...] = (
    TourStep(
        "El problema",
        None,
        "Los bots y las plataformas de backtest muestran la curva más bonita: sin costes reales "
        "y sin contar los intentos que salieron mal.",
        "El menú del tablero: cada página responde una pregunta del jurado.",
    ),
    TourStep(
        "Por qué fallan los minoristas",
        "Datos y calidad (técnico)",
        "Deciden con datos con huecos y con información del futuro sin darse cuenta. Aquí los "
        "datos son point-in-time y los huecos se informan, no se rellenan.",
        "La tabla de calidad de la capa silver y la columna de huecos.",
    ),
    TourStep(
        "Nuestra respuesta",
        "¿Funciona? Carry y gates",
        "Pre-registramos la hipótesis antes de mirar, contamos todos los intentos y una estrategia "
        "solo avanza si pasa cuatro gates. Descartamos H1 aunque su Sharpe era alto.",
        "Los gates G1 a G4, el PBO y el Deflated Sharpe de H1 y H2.",
    ),
    TourStep(
        "La evidencia",
        "¿Qué riesgo hay? Simulación",
        "Simulamos miles de trayectorias, incluida la quiebra del exchange. Y abrimos una sola "
        "vez la prueba final con datos nunca vistos: el carry no la superó, y el tablero lo dice.",
        "La validación del simulador y la probabilidad de quiebra de equilibrio.",
    ),
    TourStep(
        "Demo en vivo",
        "¿Cómo va en vivo? Paper trading",
        "El runner decide ahora mismo con el funding real de Binance, sin dinero real, con riesgo "
        "pre-trade, kill-switch y alertas al móvil.",
        "El heartbeat, el kill-switch armado y las últimas liquidaciones (se actualiza sola).",
    ),
    TourStep(
        "Viabilidad",
        "¿Y si invierto? Simula tu inversión",
        "Con tu capital y tu horizonte: cuánto podrías ganar o perder y si le ganas a una "
        "stablecoin al 4 %.",
        "Pide a alguien del público un capital y un horizonte, y muestra P(perder dinero).",
    ),
    TourStep(
        "Cierre",
        None,
        "PrometheusQuant dice cuándo una estrategia no sirve: el carry pasó en desarrollo y "
        "falló en la prueba final. Lo siguiente: más estrategias por el mismo protocolo, como el "
        "momentum y Polymarket.",
        "Vuelve a la página en vivo mientras respondes preguntas.",
    ),
)


def is_fair_mode(query: Mapping[str, object]) -> bool:
    """``?modo=feria`` (sin distinguir mayúsculas). Cualquier otro valor deja el modo normal."""
    value = query.get("modo", "")
    if isinstance(value, list):  # una clave repetida llega como lista
        value = value[-1] if value else ""
    return str(value).strip().lower() == FAIR_MODE


def clamp(step: int) -> int:
    """Índice válido del recorrido (de 0 a 6)."""
    return max(0, min(len(STEPS) - 1, step))
