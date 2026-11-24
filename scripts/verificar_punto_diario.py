"""Comprueba que el punto diario del CLOB es el precio de ese instante, no uno posterior (PQ-93).

Enmienda 1 del pre-registro PQ-87, §4: en vez de comprobarlo en todo el silver (exigiría la serie
por minuto de todos los tokens), se comprueba en una muestra aleatoria estratificada por mes, con
semilla fija. Para cada punto diario elegido se pide la serie por minuto alrededor de ese instante y
se compara con el último precio por minuto **anterior o igual** a él.

Solo lee: el catálogo del bronze de PQ-92 y la API pública. No mira resoluciones ni retornos.

Uso:
    uv run python scripts/verificar_punto_diario.py --por-mes 5 --out verificacion.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl

CLOB = "https://clob.polymarket.com/prices-history"
VENTANA = 30 * 60  # segundos a cada lado del punto diario
TOLERANCIA = 0.001  # diferencias menores son redondeo


def serie(client: httpx.Client, token: str, params: dict[str, str | int]) -> list[dict[str, float]]:
    r = client.get(CLOB, params={"market": token, **params})
    r.raise_for_status()
    return list(r.json().get("history") or [])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--desde", default="2023-01")
    p.add_argument("--hasta", default="2025-06")
    p.add_argument("--por-mes", type=int, default=5, help="mercados por mes de cierre")
    p.add_argument("--semilla", type=int, default=93)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    files = sorted(
        (a.data_dir / "bronze/source=polymarket/dataset=markets").glob("year=*/month=*/*.parquet")
    )
    catalog = pl.concat([pl.read_parquet(f).with_columns(pl.lit(f.parent.name[-2:]).alias("m"),
                         pl.lit(f.parent.parent.name[-4:]).alias("y")) for f in files])  # fmt: skip
    catalog = catalog.with_columns((pl.col("y") + "-" + pl.col("m")).alias("mes")).filter(
        (pl.col("mes") >= a.desde) & (pl.col("mes") <= a.hasta)
    )
    rng = random.Random(a.semilla)  # noqa: S311 - muestreo reproducible, no criptografía
    resultados = []
    with httpx.Client(timeout=60, headers={"User-Agent": "prometheus-research/0.1"}) as client:
        for (mes,), group in sorted(catalog.group_by("mes"), key=lambda g: str(g[0][0])):
            filas = group["raw"].to_list()
            for raw in rng.sample(filas, min(a.por_mes, len(filas))):
                tokens = json.loads(json.loads(raw).get("clobTokenIds") or "[]")
                if not tokens:
                    continue
                diaria = serie(client, tokens[0], {"interval": "max", "fidelity": 1440})
                if not diaria:
                    continue
                punto = rng.choice(diaria)
                t = int(punto["t"])
                minuto = serie(
                    client, tokens[0], {"startTs": t - VENTANA, "endTs": t + VENTANA, "fidelity": 1}
                )
                previos = [x for x in minuto if int(x["t"]) <= t]
                ref = previos[-1] if previos else None
                resultados.append(
                    {
                        "mes": mes,
                        "t": datetime.fromtimestamp(t, UTC).isoformat(),
                        "diario": punto["p"],
                        "minuto_previo": ref["p"] if ref else None,
                        "segundos_antes": t - int(ref["t"]) if ref else None,
                        "coincide": ref is not None and abs(ref["p"] - punto["p"]) <= TOLERANCIA,
                    }
                )
    comparados = [r for r in resultados if r["minuto_previo"] is not None]
    fallos = [r for r in comparados if not r["coincide"]]
    resumen = {
        "consultado": datetime.now(UTC).isoformat(timespec="seconds"),
        "parametros": {k: str(v) for k, v in vars(a).items()},
        "puntos": len(resultados),
        "comparados": len(comparados),
        "sin_minuto_previo": len(resultados) - len(comparados),
        "no_coinciden": len(fallos),
        "fallos": fallos,
    }
    a.out.write_text(json.dumps({"resumen": resumen, "puntos": resultados}, indent=1))
    print(json.dumps({k: v for k, v in resumen.items() if k != "fallos"}, indent=1))
    for f in fallos:
        print("NO COINCIDE", f)
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
