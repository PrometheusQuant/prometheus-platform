"""Evidencia de la enmienda 1 de PQ-87, §12.2: el catálogo «cerrado al ingerir» (PQ-93).

No deja fuera ningún mercado que existiera antes del corte de evaluación.

Hace dos consultas públicas a Gamma, por ``startDate`` ascendente y con volumen ≥ 1.000 USD:

1. mercados **abiertos** hoy: el más antiguo;
2. mercados **cerrados** con ``endDate`` posterior al fin del catálogo (2026-10): el más antiguo.

Si los dos empezaron después del corte (2025-06-30), ningún mercado del periodo de evaluación
falta en el catálogo. Guarda las URL y las respuestas en JSON. Solo lee; no mira precios ni pagos.

Uso:
    uv run python scripts/verificar_universo_polymarket.py --out universo.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

GAMMA = "https://gamma-api.polymarket.com/markets"
CORTE = "2025-06-30T23:59:59Z"
CAMPOS = (
    "id",
    "question",
    "startDate",
    "createdAt",
    "endDate",
    "closedTime",
    "volumeNum",
    "closed",
)


def consulta(client: httpx.Client, extra: dict[str, str]) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "volume_num_min": 1000,
        "order": "startDate",
        "ascending": "true",
        "limit": 5,
        **extra,
    }
    r = client.get(GAMMA, params=params)
    r.raise_for_status()
    filas = [{k: m.get(k) for k in CAMPOS} for m in r.json()]
    inicio = filas[0]["startDate"] if filas else None
    posterior = inicio is not None and datetime.fromisoformat(
        str(inicio).replace("Z", "+00:00")
    ) > datetime.fromisoformat(CORTE)
    return {
        "url": str(r.request.url),
        "mas_antiguos": filas,
        "inicio_mas_antiguo": inicio,
        "posterior_al_corte": posterior,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fin-catalogo", default="2026-11-01T00:00:00Z", help="endDate > fin")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with httpx.Client(timeout=60, headers={"User-Agent": "prometheus-research/0.1"}) as client:
        resultado = {
            "abiertos_hoy": consulta(client, {"closed": "false"}),
            "cerrados_endDate_lejano": consulta(
                client, {"closed": "true", "end_date_min": a.fin_catalogo}
            ),
        }
    salida = {
        "consultado": datetime.now(UTC).isoformat(timespec="seconds"),
        "corte": CORTE,
        **resultado,
    }
    a.out.write_text(json.dumps(salida, indent=1, ensure_ascii=False))
    for nombre, r in resultado.items():
        print(
            f"{nombre}: más antiguo {r['inicio_mas_antiguo']}, posterior: {r['posterior_al_corte']}"
        )
    return 0 if all(r["posterior_al_corte"] for r in resultado.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
