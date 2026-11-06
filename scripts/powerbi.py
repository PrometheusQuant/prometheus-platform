"""Apoyo al dashboard de Power BI (PQ-47): consultas de Power Query y valores de control.

No modifica datos. Dos usos:

    # Regenera las consultas M (una por tabla gold) desde las declaraciones de gold.py
    uv run python scripts/powerbi.py consultas --out reports/powerbi/consultas.pq

    # Imprime los valores que el .pbix debe mostrar, calculados con las mismas fórmulas que research
    uv run python scripts/powerbi.py control --gold data/gold

Las consultas usan un parámetro de Power Query llamado ``Carpeta`` con la ruta de
``data/gold/export`` en Windows, y tipan cada columna con la configuración regional ``en-US``
(punto decimal), sin depender de la configuración del equipo.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from prometheus_platform.data_platform.gold import TABLES, GoldTable
from prometheus_platform.research.validation import performance

M_TYPES = {
    pl.String: "type text",
    pl.Float64: "type number",
    pl.Int64: "Int64.Type",
    pl.Boolean: "type logical",
    pl.Date: "type date",
}
CONTROL_CONFIGS = ("H2/k9-theta20", "H1/k3-theta20")
SCENARIO = "sin quiebra del exchange"


def m_query(table: GoldTable) -> str:
    types = ", ".join(f'{{"{c.name}", {M_TYPES[type(c.dtype)]}}}' for c in table.columns)
    return "\n".join(
        [
            f"// ---- {table.name}: {table.description}",
            f"// Consulta en blanco > Editor avanzado; nombre de la consulta: {table.name}",
            "let",
            f'    Origen = Csv.Document(File.Contents(Carpeta & "{table.name}.csv"),',
            '        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
            "    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),",
            "    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.",
            "    SinVacios = Table.TransformColumns(",
            '        Encabezados, {}, each if _ = "" then null else _),',
            f'    Tipado = Table.TransformColumnTypes(SinVacios, {{{types}}}, "en-US")',
            "in",
            "    Tipado",
            "",
        ]
    )


def render_queries() -> str:
    header = [
        "// Consultas de Power Query (M) para el modelo gold. Generado por scripts/powerbi.py.",
        "// No editar a mano: regenerar con `uv run python scripts/powerbi.py consultas`.",
        "// Requiere un parámetro de texto «Carpeta» que termine en barra invertida, p. ej.",
        '// "C:\\PrometheusQuant\\gold\\export\\"',
        "",
    ]
    return "\n".join(header + [m_query(t) for t in TABLES])


def control_values(gold: Path) -> list[tuple[str, str]]:
    """Valores que deben mostrar las medidas de medidas.dax, con las fórmulas de research."""
    rows: list[tuple[str, str]] = [
        (
            f"Filas de {t.name}",
            f"{pl.scan_parquet(gold / f'{t.name}.parquet').select(pl.len()).collect().item():,}",
        )
        for t in TABLES
    ]
    returns = pl.read_parquet(gold / "fact_retorno_estrategia.parquet")
    desempeno = pl.read_parquet(gold / "fact_desempeno.parquet")
    for config in CONTROL_CONFIGS:
        series = returns.filter(pl.col("configuracion_id") == config).sort("fecha")
        if series.height < 2:  # performance necesita al menos 2 días
            continue
        perf = performance(series["retorno"].to_numpy().astype(np.float64))
        rows += [
            (f"{config}: días (fact_retorno_estrategia)", f"{perf.days:,}"),
            (f"{config}: Retorno acumulado", f"{series['capital'][-1] - 1:.4%}"),
            (f"{config}: CAGR", f"{perf.cagr:.4%}"),
            (f"{config}: Sharpe anualizado", f"{perf.sharpe:.4f}"),
            (f"{config}: Volatilidad anual", f"{series['retorno'].std() * 365**0.5:.4%}"),
            (f"{config}: Máximo drawdown", f"{perf.max_drawdown:.4%}"),
            (
                f"{config}: % días con exposición (retorno ≠ 0)",
                f"{(series['retorno'] != 0).mean():.2%}",
            ),
        ]
        research = desempeno.filter(pl.col("configuracion_id") == config)
        if research.height:
            r = research.row(0, named=True)
            rows.append(
                (
                    f"{config}: research (fact_desempeno, {r['dias']} días)",
                    f"Sharpe {r['sharpe']:.4f} · CAGR {r['cagr']:.4%}"
                    f" · máx. DD {r['max_drawdown']:.4%}",
                )
            )
    funding = pl.read_parquet(gold / "fact_funding_diario.parquet")
    for symbol, mean in (
        funding.group_by("simbolo")
        .agg(pl.col("funding_anualizado_medio").mean())
        .sort("simbolo")
        .iter_rows()
    ):
        rows.append((f"Funding anualizado medio {symbol}", f"{mean:.2%}"))
    gates = pl.read_parquet(gold / "fact_gates.parquet")
    for hyp, passed, total in (
        gates.group_by("hipotesis")
        .agg(pl.col("pasa").sum(), pl.len())
        .sort("hipotesis")
        .iter_rows()
    ):
        rows.append((f"Gates aprobados {hyp}", f"{passed} de {total}"))
    scenario = pl.read_parquet(gold / "fact_escenarios.parquet").filter(
        pl.col("escenario") == SCENARIO
    )
    if scenario.height:
        s = scenario.row(0, named=True)
        rows += [
            (f"P(pérdida) «{SCENARIO}»", f"{s['prob_perdida']:.2%}"),
            (f"CVaR 95 % «{SCENARIO}»", f"{s['cvar95']:.2%}"),
        ]
    model = pl.read_parquet(gold / "fact_metricas_modelo.parquet").drop_nulls("auc")
    if model.height:
        best = model.sort("auc", descending=True).row(0, named=True)
        rows.append(
            ("Mejor AUC (fact_metricas_modelo)", f"{best['auc']:.4f} ({best['modelo_id']})")
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    queries = sub.add_parser("consultas", help="Escribe las consultas M de las tablas gold")
    queries.add_argument("--out", type=Path, default=Path("reports/powerbi/consultas.pq"))
    control = sub.add_parser("control", help="Imprime los valores de control en Markdown")
    control.add_argument("--gold", type=Path, default=Path("data/gold"))
    args = parser.parse_args()
    if args.action == "consultas":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render_queries(), encoding="utf-8")
        print(f"consultas en {args.out}")
        return
    print("| Medida | Valor esperado |\n|---|---|")
    for name, value in control_values(args.gold):
        print(f"| {name} | {value} |")


if __name__ == "__main__":
    main()
