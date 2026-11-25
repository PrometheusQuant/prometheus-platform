"""Spike PQ-103: ¿el Crypto Fear & Greed Index sirve como dato point-in-time?

Mide, sin credenciales:

1. La historia completa de la API pública de alternative.me (``/fng/?limit=0``): desde cuándo,
   cuántos días y qué huecos tiene.
2. Si **revisan valores pasados**. Cada copia de ``api.alternative.me/fng/`` que guardó la Wayback
   Machine trae el valor del día tal como se publicó. Se compara con la historia que da la API hoy.
3. Con qué retraso aparece el valor de un día: la hora de cada copia frente a las 00:00 UTC del día
   que muestra. Así se fija el ``knowledge_time``.

Uso:
    uv run python scripts/spike_sentimiento.py --out spike-sentimiento.json

Solo usa la biblioteca estándar. Hace una petición por copia archivada, con pausas, para no
saturar archive.org.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import itertools
import json
import statistics
import time
import urllib.request
from typing import Any

FNG = "https://api.alternative.me/fng/?limit=0&format=json"
CDX = (
    "https://web.archive.org/cdx/search/cdx?url=api.alternative.me/fng/*&output=json"
    "&filter=statuscode:200&collapse=timestamp:6&limit=400"
)
WAYBACK = "https://web.archive.org/web/{ts}id_/https://api.alternative.me/fng/"
HEADERS = {"User-Agent": "prometheus-research/0.1"}
DAY = 86_400


def _get(url: str, retries: int = 3) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)  # noqa: S310 - URL fija
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - URL fija
                raw = response.read()
            if raw[:2] == b"\x1f\x8b":  # archive.org a veces sirve el cuerpo comprimido
                raw = gzip.decompress(raw)
            return json.loads(raw)
        except (OSError, ValueError) as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).date().isoformat()


def history() -> dict[str, Any]:
    rows = _get(FNG)["data"]
    stamps = sorted(int(r["timestamp"]) for r in rows)
    gaps = [
        {"despues_de": _day(a), "dias": (b - a) // DAY}
        for a, b in itertools.pairwise(stamps)
        if b - a != DAY
    ]
    return {
        "dias": len(rows),
        "desde": _day(stamps[0]),
        "hasta": _day(stamps[-1]),
        "huecos": gaps,
        "horas_utc": sorted({dt.datetime.fromtimestamp(t, dt.UTC).hour for t in stamps}),
        "valores": {_day(int(r["timestamp"])): int(r["value"]) for r in rows},
    }


def revisions(values: dict[str, int], pause: float = 2.0) -> dict[str, Any]:
    captures = [r[1] for r in _get(CDX)[1:] if r[2].rstrip("/").endswith("/fng")]
    compared, errors = [], []
    for ts in captures:
        try:
            row = _get(WAYBACK.format(ts=ts))["data"][0]
        except RuntimeError as exc:
            errors.append({"captura": ts, "error": str(exc)[:80]})
            continue
        day = _day(int(row["timestamp"]))
        taken = dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=dt.UTC)
        lag = (taken - dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC)).total_seconds()
        compared.append(
            {
                "captura": ts,
                "dia": day,
                "archivado": int(row["value"]),
                "hoy": values.get(day),
                "horas_desde_las_00": round(lag / 3600, 2),
            }
        )
        time.sleep(pause)
    lags = [c["horas_desde_las_00"] for c in compared]
    return {
        "capturas": len(captures),
        "comparadas": len(compared),
        "distintas": [c for c in compared if c["archivado"] != c["hoy"]],
        "errores": errors,
        "rango": [min(c["dia"] for c in compared), max(c["dia"] for c in compared)]
        if compared
        else None,
        "retraso_horas": {
            "min": min(lags),
            "mediana": statistics.median(lags),
            "max": max(lags),
            "capturas_con_el_dia_anterior": sum(1 for x in lags if x >= 24),
        }
        if lags
        else None,
        "detalle": compared,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="spike-sentimiento.json")
    args = parser.parse_args()
    hist = history()
    rev = revisions(hist["valores"])
    result: dict[str, Any] = {
        "consultado": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "historia": {k: v for k, v in hist.items() if k != "valores"},
        "revisiones": rev,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(
        f"{hist['dias']} días desde {hist['desde']}; {len(hist['huecos'])} huecos. "
        f"Copias comparadas: {rev['comparadas']} de {rev['capturas']}, "
        f"distintas: {len(rev['distintas'])}."
    )


if __name__ == "__main__":
    main()
