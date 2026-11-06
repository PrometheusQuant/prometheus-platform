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
from scipy import stats

from prometheus_platform.research.carry_evaluation import HypothesisEvaluation
from prometheus_platform.research.funding_model import ModelStudy
from prometheus_platform.research.simulation import REGIME_NAMES, Regime, SimulationStudy


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
    dates = np.array([d[:10] for d in evaluation.dates], dtype="datetime64[D]")
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


def write_model_study(study: ModelStudy, out_dir: Path) -> Path:
    """Resumen JSON del estudio predictivo del funding (PQ-32)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(study)
    payload.pop("roc_points")
    path = out_dir / "summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return path


def plot_roc(study: ModelStudy, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 5), dpi=150)
    auc = {f"{c.name}{':tuned' if c.tuned else ':default' if c.name != 'regla_s9' else ''}": c.auc
           for c in study.classification}  # fmt: skip
    for key, (fpr, tpr) in study.roc_points.items():
        if key.endswith(":default"):
            continue
        ax.plot(fpr, tpr, linewidth=1.4, label=f"{key} (AUC {auc.get(key, float('nan')):.3f})")
    ax.plot([0, 1], [0, 1], color="#94a3b8", linestyle=":", linewidth=1)
    ax.set_xlabel("Tasa de falsos positivos")
    ax.set_ylabel("Tasa de verdaderos positivos")
    ax.set_title("¿La próxima tasa superará el 20 %? (walk-forward)")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def write_simulation(study: SimulationStudy, out_dir: Path) -> Path:
    """Resumen JSON del estudio de simulación (cap. 6)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    names = [REGIME_NAMES[r] for r in Regime]
    payload = {
        "markov_1er_orden": {
            "estados": names,
            "conteos": study.chain.counts.tolist(),
            "transicion": study.chain.transition.tolist(),
            "estacionaria": study.chain.stationary.tolist(),
            "chi2_independencia": study.chain.chi2,
            "chi2_p": study.chain.chi2_p_value,
            "duracion_esperada": study.chain.expected_duration.tolist(),
        },
        "markov_bloques": {
            "bloque_liquidaciones": study.block_model.block,
            "transicion": study.block_model.chain.transition.tolist(),
            "estacionaria": study.block_model.chain.stationary.tolist(),
            "chi2_p": study.block_model.chain.chi2_p_value,
            "bloques_por_regimen": {
                REGIME_NAMES[r]: len(v) for r, v in study.block_model.weeks.items()
            },
        },
        "distribuciones": {
            REGIME_NAMES[r]: {
                "n": m.n,
                "masas_puntuales": m.point_mass,
                "ajustes": [asdict(f) for f in m.fits],
                "mejor": m.best.distribution if m.fits else None,
            }
            for r, m in study.regime_models.items()
        },
        "duraciones": [asdict(t) | {"regime": REGIME_NAMES[t.regime]} for t in study.sojourn],
        "validacion": [asdict(study.historical)] + [asdict(v) for v in study.validation],
        "escenarios": study.scenarios,
        "probabilidad_quiebra_equilibrio": study.break_even_failure,
        "frontera": study.frontier,
    }
    path = out_dir / "summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return path


def _save(fig: Any, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _plot_transitions(study: SimulationStudy, path: Path) -> Path:
    names = [REGIME_NAMES[r] for r in Regime]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), dpi=150)
    block_days = study.block_model.block // 3
    for ax, matrix, title in (
        (axes[0], study.chain.transition, "Liquidación a liquidación (1er orden)"),
        (axes[1], study.block_model.chain.transition, f"Bloques de {block_days} días"),
    ):
        ax.imshow(matrix, cmap="Oranges", vmin=0, vmax=1)
        ax.set_xticks(range(3), names)
        ax.set_yticks(range(3), names)
        ax.set_xlabel("régimen siguiente")
        ax.set_title(title, fontsize=9)
        for i, j in np.ndindex(matrix.shape):
            ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=9)
    axes[0].set_ylabel("régimen actual")
    return _save(fig, path)


def _plot_high_fit(study: SimulationStudy, path: Path) -> Path:
    high = next(t for t in study.sojourn if t.regime is Regime.HIGH)
    model = study.regime_models[Regime.HIGH]
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=150)
    ax.hist(model.empirical, bins=60, density=True, color="#cbd5e1", label="observado")
    grid = np.linspace(0, np.quantile(model.empirical, 0.99), 300)
    for fit in sorted(model.fits, key=lambda f: f.ks_statistic)[:2]:
        dist = getattr(stats, fit.distribution)(*fit.params)
        ax.plot(grid, dist.pdf(grid), label=f"{fit.distribution} (KS {fit.ks_statistic:.3f})")
    ax.set_xlim(0, grid[-1])
    ax.set_xlabel("exceso sobre 20 % anual")
    ax.set_title(
        f"Régimen alto: ajuste de distribuciones (racha p95: {high.p95_observed:.0f} observada"
        f" vs {high.p95_geometric:.0f} geométrica)",
        fontsize=8,
    )
    ax.legend(fontsize=8)
    return _save(fig, path)


def _plot_montecarlo(study: SimulationStudy, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=150)
    ax.hist(study.baseline.annual_returns * 100, bins=80, alpha=0.75, color="#c2410c",
            label="sin quiebra")  # fmt: skip
    ax.hist(study.tail_returns * 100, bins=80, alpha=0.45, color="#1d4ed8",
            label="con quiebra (p = 2 % anual)")  # fmt: skip
    ax.axvline(4, color="#334155", linestyle="--", linewidth=1, label="stablecoin 4 %")
    ax.set_yscale("log")
    ax.set_xlabel("retorno a 1 año (%)")
    ax.set_ylabel("trayectorias (escala log)")
    ax.set_title("Monte Carlo del carry H2 (años simulados)", fontsize=9)
    ax.legend(fontsize=8)
    return _save(fig, path)


def _plot_frontier(study: SimulationStudy, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=150)
    w = [f["w_carry"] * 100 for f in study.frontier]
    ax.plot(w, [f["retorno_esperado"] * 100 for f in study.frontier], color="#c2410c",
            label="retorno esperado")  # fmt: skip
    ax.plot(w, [f["cvar95"] * 100 for f in study.frontier], color="#1d4ed8", label="CVaR 95 %")
    ax.set_xlabel("% del capital en el carry (resto en stablecoin)")
    ax.set_ylabel("%")
    ax.set_title("Asignación con riesgo de quiebra del exchange (p = 2 % anual)", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return _save(fig, path)


def plot_simulation(study: SimulationStudy, figures: Path) -> list[Path]:
    """Las cuatro figuras del capítulo 6."""
    figures.mkdir(parents=True, exist_ok=True)
    return [
        _plot_transitions(study, figures / "markov-transiciones.png"),
        _plot_high_fit(study, figures / "ajuste-regimen-alto.png"),
        _plot_montecarlo(study, figures / "montecarlo-retornos.png"),
        _plot_frontier(study, figures / "asignacion-frontera.png"),
    ]
