"""Comandos de calibración de costes del paper (PQ-95).

- ``pq paper costes``: mide el slippage y las comisiones de los diarios de un bróker y los compara
  con el ``CostModel``. Deja un JSON por fuente en ``data/research/costes/`` para el dashboard.
- ``pq paper muestreo-costes``: idas y vueltas pequeñas en Binance Demo (dinero ficticio), en un
  diario propio que no toca el libro del runner.

El runner de Binance Demo opera los símbolos de H2 en la **misma cuenta** y concilia sus
perpetuos con el exchange en cada ciclo. Si el muestreo abriera un SOL-PERP justo cuando el runner
concilia, este vería una diferencia de posición. Por eso el muestreo usa por defecto otros
símbolos, BTC y ETH (supuesto de 2 pb) y DOGE (supuesto de 5 pb, el de las altcoins), y rechaza
los del runner salvo con ``--incluir-simbolos-del-runner``, que solo debe usarse con el runner
Demo detenido.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper.compose import (
    BROKERS,
    PaperPaths,
    binance_demo_execution,
    paper_dir,
)
from prometheus_platform.domain.ports import Notifier
from prometheus_platform.execution.cost_sampling import sample_costs
from prometheus_platform.ops.settings import Environment, Settings
from prometheus_platform.research.carry_evaluation import HYPOTHESES, costs_for
from prometheus_platform.research.cost_calibration import (
    order_costs,
    render_markdown,
    summarize,
    to_json,
)

SAMPLE_JOURNAL = "muestreo-costes.jsonl"
COSTS_DIR = Path("research") / "costes"
SAMPLE_SYMBOLS = ("BTCUSDT", "ETHUSDT", "DOGEUSDT")
RUNNER_SYMBOLS = frozenset(HYPOTHESES["H2"])  # los que opera el runner de Binance Demo


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"no es un número: {text!r}") from None


def add_parsers(paper_actions: Any) -> None:
    costs = paper_actions.add_parser(
        "costes", help="Slippage y comisiones medidos frente al CostModel (PQ-95)"
    )
    costs.add_argument("--broker", choices=list(BROKERS), default="binance-demo")
    sample = paper_actions.add_parser(
        "muestreo-costes",
        help="Idas y vueltas pequeñas en Binance Demo para medir costes reales (PQ-95)",
    )
    sample.add_argument("--rondas", type=int, default=3, help="idas y vueltas por símbolo y pata")
    sample.add_argument("--nocional", type=_decimal, default=Decimal(100), help="USDT por orden")
    sample.add_argument("--symbols", default=",".join(SAMPLE_SYMBOLS))
    sample.add_argument(
        "--incluir-simbolos-del-runner",
        action="store_true",
        help="permite SOL, BNB y XRP; solo con el runner de Binance Demo detenido",
    )


def costs_report(
    args: argparse.Namespace, settings: Settings, notifier: Notifier | None = None
) -> int:
    root = paper_dir(settings.data_dir, args.broker)
    sources = {"runner": PaperPaths(root).journal, "muestreo": root / SAMPLE_JOURNAL}
    out_dir = settings.data_dir / COSTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, path in sources.items():
        label = f"{args.broker}/{name}"
        if not path.exists():
            print(f"### {label}\n\nSin diario en {path}.\n")
            continue
        orders = order_costs(JsonlEventJournal(path).replay(), costs_for)
        legs = summarize(orders)
        artifact = out_dir / f"{args.broker}-{name}.json"
        artifact.write_text(
            json.dumps(to_json(label, orders, legs), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(render_markdown(label, legs))
    return 0


def sample_costs_command(
    args: argparse.Namespace, settings: Settings, notifier: Notifier | None = None
) -> int:
    if settings.environment is Environment.LIVE:
        print("El muestreo de costes solo corre en Binance Demo, nunca con PQ_ENVIRONMENT=live")
        return 2
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    clash = sorted(RUNNER_SYMBOLS.intersection(symbols))
    if clash and not args.incluir_simbolos_del_runner:
        print(
            f"{', '.join(clash)} los opera el runner de Binance Demo en la misma cuenta: un "
            "muestreo a mitad de su ciclo le descuadra la conciliación. Usa otros símbolos o, "
            "con el runner detenido, --incluir-simbolos-del-runner."
        )
        return 2
    clock = SystemClock()
    gateway = binance_demo_execution(settings, clock)
    path = paper_dir(settings.data_dir, "binance-demo") / SAMPLE_JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    sent = sample_costs(
        gateway,
        JsonlEventJournal(path),
        clock,
        symbols=symbols,
        notional=args.nocional,
        rounds=args.rondas,
    )
    print(f"{sent} órdenes en Binance Demo registradas en {path}")
    return 0
