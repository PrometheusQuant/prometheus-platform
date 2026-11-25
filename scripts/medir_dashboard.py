"""Mide cuánto tarda el dashboard con la API de agente de Streamlit (PQ-127).

Mide la primera carga, una segunda sesión con la caché caliente, la visita a cada página y un
cambio en el simulador. Así se compara el tablero de pestañas (antes) con el de páginas (después).

Uso, con el dashboard levantado con ``--server.enableAgentApi=true``:

    uv run python scripts/medir_dashboard.py --url http://127.0.0.1:8503 > tiempos.json

Si el servidor está recién arrancado, la primera carga se mide con la caché fría.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

import httpx

INTERACT = "/_stcore/agent/interact"
CAPITAL = "Capital (USD)"
REPETITIONS = 3


def _call(client: httpx.Client, body: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Una interacción completa. Si la API corta la espera, se vuelve a pedir la misma sesión."""
    start = time.perf_counter()
    data = client.post(INTERACT, json=body).json()
    while "error" in data and data["error"].get("code") == "wait_timed_out":
        data = client.post(INTERACT, json={"session_id": data["session_id"]}).json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return time.perf_counter() - start, data


def _capital_key(snapshot: dict[str, Any]) -> str | None:
    return next((a["key"] for a in snapshot["actions"] if a.get("label") == CAPITAL), None)


def _simulator_reruns(client: httpx.Client, snapshot: dict[str, Any]) -> list[float]:
    key = _capital_key(snapshot)
    if key is None:
        return []
    session, times = snapshot["session_id"], []
    for value in (2_000, 3_000, 4_000)[:REPETITIONS]:
        elapsed, snapshot = _call(client, {"session_id": session, "widget_state": {key: value}})
        times.append(elapsed)
    return times


def measure(url: str) -> dict[str, Any]:
    with httpx.Client(base_url=url, timeout=600) as client:
        cold, first = _call(client, {})
        warm, second = _call(client, {})
        pages = {p["url_path"]: p for p in first.get("pages", [])}
        visits: dict[str, float] = {}
        simulator: list[float] = _simulator_reruns(client, second)
        for path in pages:
            elapsed, snapshot = _call(client, {"session_id": second["session_id"], "page": path})
            visits[path or "(inicio)"] = round(elapsed, 2)
            if not simulator:
                simulator = _simulator_reruns(client, snapshot)
    return {
        "primera_carga_fria_s": round(cold, 2),
        "primera_carga_caliente_s": round(warm, 2),
        "paginas_s": visits,
        "rerun_simulador_s": [round(t, 2) for t in simulator],
        "rerun_simulador_mediana_s": round(statistics.median(simulator), 2) if simulator else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    print(json.dumps(measure(parser.parse_args().url), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
