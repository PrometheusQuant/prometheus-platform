"""Curva de valor del capítulo 8.1 (PQ-75).

Genera ``docs/academico/img/curva-de-valor.png``. Las puntuaciones de 1 a 5 son una
**valoración cualitativa del equipo**, justificada fila a fila en la matriz de
``docs/academico/modelo-de-negocio.md`` (§4.1). Los datos de mercado (precios, comisiones y
rendimientos) están en esa matriz, con su fuente y su fecha.

Uso: ``uv run python scripts/curva_de_valor.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt

CRITERIA = [
    "Coste bajo",
    "Transparencia\ndel backtest",
    "Control del\nsobreajuste",
    "Bajo riesgo de\ncontraparte",
    "Control de\nla custodia",
    "Facilidad\nde uso",
]
# 1 = peor, 5 = mejor, en el sentido de cada criterio (más alto siempre es mejor).
SCORES = {
    "Bots del exchange (Binance, Pionex)": [5, 1, 1, 2, 1, 5],
    "3Commas (SaaS de bots)": [2, 2, 1, 2, 2, 4],
    "Freqtrade / Hummingbot": [5, 4, 2, 2, 3, 2],
    "Basis tokenizado (Ethena sUSDe)": [4, 2, 3, 1, 1, 4],
    "Simple Earn en stablecoin": [5, 1, 3, 2, 1, 5],
    "PrometheusQuant": [4, 5, 5, 2, 3, 2],
}
OUT = Path(__file__).resolve().parents[1] / "docs" / "academico" / "img" / "curva-de-valor.png"


def main() -> None:
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    x = range(len(CRITERIA))
    for name, scores in SCORES.items():
        ours = name == "PrometheusQuant"
        ax.plot(
            x,
            scores,
            marker="o",
            linewidth=3.2 if ours else 1.4,
            alpha=1.0 if ours else 0.75,
            label=name,
            zorder=3 if ours else 2,
        )
    ax.set_xticks(list(x), CRITERIA)
    ax.set_yticks(range(1, 6))
    ax.set_ylim(0.5, 5.5)
    ax.set_ylabel("Valoración del equipo (1 = peor, 5 = mejor)")
    ax.set_title("Curva de valor: PrometheusQuant frente a las alternativas (cap. 8.1)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False, fontsize=8)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT)
    print(f"curva de valor en {OUT}")


if __name__ == "__main__":
    main()
