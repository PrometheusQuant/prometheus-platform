"""Costes reales frente a los supuestos, para la página del paper (PQ-95). Sin Streamlit.

Lee los artefactos de ``pq paper costes`` (``data/research/costes/<bróker>-<fuente>.json``): una
fila por pata con lo medido y lo supuesto, y una fila por orden para el gráfico.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from prometheus_platform.api.dashboard import style


def _leg_name(leg: object) -> str:
    return "perpetuo" if leg == "perp" else "contado"


def _bp(value: float | None, decimals: int = 2) -> str:
    text = style.number(value, decimals)
    return text if text == "—" else f"{text} pb"


def legs_table(artifacts: Sequence[dict[str, Any]]) -> pl.DataFrame:
    """Una fila por fuente y pata: lo medido frente a lo supuesto, ya en formato español."""
    rows = []
    for art in artifacts:
        for leg in art.get("legs", []):
            worse = [
                name
                for name, flag in (
                    ("slippage", leg.get("slippage_worse")),
                    ("comisión", leg.get("fee_worse")),
                )
                if flag
            ]
            rows.append(
                {
                    "fuente": str(art.get("source", "?")),
                    "pata": "perpetuo" if leg.get("leg") == "perp" else "al contado",
                    "órdenes": style.number(leg.get("orders"), 0),
                    "slippage mediano": _bp(leg.get("slippage_bp_median")),
                    "slippage p90": _bp(leg.get("slippage_bp_p90")),
                    "supuesto": _bp(leg.get("assumed_slippage_bp"), 0),
                    "comisión media": style.pct(leg.get("fee_rate_mean"), 3),
                    "comisión supuesta": style.pct(leg.get("assumed_fee_rate"), 3),
                    "¿peor que lo supuesto?": ", ".join(worse) or "no",
                }
            )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def orders_frame(artifacts: Sequence[dict[str, Any]]) -> pl.DataFrame:
    """Una fila por orden con su slippage y el supuesto, para el gráfico de puntos."""
    rows = [
        {
            "serie": f"{art.get('source', '?')} · {_leg_name(o.get('leg'))}",
            "símbolo": str(o.get("symbol", "?")),
            "slippage (pb)": float(o.get("slippage_bp", 0.0)),
            "supuesto (pb)": float(o.get("assumed_slippage_bp", 0.0)),
        }
        for art in artifacts
        for o in art.get("orders", [])
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def headline(artifacts: Sequence[dict[str, Any]]) -> str:
    """Una frase con la conclusión: ¿lo medido es peor que lo que suponen los backtests?"""
    legs = [(art.get("source", "?"), leg) for art in artifacts for leg in art.get("legs", [])]
    if not legs:
        return "Todavía no hay fills medidos."
    worse = [
        f"{source} ({'perpetuo' if leg.get('leg') == 'perp' else 'contado'})"
        for source, leg in legs
        if leg.get("slippage_worse") or leg.get("fee_worse")
    ]
    orders = sum(int(leg.get("orders", 0)) for _, leg in legs)
    if not worse:
        return (
            f"En {orders} órdenes reales, el slippage mediano y la comisión quedan dentro de lo "
            "que suponen los backtests."
        )
    return (
        f"En {orders} órdenes reales, lo medido es peor que lo supuesto en: {', '.join(worse)}. "
        "Corresponde una enmienda de costes para los backtests siguientes."
    )
