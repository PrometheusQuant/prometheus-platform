"""Asistente del bot de Telegram (PQ-90): explica el estado de la cartera, **no decide ni opera**.

``/pregunta <texto>`` llama a la API de Claude con un puñado de **herramientas de solo lectura**:

| Herramienta | Qué devuelve |
|---|---|
| ``estado_paper`` | Equity, PnL, posiciones, heartbeat, kill-switch y alerta de contraparte |
| ``decisiones_recientes`` | Las últimas liquidaciones con su S_k, la decisión y el estado deseado |
| ``evaluaciones`` | Los gates de las evaluaciones del desarrollo y el presupuesto recomendado |

Por qué no puede operar (ADR-0013):

- El registro de herramientas es **cerrado**: cualquier otro nombre devuelve un error y no ejecuta
  nada.
- Las herramientas solo **leen** archivos (el diario, el heartbeat, los artefactos). Este módulo no
  importa el bróker, el kill-switch ni ningún puerto de órdenes; una prueba lo verifica.
- El kill-switch se consulta leyendo su archivo bandera, no con la clase que lo activa.

**Coste:** cada consulta registra sus tokens y su coste en ``data/paper/asistente_costes.json``.
Pasado el límite diario (``PQ_ASSISTANT_DAILY_LIMIT_USD``), el asistente deja de responder hasta el
día siguiente (UTC). Modelo: ``claude-opus-5-5`` con esfuerzo bajo (es una conversación corta) y
respaldo del servidor ante rechazos.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import build_view, read_heartbeat, strategy_breakdown
from prometheus_platform.domain.events import DomainEvent
from prometheus_platform.domain.ports import Clock
from prometheus_platform.ops.logging import get_logger

MODEL = "claude-opus-5-5"
# Precio de claude-opus-5-5 (tabla de la skill claude-api, 2026-11-03): 4 y 20 USD por millón.
PRICE_IN, PRICE_OUT = Decimal("4") / 1_000_000, Decimal("20") / 1_000_000
MAX_TURNS = 6  # vueltas de herramientas por pregunta: corta cualquier bucle
MAX_QUESTION_CHARS = 500
COST_FILE = "asistente_costes.json"
log = get_logger(component="paper_assistant")

SYSTEM = " ".join(
    [
        "Eres el asistente de PrometheusQuant, una plataforma de investigación y paper trading",
        "de cripto (sin dinero real).",
        "Respondes en español, en pocas frases y en lenguaje llano,",
        "a personas no técnicas de un jurado universitario.",
        "Usa las herramientas para mirar el estado real antes de responder y no inventes cifras.",
        "No puedes operar, cerrar posiciones ni tocar el kill-switch:",
        "si te lo piden, explica que eso solo lo hace el equipo desde la CLI.",
        "No des consejos de inversión.",
    ]
)


@dataclass(frozen=True, slots=True)
class Context:
    """Lo único que ven las herramientas: rutas de lectura."""

    paths: PaperPaths
    data_dir: Path
    replay: Callable[[], list[DomainEvent]]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def estado_paper(ctx: Context) -> dict[str, Any]:
    view = build_view(ctx.replay())
    equity, initial = view.equity, view.initial_equity
    flag = ctx.paths.kill_switch
    kill = _read_json(flag) if flag.exists() else None
    beat = read_heartbeat(ctx.paths.heartbeat)
    return {
        "equity_usd": None if equity is None else str(equity),
        "pnl_desde_el_inicio_usd": None
        if equity is None or initial is None
        else str(equity - initial),
        "funding_cobrado_usd": str(view.funding),
        "costes_usd": str(view.costs),
        "posiciones": {str(i): str(q) for i, q in view.positions.items()},
        "por_estrategia": [
            {"estrategia": r.strategy, "capital_usd": str(r.exposure), "pnl_usd": str(r.pnl)}
            for r in strategy_breakdown(view)
        ],
        "kill_switch": "activado" if flag.exists() else "armado",
        "motivo_kill_switch": (kill or {}).get("reason") if isinstance(kill, dict) else None,
        "heartbeat": None
        if beat is None
        else {k: str(v) for k, v in beat.items() if k in {"at", "ok", "detail", "contraparte"}},
    }


def decisiones_recientes(ctx: Context, cuantas: int = 6) -> dict[str, Any]:
    view = build_view(ctx.replay())
    rows = view.settlements[-max(1, min(cuantas, 20)) :]
    return {
        "regla": "entra si la media anualizada de las últimas 9 liquidaciones (S_k) >= 20 %;"
        " sale si baja de 10 % o la última tasa es negativa",
        "liquidaciones": [
            {
                "simbolo": s.symbol,
                "hora_utc": s.funding_time.isoformat(),
                "s_k_anualizada": s.s_k or None,
                "decision": s.action,
                "estado_deseado": "dentro" if s.target_open else "fuera",
            }
            for s in rows
        ],
    }


def evaluaciones(ctx: Context) -> dict[str, Any]:
    research = ctx.data_dir / "research"
    out: dict[str, Any] = {}
    for family in ("carry", "trend"):
        for summary in sorted((research / family).glob("*/summary.json")):
            data = _read_json(summary) or {}
            out[f"{family}-{summary.parent.name}"] = {
                "configuracion_elegida": data.get("selected"),
                "pasa_los_gates": data.get("passed"),
                "gates": [
                    {"gate": g.get("name"), "criterio": g.get("criterion"), "pasa": g.get("passed")}
                    for g in data.get("gates", [])
                ],
            }
    budget = _read_json(research / "budget" / "summary.json")
    if isinstance(budget, dict):
        out["presupuesto_recomendado"] = {
            k: budget.get(k) for k in ("presupuesto", "efectivo", "tope_por_exchange", "cvar95")
        }
    out["nota"] = "Evaluaciones del periodo de desarrollo; el holdout sigue cerrado."
    return out


Tool = Callable[..., dict[str, Any]]
# Registro CERRADO: solo estas tres funciones de lectura pueden ejecutarse.
TOOLS: Mapping[str, tuple[Tool, str, dict[str, Any]]] = {
    "estado_paper": (
        estado_paper,
        "Estado actual del paper trading: equity, PnL, posiciones, heartbeat y kill-switch.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    "decisiones_recientes": (
        decisiones_recientes,
        "Últimas liquidaciones de funding con la señal S_k y la decisión del carry.",
        {
            "type": "object",
            "properties": {"cuantas": {"type": "integer", "minimum": 1, "maximum": 20}},
            "additionalProperties": False,
        },
    ),
    "evaluaciones": (
        evaluaciones,
        "Gates de las evaluaciones del desarrollo (carry, tendencia) y presupuesto recomendado.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
}


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": desc, "input_schema": schema}
        for name, (_, desc, schema) in TOOLS.items()
    ]


def run_tool(name: str, arguments: Mapping[str, Any], ctx: Context) -> tuple[str, bool]:
    """Ejecuta una herramienta del registro. Devuelve (texto JSON, es_error)."""
    entry = TOOLS.get(name)
    if entry is None:
        return f"La herramienta {name!r} no existe: el asistente solo puede leer.", True
    function, _, schema = entry
    allowed = set(schema.get("properties", {}))
    kwargs = {k: v for k, v in arguments.items() if k in allowed}
    try:
        return json.dumps(function(ctx, **kwargs), ensure_ascii=False, default=str), False
    except Exception as exc:  # una herramienta rota no tumba el bot
        return f"Error al leer: {type(exc).__name__}", True


class CostLedger:
    """Coste por día UTC en un JSON pequeño, con escritura atómica."""

    def __init__(self, path: Path, daily_limit_usd: Decimal) -> None:
        self._path, self.limit = path, daily_limit_usd

    def spent(self, day: date) -> Decimal:
        data = _read_json(self._path)
        return (
            Decimal(str(data.get(day.isoformat(), "0"))) if isinstance(data, dict) else Decimal(0)
        )

    def add(self, day: date, cost: Decimal) -> Decimal:
        data = _read_json(self._path)
        data = data if isinstance(data, dict) else {}
        total = Decimal(str(data.get(day.isoformat(), "0"))) + cost
        data[day.isoformat()] = str(total)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        return total


Create = Callable[..., Any]  # client.beta.messages.create (inyectable en las pruebas)


class Assistant:
    def __init__(self, *, create: Create, ctx: Context, ledger: CostLedger, clock: Clock) -> None:
        self._create, self._ctx, self._ledger, self._clock = create, ctx, ledger, clock

    def answer(self, question: str) -> str:
        question = question.strip()[:MAX_QUESTION_CHARS]
        if not question:
            return (
                "Escribe la pregunta tras el comando, p. ej.: /pregunta ¿por qué no hay posición?"
            )
        today = self._clock.now().date()
        if self._ledger.spent(today) >= self._ledger.limit:
            limit = self._ledger.limit
            return f"El asistente llegó a su límite de {limit} USD por hoy. Vuelve mañana."
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        cost = Decimal(0)
        try:
            for _ in range(MAX_TURNS):
                response = self._create(
                    model=MODEL,
                    max_tokens=2000,
                    system=SYSTEM,
                    tools=tool_definitions(),
                    messages=messages,
                    output_config={"effort": "low"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
                usage = response.usage
                cost += PRICE_IN * usage.input_tokens + PRICE_OUT * usage.output_tokens
                if response.stop_reason == "refusal":
                    return (
                        "No puedo responder a eso. Prueba a preguntar por el estado de la cartera."
                    )
                if response.stop_reason != "tool_use":
                    text = "".join(b.text for b in response.content if b.type == "text").strip()
                    return text or "No tengo una respuesta para eso."
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        content, failed = run_tool(block.name, block.input or {}, self._ctx)
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content,
                                "is_error": failed,
                            }
                        )
                messages.append({"role": "user", "content": results})
            return "La pregunta necesitó demasiadas consultas; prueba con algo más concreto."
        finally:
            total = self._ledger.add(today, cost)
            log.info(
                "assistant_cost",
                cost_usd=str(cost.quantize(Decimal("0.0001"))),
                today_usd=str(total),
            )
