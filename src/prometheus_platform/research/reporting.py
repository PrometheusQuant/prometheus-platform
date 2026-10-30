"""Salidas de la evaluación: resumen JSON, retornos en Parquet y figuras para la documentación."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from prometheus_platform.research.carry_evaluation import HypothesisEvaluation


def summary(evaluation: HypothesisEvaluation) -> dict[str, Any]:
    return {
        "hypothesis": evaluation.hypothesis,
        "symbols": list(evaluation.symbols),
        "period": [evaluation.dates[0], evaluation.dates[-1]],
        "days": len(evaluation.dates),
        "selected": evaluation.selected,
        "cpcv_mean_test_sharpe": evaluation.cpcv_mean_sharpe,
        "selected_performance": asdict(evaluation.selected_performance),
        "benchmark_B1": asdict(evaluation.benchmark),
        "pbo": evaluation.pbo,
        "dsr": evaluation.dsr,
        "n_trials": evaluation.n_trials,
        "var_sharpe_daily": evaluation.var_sharpe,
        "gates": [asdict(g) for g in evaluation.gates],
        "passed": evaluation.passed,
        "decomposition": evaluation.decomposition,
        "sensitivity": evaluation.sensitivity,
    }


def write_outputs(evaluation: HypothesisEvaluation, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary(evaluation), indent=2, ensure_ascii=False, default=str)
    )
    pl.DataFrame({"date": evaluation.dates, **evaluation.returns}).write_parquet(
        out_dir / "daily_returns.parquet"
    )
    return out_dir / "summary.json"


def plot_equity(evaluation: HypothesisEvaluation, path: Path, benchmark: np.ndarray) -> Path:
    """Curvas de capital de las 9 configuraciones, la elegida resaltada, y B1."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = np.array(evaluation.dates, dtype="datetime64[D]")
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    for name, returns in sorted(evaluation.returns.items()):
        selected = name == evaluation.selected
        ax.plot(
            dates,
            np.cumprod(1 + returns),
            linewidth=2.2 if selected else 0.8,
            alpha=1.0 if selected else 0.45,
            color="#c2410c" if selected else "#64748b",
            label=f"{name} (elegida)" if selected else None,
        )
    ax.plot(dates, np.cumprod(1 + benchmark[: len(dates)]), color="#1d4ed8", linewidth=1.4,
            linestyle="--", label="B1 siempre activo")  # fmt: skip
    ax.set_title(
        f"{evaluation.hypothesis} · {', '.join(evaluation.symbols)} · desarrollo, neto de costes"
    )
    ax.set_ylabel("Capital (inicio = 1)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
