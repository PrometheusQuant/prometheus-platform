"""Costes cotizados, VAN, TIR y capital de equilibrio (PQ-49, Proyecto Integrador 8.3-8.4).

Evalúa la decisión **incremental**: poner un capital C en el carry en lugar de dejarlo en la
stablecoin al 4 % anual (el hurdle del pre-registro). El flujo anual es el del modelo de negocio
(cap. 8, §5.2):

    flujo = C · (r_P - r_B) - costes de operación del año

con r_P = retorno anual esperado del carry en cada escenario del Monte Carlo (cap. 6) y r_B = 4 %.
La tasa de descuento también es 4 %: es el costo de oportunidad del capital. La inversión inicial
es la puesta en marcha del despliegue (horas x tarifa). El desarrollo ya hecho es un costo hundido
y no entra en la decisión; se informa aparte.

Los precios externos llevan su fuente y su fecha. Lo que no se pudo verificar en la fuente oficial
queda marcado ``verificado=False`` y se excluye del escenario principal.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scipy.optimize import brentq

HURDLE = 0.04  # stablecoin al 4 % anual: benchmark B2 y costo de oportunidad (pre-registro §6)
DISCOUNT_RATE = HURDLE
HORIZONS = (1, 3)
CAPITALS = (500.0, 1_000.0, 5_000.0, 10_000.0)
IRR_BRACKET = (-0.99, 10.0)
ILLUSTRATIVE_RATE_USD_HOUR = 5.0  # supuesto ilustrativo, sin fuente: solo para la sensibilidad
QUOTE_DATE = "2026-11-06"

# Tipos de cambio y salario: fuente oficial, consultados el 2026-11-06.
EUR_USD = 1.1165  # BCE vía api.frankfurter.app
BOB_USD = 11.89  # tipo de cambio oficial del BCB, tabla 208-26
MIN_WAGE_BOB_MONTH = 3_300.0  # salario mínimo nacional 2026 (DS 5516)
LEGAL_HOURS_MONTH = 240.0  # 30 días x 8 horas: base legal para la hora de trabajo en Bolivia
MIN_WAGE_USD_HOUR = MIN_WAGE_BOB_MONTH / LEGAL_HOURS_MONTH / BOB_USD


@dataclass(frozen=True)
class Quote:
    """Un precio externo con su fuente. ``verificado`` = leído en la fuente oficial."""

    concepto: str
    usd_mes: float
    fuente: str
    fecha: str
    verificado: bool
    nota: str = ""


INFRA_OPTIONS: tuple[Quote, ...] = (
    Quote(
        "Laptop propia (solo durante la demo)",
        0.0,
        "equipo existente",
        QUOTE_DATE,
        True,
        "no opera 24/7: el historial tendría huecos",
    ),
    Quote(
        "Oracle Cloud Always Free (Ampere A1, 2 OCPU y 12 GB)",
        0.0,
        "https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm",
        QUOTE_DATE,
        True,
        "1.500 OCPU-h y 9.000 GB-h al mes; 200 GB de bloque. Capacidad sujeta a disponibilidad",
    ),
    Quote(
        "Hetzner Cloud Cost-Optimized (plan más barato)",
        5.99 * EUR_USD,
        "https://www.hetzner.com/cloud/",
        QUOTE_DATE,
        True,
        "desde 5,99 EUR/mes sin IVA; fuera de la UE el IVA normalmente no aplica (por verificar)",
    ),
)

DOMAIN = Quote(
    "Dominio .com en Cloudflare Registrar (opcional)",
    11.17 / 12,
    "https://costgoat.com/compare/domains/com",
    "2026-10-20",
    False,
    "precio al costo tras la subida mayorista del 2026-11-01; por verificar en Cloudflare",
)


@dataclass(frozen=True)
class Labor:
    """Horas del equipo valoradas al costo de oportunidad (parámetros declarados)."""

    tarifa_usd_hora: float = MIN_WAGE_USD_HOUR
    horas_operacion_mes: float = 8.0  # supuesto: monitoreo, actualizaciones y revisión semanal
    horas_puesta_en_marcha: float = 16.0  # supuesto: crear la VM, desplegar y probar
    fuente_tarifa: str = "salario mínimo nacional 2026 (DS 5516) / 240 h / TCO del BCB"


@dataclass(frozen=True)
class Evaluation:
    escenario: str
    infraestructura: str
    capital: float
    anios: int
    retorno_anual: float
    flujo_anual: float
    inversion_inicial: float
    van: float
    tir: float | None
    capital_equilibrio: float | None


def npv(rate: float, flows: Sequence[float]) -> float:
    """Valor actual neto; ``flows[0]`` ocurre hoy (t = 0)."""
    return sum(f / (1 + rate) ** t for t, f in enumerate(flows))


def irr(flows: Sequence[float]) -> float | None:
    """Tasa interna de retorno. ``None`` si el VAN no cambia de signo en el intervalo buscado."""
    low, high = IRR_BRACKET
    f_low, f_high = npv(low, flows), npv(high, flows)
    if f_low == 0:
        return low
    if f_low * f_high > 0:
        return None
    return float(brentq(lambda r: npv(r, flows), low, high, xtol=1e-12))


def annuity_factor(rate: float, years: int) -> float:
    return sum(1 / (1 + rate) ** t for t in range(1, years + 1))


def break_even_capital(
    excess_return: float, annual_cost: float, initial_cost: float, rate: float, years: int
) -> float | None:
    """Capital con VAN = 0: C* = (I0 + K·A) / (Δr·A).

    ``None`` si Δr ≤ 0: ningún capital alcanza el equilibrio.
    """
    if excess_return <= 0:
        return None
    factor = annuity_factor(rate, years)
    return (initial_cost + annual_cost * factor) / (excess_return * factor)


def evaluate(  # noqa: PLR0913 - keyword-only: cada argumento es una dimensión del escenario
    *,
    escenario: str,
    retorno_anual: float,
    infra: Quote,
    labor: Labor,
    capital: float,
    years: int,
    extra_usd_mes: float = 0.0,
) -> Evaluation:
    annual_cost = 12 * (
        infra.usd_mes + extra_usd_mes + labor.horas_operacion_mes * labor.tarifa_usd_hora
    )
    initial = labor.horas_puesta_en_marcha * labor.tarifa_usd_hora
    excess = retorno_anual - HURDLE
    flow = capital * excess - annual_cost
    flows = [-initial] + [flow] * years
    return Evaluation(
        escenario=escenario,
        infraestructura=infra.concepto,
        capital=capital,
        anios=years,
        retorno_anual=retorno_anual,
        flujo_anual=flow,
        inversion_inicial=initial,
        van=npv(DISCOUNT_RATE, flows),
        tir=irr(flows),
        capital_equilibrio=break_even_capital(excess, annual_cost, initial, DISCOUNT_RATE, years),
    )


@dataclass
class FinanceSummary:
    fecha_cotizacion: str
    tasa_descuento: float
    hurdle: float
    tipo_cambio: dict[str, Any]
    mano_de_obra: dict[str, Any]
    cotizaciones: list[dict[str, Any]]
    escenarios: dict[str, dict[str, float]]
    evaluaciones: list[dict[str, Any]] = field(default_factory=list)
    sensibilidad_tarifa: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_scenarios(data_dir: Path) -> dict[str, dict[str, float]]:
    """Retorno anual simulado (media, p5 y p95) de cada escenario de quiebra del cap. 6."""
    path = data_dir / "research" / "simulation" / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: {k: float(values[k]) for k in ("media", "p5", "p95")}
        for name, values in summary["escenarios"].items()
    }


def run_finance(data_dir: Path, labor: Labor | None = None) -> FinanceSummary:
    labor = labor or Labor()
    scenarios = load_scenarios(data_dir)
    evaluations = [
        evaluate(
            escenario=name,
            retorno_anual=values["media"],
            infra=infra,
            labor=labor,
            capital=capital,
            years=years,
        )
        for name, values in scenarios.items()
        for infra in INFRA_OPTIONS
        for capital in CAPITALS
        for years in HORIZONS
    ]
    best = max(scenarios, key=lambda n: scenarios[n]["media"])
    sensitivity = []
    for label, rate in (
        ("horas no valoradas", 0.0),
        ("salario mínimo (fuente oficial)", labor.tarifa_usd_hora),
        ("supuesto ilustrativo", ILLUSTRATIVE_RATE_USD_HOUR),
    ):
        variant = Labor(
            tarifa_usd_hora=rate,
            horas_operacion_mes=labor.horas_operacion_mes,
            horas_puesta_en_marcha=labor.horas_puesta_en_marcha,
            fuente_tarifa=label,
        )
        result = evaluate(
            escenario=best,
            retorno_anual=scenarios[best]["media"],
            infra=INFRA_OPTIONS[1],
            labor=variant,
            capital=CAPITALS[1],
            years=HORIZONS[-1],
        )
        sensitivity.append(
            {
                "tarifa": label,
                "usd_hora": rate,
                "escenario": best,
                "capital_equilibrio": result.capital_equilibrio,
            }
        )
    return FinanceSummary(
        sensibilidad_tarifa=sensitivity,
        fecha_cotizacion=QUOTE_DATE,
        tasa_descuento=DISCOUNT_RATE,
        hurdle=HURDLE,
        tipo_cambio={"EUR_USD": EUR_USD, "BOB_USD": BOB_USD},
        mano_de_obra=asdict(labor),
        cotizaciones=[asdict(q) for q in (*INFRA_OPTIONS, DOMAIN)],
        escenarios=scenarios,
        evaluaciones=[asdict(e) for e in evaluations],
    )


def write_finance(summary: FinanceSummary, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.json"
    path.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# --- Tablas para el documento (generadas: no se copian cifras a mano) -------------------------

DOC_START = "<!-- PQ-49:inicio (generado por `uv run pq research finance --update-doc`) -->"
DOC_END = "<!-- PQ-49:fin -->"


def _usd(value: float | None) -> str:
    if value is None:
        return "no existe"
    return f"{value:,.0f} USD".replace(",", ".")


def _pct(value: float | None) -> str:
    return "no existe" if value is None else f"{100 * value:.1f} %".replace(".", ",")


def _source(url: str) -> str:
    return f"<{url}>" if url.startswith("http") else url


def render_markdown(summary: FinanceSummary, *, infra: str | None = None) -> str:
    oracle = infra or INFRA_OPTIONS[1].concepto
    rows = [e for e in summary.evaluaciones if e["infraestructura"] == oracle]
    lines = [
        DOC_START,
        "",
        f"**Fecha de cotización:** {summary.fecha_cotizacion}. "
        f"**Tasa de descuento y benchmark:** {_pct(summary.tasa_descuento)} anual (stablecoin).",
        "",
        "#### Costes cotizados (8.3)",
        "",
        "| Concepto | USD/mes | Fuente | Verificado |",
        "|---|---:|---|---|",
    ]
    for q in summary.cotizaciones:
        verified = "sí" if q["verificado"] else "**por verificar**"
        usd = f"{q['usd_mes']:.2f}".replace(".", ",")
        lines.append(
            f"| {q['concepto']} | {usd} | {_source(q['fuente'])} ({q['fecha']}) | {verified} |"
        )
    labor = summary.mano_de_obra
    rate = f"{labor['tarifa_usd_hora']:.2f}".replace(".", ",")
    lines += [
        "",
        f"- **Horas del equipo:** {rate} USD/h ({labor['fuente_tarifa']}). Es un piso: el costo de",
        "  oportunidad real de un analista es mayor. Las horas de operación"
        f" ({labor['horas_operacion_mes']:.0f} h/mes) y de puesta en marcha"
        f" ({labor['horas_puesta_en_marcha']:.0f} h) son **supuestos declarados**.",
        "- **Comisiones y slippage de Binance:** ya están dentro de los retornos simulados (VIP 0,"
        " [compliance](../compliance/binance.md)); las reales se confirman en PQ-17.",
        "- **Desarrollo ya realizado:** costo hundido; no entra en la decisión de operar.",
        "",
        f"#### Evaluación con {oracle} (8.4)",
        "",
        "Flujo anual = C·(r_P - 4 %) - costes de operación. VAN a 1 y 3 años; TIR sobre la"
        " puesta en marcha; capital de equilibrio = capital mínimo con VAN = 0.",
        "",
        "| Escenario (cap. 6) | r_P medio | Capital | VAN 1 año | VAN 3 años | TIR 3 años |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario in summary.escenarios:
        for capital in CAPITALS:
            one, three = (
                next(
                    e
                    for e in rows
                    if e["escenario"] == scenario and e["capital"] == capital and e["anios"] == y
                )
                for y in HORIZONS
            )
            lines.append(
                f"| {scenario} | {_pct(one['retorno_anual'])} | {_usd(capital)} |"
                f" {_usd(one['van'])} | {_usd(three['van'])} | {_pct(three['tir'])} |"
            )
    lines += [
        "",
        "**Capital de equilibrio (VAN = 0) por infraestructura, a 3 años**",
        "",
        "| Escenario | " + " | ".join(q["concepto"] for q in summary.cotizaciones[:3]) + " |",
        "|---|" + "---:|" * 3,
    ]
    for scenario in summary.escenarios:
        cells = []
        for q in summary.cotizaciones[:3]:
            match = next(
                e
                for e in summary.evaluaciones
                if e["escenario"] == scenario
                and e["infraestructura"] == q["concepto"]
                and e["anios"] == HORIZONS[-1]
            )
            cells.append(_usd(match["capital_equilibrio"]))
        lines.append(f"| {scenario} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "**Sensibilidad a la tarifa horaria** (escenario"
        f" {summary.sensibilidad_tarifa[0]['escenario']}, Oracle, 3 años). Las horas de operación"
        " son el costo dominante; sin valorarlas, cualquier capital tiene VAN positivo:",
        "",
        "| Tarifa | USD/h | Capital de equilibrio |",
        "|---|---:|---:|",
    ]
    for row in summary.sensibilidad_tarifa:
        rate = f"{row['usd_hora']:.2f}".replace(".", ",")
        lines.append(f"| {row['tarifa']} | {rate} | {_usd(row['capital_equilibrio'])} |")
    lines += [
        "",
        "**Rango de un año (p5 a p95 del Monte Carlo), por cada 1.000 USD frente a la"
        " stablecoin:**",
        "",
        "| Escenario | Peor año (p5) | Año medio | Buen año (p95) |",
        "|---|---:|---:|---:|",
    ]
    for scenario, values in summary.escenarios.items():
        cells = [_usd(1_000 * (values[k] - summary.hurdle)) for k in ("p5", "media", "p95")]
        lines.append(f"| {scenario} | " + " | ".join(cells) + " |")
    lines += ["", DOC_END]
    return "\n".join(lines)


def update_document(path: Path, block: str) -> None:
    """Reemplaza el bloque entre los marcadores PQ-49 (o lo agrega al final si no existe)."""
    text = path.read_text(encoding="utf-8")
    if DOC_START in text and DOC_END in text:
        before = text[: text.index(DOC_START)]
        after = text[text.index(DOC_END) + len(DOC_END) :]
        text = before + block + after
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
