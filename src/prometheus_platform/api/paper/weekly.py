"""Informe semanal del paper trading en PDF (PQ-85).

Arma las entradas de ``semana.qmd`` (cifras en ``_semana.yml``, tablas en ``_tablas/`` y la curva
de equity en ``_img/``) a partir de ``WeeklySummary``, la misma función que alimenta el resumen
semanal de Telegram: el PDF y el mensaje nunca dan cifras distintas. Quarto lo convierte en PDF
con Typst, igual que el informe ejecutivo (PQ-39).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from matplotlib.figure import Figure

from prometheus_platform.api.paper.report import WeeklySummary

TEMPLATE = Path(__file__).with_name("semana.qmd")
QUARTO_TIMEOUT = 300  # segundos; el informe tarda unos 10 s


class WeeklyReportError(RuntimeError):
    """No se pudo generar el PDF (falta Quarto o falló el render)."""


def pdf_name(summary: WeeklySummary) -> str:
    return f"informe-paper-{summary.week}.pdf"


def build_inputs(summary: WeeklySummary, out: Path, broker: str | None) -> None:
    """Escribe las entradas del informe y copia la plantilla en ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    details = summary.details()
    values = {
        "semana": summary.week,
        "desde": summary.start.isoformat(),
        "hasta": summary.end.isoformat(),
        "broker": broker or "n/d",
        "ordenes": details["órdenes ejecutadas"],
        "funding": details["funding neto"],
        "comisiones": details["comisiones"],
        "slippage": details["slippage"],
        "equity_inicio": f"{summary.equity_start:.2f} USD" if summary.equity_start else "n/d",
        "equity_cierre": details["equity al cierre"],
        "variacion": details["variación semanal"],
        "caida_maxima": details["caída máxima en la semana"],
        "violaciones": details["violaciones de riesgo"],
        "kill_switch": details["kill-switch activado"],
        "tiene_curva": len(summary.curve) > 1,
    }
    # JSON es YAML válido (como en el informe ejecutivo): no hace falta otra dependencia.
    (out / "_semana.yml").write_text(
        json.dumps({"s": values}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tables = out / "_tablas"
    tables.mkdir(exist_ok=True)
    (tables / "estrategias.md").write_text(_strategies_table(summary), encoding="utf-8")
    image = out / "_img" / "equity.png"
    image.unlink(missing_ok=True)
    if values["tiene_curva"]:
        _equity_figure(summary, image)
    shutil.copyfile(TEMPLATE, out / TEMPLATE.name)


def _strategies_table(summary: WeeklySummary) -> str:
    if not summary.strategies:
        return "*Sin datos: el diario no tiene operaciones hasta el cierre de esta semana.*\n"
    lines = [
        "| Estrategia | Exchange | PnL de la semana (USD) | Funding (USD) | Costes (USD) "
        "| Exposición al cierre (USD) |",
        "|---|---|--:|--:|--:|--:|",
    ]
    lines += [
        f"| {r.strategy} | {r.exchange} | {r.pnl:+.2f} | {r.funding:+.4f} | {r.costs:.4f} "
        f"| {r.exposure:.2f} |"
        for r in summary.strategies
    ]
    return "\n".join(lines) + "\n"


def _equity_figure(summary: WeeklySummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(7.0, 2.6), dpi=150)
    axes = figure.add_subplot()
    # días desde 1970-01-01 UTC: la época por defecto de las fechas de matplotlib (date2num)
    times = [t.timestamp() / 86_400 for t, _ in summary.curve]
    axes.plot(times, [float(v) for _, v in summary.curve], color="#1f5fa8")
    axes.xaxis_date()
    axes.set_ylabel("Equity (USD)")
    axes.grid(alpha=0.3)
    axes.spines[["top", "right"]].set_visible(False)
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(path)


def render_pdf(summary: WeeklySummary, out: Path) -> Path:
    """Convierte ``semana.qmd`` en PDF con Quarto. Lanza ``WeeklyReportError`` si no puede."""
    if shutil.which("quarto") is None:
        raise WeeklyReportError("falta Quarto: https://quarto.org/docs/get-started/")
    result = subprocess.run(  # noqa: S603  # argumentos fijos, sin shell
        ["quarto", "render", TEMPLATE.name, "--to", "typst"],  # noqa: S607
        cwd=out,
        capture_output=True,
        text=True,
        timeout=QUARTO_TIMEOUT,
        check=False,
    )
    rendered = out / TEMPLATE.with_suffix(".pdf").name
    if result.returncode != 0 or not rendered.exists():
        tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise WeeklyReportError(f"Quarto falló ({result.returncode}): {' | '.join(tail)}")
    return rendered.replace(out / pdf_name(summary))
