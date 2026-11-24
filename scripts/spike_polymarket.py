"""Spike PQ-78: qué datos históricos de Polymarket se pueden obtener de sus API públicas.

Mide, sin credenciales y solo con endpoints públicos:

1. El geobloqueo desde la IP actual.
2. Cuántos mercados cerrados con volumen mínimo hay por mes (Gamma ``/markets``). Gamma no da
   un total y no acepta ``offset`` > 2.000, así que el conteo se hace por bisección dentro de cada
   mes. Un mes que llega al tope se informa como cota inferior («≥ 2.001»).
3. En una muestra aleatoria por mes (semilla fija), si el CLOB sirve el historial de precios:
   la serie diaria completa y los 15 días previos al cierre con granularidad horaria y de minuto.
4. La coherencia entre el último precio y la resolución publicada (0/1). Es un control de calidad,
   **no** una medida de calibración: el spike no mira rentabilidades por tramo de precio para no
   contaminar el pre-registro de la Estrategia de Polymarket (PQ-87).

Uso:
    uv run python scripts/spike_polymarket.py --out spike-polymarket.json

Solo usa la biblioteca estándar. No guarda precios: el JSON de salida trae conteos y la muestra
(identificadores y metadatos), no las series.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB = "https://clob.polymarket.com/prices-history"
GEOBLOCK = "https://polymarket.com/api/geoblock"
HEADERS = {"User-Agent": "prometheus-research/0.1"}
OFFSET_MAXIMO = 2000  # medido el 2026-11-24: offset=2001 responde 422
VENTANA_CLOB = 15 * 86400  # startTs/endTs admiten como mucho 15 días
HTTP_OK = 200
HTTP_RECHAZO = 422
HTTP_LIMITE = 429
REINTENTOS = 5


def pedir(url: str) -> tuple[int, Any]:
    """GET con reintentos ante 429, 5xx y cortes de red. Devuelve (estado, JSON)."""
    for intento in range(REINTENTOS):
        req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310 (URL fija https)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != HTTP_LIMITE and e.code < 500:
                return e.code, None
        except (OSError, ValueError):
            pass
        time.sleep(2 * (intento + 1))
    return 599, None


def mercado(desde: str, hasta: str, vmin: float, offset: int) -> dict[str, Any] | None:
    estado, datos = pedir(
        f"{GAMMA}?closed=true&volume_num_min={vmin}&end_date_min={desde}&end_date_max={hasta}"
        f"&limit=1&offset={offset}"
    )
    return datos[0] if estado == HTTP_OK and datos else None


def contar_mes(mes: dt.date, vmin: float) -> tuple[int, bool]:
    """Mercados cerrados que terminan en `mes`. Devuelve (conteo, llegó_al_tope)."""
    siguiente = (mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    desde, hasta = f"{mes:%Y-%m-%d}T00:00:00Z", f"{siguiente:%Y-%m-%d}T00:00:00Z"
    if mercado(desde, hasta, vmin, 0) is None:
        return 0, False
    if mercado(desde, hasta, vmin, OFFSET_MAXIMO) is not None:
        return OFFSET_MAXIMO + 1, True
    lo, hi = 0, OFFSET_MAXIMO  # lo tiene dato, hi no
    while hi - lo > 1:
        medio = (lo + hi) // 2
        if mercado(desde, hasta, vmin, medio) is not None:
            lo = medio
        else:
            hi = medio
    return lo + 1, False


def muestrear_mes(
    mes: dt.date, n: int, vmin: float, k: int, rng: random.Random
) -> list[dict[str, Any]]:
    siguiente = (mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    desde, hasta = f"{mes:%Y-%m-%d}T00:00:00Z", f"{siguiente:%Y-%m-%d}T00:00:00Z"
    offsets = sorted(rng.sample(range(n), min(k, n)))
    salida = []
    for o in offsets:
        m = mercado(desde, hasta, vmin, o)
        if m:
            salida.append({"mes": f"{mes:%Y-%m}", **{c: m.get(c) for c in CAMPOS}})
    return salida


CAMPOS = (
    "id", "conditionId", "question", "endDate", "closedTime", "volumeNum", "umaResolutionStatus",
    "outcomePrices", "enableOrderBook", "clobTokenIds", "negRisk", "feeType", "feesEnabled",
)  # fmt: skip


def instante(texto: str | None) -> int | None:
    if not texto:
        return None
    t = texto.replace(" ", "T").replace("Z", "+00:00")
    if t.endswith("+00"):
        t += ":00"
    try:
        return int(dt.datetime.fromisoformat(t).timestamp())
    except ValueError:
        return None


def historial(token: str, consulta: str) -> list[dict[str, float]]:
    estado, datos = pedir(f"{CLOB}?market={token}&{consulta}")
    return (datos or {}).get("history") or [] if estado == HTTP_OK else []


def disponibilidad(m: dict[str, Any]) -> dict[str, Any]:
    """Qué historial hay para el primer resultado del mercado."""
    tokens = json.loads(m.get("clobTokenIds") or "[]")
    cierre = instante(m.get("closedTime")) or instante(m.get("endDate"))
    final = json.loads(m.get("outcomePrices") or "[]")
    r: dict[str, Any] = {"id": m["id"], "mes": m["mes"], "con_tokens": bool(tokens)}
    if not tokens or cierre is None:
        return r
    # La serie diaria solo trae puntos a medianoche: un mercado de menos de un día no tiene
    # ninguno aunque sí tenga datos por minuto.
    r["puntos_diarios"] = len(historial(tokens[0], "interval=max&fidelity=1440"))
    minuto: list[dict[str, float]] = []
    for fid in (60, 1):
        serie = historial(
            tokens[0], f"startTs={cierre - VENTANA_CLOB}&endTs={cierre}&fidelity={fid}"
        )
        r[f"puntos_15d_fid{fid}"] = len(serie)
        minuto = serie
    claves = ("puntos_diarios", "puntos_15d_fid60", "puntos_15d_fid1")
    r["con_historial"] = any(r[k] for k in claves)
    r["binario"] = final in (["1", "0"], ["0", "1"])
    if r["binario"] and minuto:
        # Coherencia con la resolución: el último precio por minuto antes del cierre.
        ultimo = minuto[-1]
        r["ultimo_precio"] = ultimo["p"]
        r["minutos_antes_del_cierre"] = round((cierre - ultimo["t"]) / 60)
        r["ultimo_precio_coincide"] = (ultimo["p"] > 0.5) == (final[0] == "1")
    return r


def meses(desde: str, hasta: str) -> list[dt.date]:
    a = dt.date.fromisoformat(f"{desde}-01")
    b = dt.date.fromisoformat(f"{hasta}-01")
    salida = []
    while a <= b:
        salida.append(a)
        a = (a.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return salida


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--desde", default="2020-01", help="primer mes (AAAA-MM)")
    p.add_argument("--hasta", default="2026-11", help="último mes (AAAA-MM)")
    p.add_argument("--volumen-minimo", type=float, default=1000.0, help="USD")
    p.add_argument("--muestra-por-mes", type=int, default=5)
    p.add_argument("--hilos", type=int, default=8)
    p.add_argument("--semilla", type=int, default=78)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    _, geo = pedir(GEOBLOCK)
    geo = {k: v for k, v in (geo or {}).items() if k != "ip"}  # la IP no se guarda
    print("geobloqueo:", geo, flush=True)

    lista = meses(a.desde, a.hasta)
    with ThreadPoolExecutor(a.hilos) as ex:
        conteos = dict(
            zip(lista, ex.map(lambda m: contar_mes(m, a.volumen_minimo), lista), strict=True)
        )
    rng = random.Random(a.semilla)  # noqa: S311 (muestreo reproducible, no criptografía)
    plan = [(m, n) for m, (n, _) in conteos.items() if n]
    semillas = [rng.randrange(2**32) for _ in plan]
    with ThreadPoolExecutor(a.hilos) as ex:
        lotes = ex.map(
            lambda par: muestrear_mes(
                par[0][0],
                par[0][1],
                a.volumen_minimo,
                a.muestra_por_mes,
                random.Random(par[1]),  # noqa: S311
            ),
            zip(plan, semillas, strict=True),
        )
        muestra = [m for lote in lotes for m in lote]
    with ThreadPoolExecutor(a.hilos) as ex:
        resultados = list(ex.map(disponibilidad, muestra))

    por_anio: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for mes, (n, tope) in conteos.items():
        c = por_anio[f"{mes:%Y}"]
        c["mercados"] += n
        c["meses_en_tope"] += tope
    for r in resultados:
        c = por_anio[r["mes"][:4]]
        c["muestra"] += 1
        c["con_historial"] += bool(r.get("con_historial"))
        c["con_diaria"] += r.get("puntos_diarios", 0) > 0
        c["con_horaria_15d"] += r.get("puntos_15d_fid60", 0) > 0
        c["con_minuto_15d"] += r.get("puntos_15d_fid1", 0) > 0
        c["binarios"] += bool(r.get("binario"))
        c["coinciden"] += bool(r.get("ultimo_precio_coincide"))

    print(f"\nvolumen >= {a.volumen_minimo:,.0f} USD; '≥' = algún mes llegó al tope de Gamma")
    cab = "año   mercados  muestra  historial  diaria  horaria15d  minuto15d  binarios  coinciden"
    print(cab)
    for anio, c in sorted(por_anio.items()):
        cota = "≥" if c["meses_en_tope"] else " "
        print(
            f"{anio}  {cota}{c['mercados']:>7}  {c['muestra']:>7}  {c['con_historial']:>9}  "
            f"{c['con_diaria']:>6}  "
            f"{c['con_horaria_15d']:>10}  {c['con_minuto_15d']:>9}  {c['binarios']:>8}  "
            f"{c['coinciden']:>9}"
        )
    total = sum(c["mercados"] for c in por_anio.values())
    print(f"total: {total} mercados cerrados (cota inferior si hay meses en el tope)")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "consultado": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "parametros": vars(a),
                "geobloqueo": geo,
                "conteos_por_mes": {
                    f"{m:%Y-%m}": {"mercados": n, "en_tope": t} for m, (n, t) in conteos.items()
                },
                "muestra": muestra,
                "disponibilidad": resultados,
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
