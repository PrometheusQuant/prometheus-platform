"""Monitoreo de drift (CRISP-ML(Q) F6, PQ-86): datos, modelo y desempeño frente a lo esperado.

Tres detectores, cada uno con su umbral documentado en ``docs/runbooks/drift.md``:

- **Datos:** el funding anualizado posterior al holdout frente al del desarrollo, por símbolo
  (PSI ≥ 0,25, ``research/drift.py``).
- **Modelo:** la calibración del clasificador del capítulo 5, entrenado como siempre solo con el
  desarrollo, sobre las liquidaciones posteriores al holdout cuyo resultado ya se conoce
  (ECE ≥ 0,10).
- **Desempeño:** el capital del paper trading fuera de la banda p5-p95 del Monte Carlo del carry H2
  para los días que lleva operando (la misma banda de la pestaña de cartera, PQ-84).

**Nada se ajusta solo** (DoD, fase 6: «prohibido retocar sin un nuevo ciclo PDCA»). Una alerta
avisa al canal y, con ``--ticket``, abre un issue en GitHub para decidir con un ciclo nuevo.

El holdout del carry (2024-07-01 → 2026-09-30) no se lee: la referencia es el desarrollo
(``development_only``) y «en vivo» es todo lo posterior a ``HOLDOUT_END``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from prometheus_platform.api.dashboard import portfolio
from prometheus_platform.api.paper.report import PaperView
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.domain.protocol import HOLDOUT_END
from prometheus_platform.portfolio_risk.budget import BLOCK_DAYS
from prometheus_platform.research import carry_evaluation as ce
from prometheus_platform.research import nowcast
from prometheus_platform.research.drift import (
    ECE_ALERT,
    MIN_LIVE,
    PSI_ALERT,
    Calibration,
    DataDrift,
    calibration,
    data_drift,
)
from prometheus_platform.research.funding_model import FEATURES, TARGET, THRESHOLD
from prometheus_platform.research.panel import development_only

RUNBOOK = "docs/runbooks/drift.md"
PDCA = "no se ajusta nada solo: abre un ciclo PDCA nuevo (Plan → Do → Check → Act) para decidir"
TICKET_LABEL = "drift"

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Performance:
    days: int
    paper: float  # capital del paper con inicio en 1
    p5: float
    p50: float
    p95: float

    @property
    def alert(self) -> bool:
        return not self.p5 <= self.paper <= self.p95


@dataclass
class DriftReport:
    generated_at: datetime
    data: list[DataDrift] = field(default_factory=list)
    model: Calibration | None = None
    performance: Performance | None = None
    skipped: dict[str, str] = field(default_factory=dict)  # detector → por qué no se evaluó

    def alerts(self, environment: str) -> list[Alert]:
        found = []
        moved = [d for d in self.data if d.alert]
        if moved:
            details = {
                d.symbol: f"PSI {d.psi:.2f}, mediana {d.reference_median:.1%} → {d.live_median:.1%}"
                for d in moved
            }
            found.append(self._alert("datos", f"PSI ≥ {PSI_ALERT}", details, environment))
        if self.model is not None and self.model.alert:
            details = {
                "ECE": f"{self.model.ece:.3f}",
                "Brier": f"{self.model.brier:.3f}",
                "AUC": f"{self.model.auc:.3f}" if self.model.auc is not None else "n/d",
                "liquidaciones": str(self.model.n),
            }
            found.append(self._alert("modelo", f"ECE ≥ {ECE_ALERT}", details, environment))
        if self.performance is not None and self.performance.alert:
            perf = self.performance
            details = {
                "días de paper": str(perf.days),
                "capital del paper": f"{perf.paper:.4f}",
                "banda p5-p95": f"{perf.p5:.4f} a {perf.p95:.4f}",
            }
            found.append(self._alert("desempeño", "fuera de la banda p5-p95", details, environment))
        return found

    def _alert(
        self, detector: str, threshold: str, details: dict[str, str], environment: str
    ) -> Alert:
        return Alert(
            severity=AlertSeverity.WARNING,
            title=f"drift de {detector}",
            occurred_at=self.generated_at,
            environment=environment,
            details={**details, "umbral": threshold, "acción": PDCA, "runbook": RUNBOOK},
        )

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "generated_at": self.generated_at.isoformat(),
            "thresholds": {"psi": PSI_ALERT, "ece": ECE_ALERT, "performance": "p5-p95"},
            "data": [asdict(d) | {"alert": d.alert, "level": d.level} for d in self.data],
            "model": asdict(self.model) | {"alert": self.model.alert} if self.model else None,
            "performance": (
                asdict(self.performance) | {"alert": self.performance.alert}
                if self.performance
                else None
            ),
            "skipped": self.skipped,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


# --- detectores sobre datos ya cargados -------------------------------------------------------


def _live(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.filter(pl.col("funding_time") > HOLDOUT_END)


def check_data(report: DriftReport, panels: Mapping[str, pl.DataFrame]) -> None:
    for symbol, panel in panels.items():
        reference = development_only(panel)["annualized"].drop_nulls().to_numpy()
        live = _live(panel)["annualized"].drop_nulls().to_numpy()
        if live.size < MIN_LIVE:
            report.skipped[f"datos {symbol}"] = f"solo {live.size} liquidaciones tras el holdout"
            continue
        report.data.append(data_drift(symbol, reference, live))


def check_model(
    report: DriftReport, panels: Mapping[str, pl.DataFrame], params: dict[str, int]
) -> None:
    """Calibración en vivo del clasificador entrenado solo con el desarrollo."""
    dev = pl.concat([development_only(p) for p in panels.values()], how="diagonal_relaxed")
    live = pl.concat([_live(p) for p in panels.values()], how="diagonal_relaxed").drop_nulls(
        [*FEATURES, TARGET]
    )
    if live.height < MIN_LIVE:
        report.skipped["modelo"] = f"solo {live.height} liquidaciones con resultado tras el holdout"
        return
    trained = nowcast.train(dev, params)
    x = np.clip(live.select(FEATURES).cast(pl.Float64).to_numpy(), trained.low, trained.high)
    model = trained.model
    probs = model.predict_proba(x)[:, list(model.classes_).index(True)]
    labels = live[TARGET].cast(pl.Float64).to_numpy() >= THRESHOLD
    report.model = calibration(labels, probs)


def check_performance(report: DriftReport, view: PaperView, daily: np.ndarray | None) -> None:
    paper = portfolio.daily_paper_equity(view.valuations)
    if daily is None or daily.size < BLOCK_DAYS:
        report.skipped["desempeño"] = "falta la evaluación de H2 (sus retornos del desarrollo)"
        return
    bands = portfolio.bands_frame(paper, daily)
    if bands.is_empty():
        report.skipped["desempeño"] = "el paper lleva menos de un día de valoraciones"
        return
    last = bands.row(-1, named=True)
    report.performance = Performance(
        days=int(last["día"]),
        paper=float(last["paper"]),
        p5=float(last["backtest p5"]),
        p50=float(last["backtest mediana"]),
        p95=float(last["backtest p95"]),
    )


# --- carga y tickets ----------------------------------------------------------------------------


def load_panels(data_dir: Path) -> dict[str, pl.DataFrame]:
    """Liquidaciones (con sus variables) de los símbolos de H1 y H2 desde silver."""
    symbols = [s for group in ce.HYPOTHESES.values() for s in group]
    return {s: ce.load_symbol(data_dir / "silver", s).settlements for s in symbols}


def write_report(report: DriftReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"drift-{report.generated_at:%Y-%m-%d}.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return path


def open_ticket(alert: Alert, run: Runner = subprocess.run) -> str:
    """Issue en GitHub con la etiqueta ``drift``; si ya hay uno abierto para el detector, ese.

    Devuelve la URL. Lanza ``RuntimeError`` si ``gh`` falla (sin sesión, sin red).
    """
    title = f"{alert.title.capitalize()} ({alert.occurred_at:%Y-%m-%d})"
    existing = _gh(
        run,
        "issue", "list", "--label", TICKET_LABEL, "--state", "open",
        "--search", f"{alert.title} in:title", "--json", "url", "--jq", ".[0].url",
    ).strip()  # fmt: skip
    if existing:
        return existing
    _gh(
        run,
        "label", "create", TICKET_LABEL, "--force", "--color", "D93F0B",
        "--description", "Alerta de drift (PQ-86): decidir con un ciclo PDCA",
    )  # fmt: skip
    body = "\n".join(
        [
            f"Alerta automática de `pq monitor drift` ({alert.occurred_at:%Y-%m-%d %H:%M} UTC).",
            "",
            *(f"- **{k}:** {v}" for k, v in sorted(alert.details.items())),
            "",
            "Regla de la DoD (fase 6): **prohibido retocar sin un nuevo ciclo PDCA**.",
            "Este issue no cambia nada: sirve para decidir, con un ticket PQ en Jira,",
            "si hace falta un ciclo nuevo.",
        ]
    )
    return _gh(
        run, "issue", "create", "--title", title, "--label", TICKET_LABEL, "--body", body
    ).strip()


def _gh(run: Runner, *args: str) -> str:
    result = run(["gh", *args], capture_output=True, text=True, timeout=60, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1]} falló ({result.returncode})")
    return str(result.stdout)


def summary_lines(report: DriftReport) -> Sequence[str]:
    lines = [
        f"datos {d.symbol}: PSI {d.psi:.3f} ({d.level}), KS {d.ks_statistic:.3f}"
        f" p={d.ks_pvalue:.2g}, n={d.n_live}"
        for d in report.data
    ]
    if report.model is not None:
        m = report.model
        auc = f"{m.auc:.3f}" if m.auc is not None else "n/d"
        lines.append(f"modelo: ECE {m.ece:.3f}, Brier {m.brier:.3f}, AUC {auc}, n={m.n}")
    if report.performance is not None:
        p = report.performance
        lines.append(
            f"desempeño: paper {p.paper:.4f} a {p.days} días; banda {p.p5:.4f}-{p.p95:.4f}"
        )
    lines += [f"sin evaluar ({k}): {v}" for k, v in report.skipped.items()]
    return lines
