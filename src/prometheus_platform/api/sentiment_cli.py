"""``pq sentimiento``: el Crypto Fear & Greed Index en el lakehouse (PQ-128).

``pq sentimiento descargar`` baja la historia completa, la guarda en bronze como una descarga más
(nunca sobrescribe) y reconstruye el silver. Es idempotente: repetirla solo añade una copia.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.fear_greed import ATTRIBUTION, FearGreedError, FearGreedSource
from prometheus_platform.data_platform.sentiment import (
    SentimentValidationError,
    build_silver,
    write_bronze,
)


def add_parser(commands: Any) -> None:
    sentiment = commands.add_parser(
        "sentimiento", help="Fear & Greed Index de alternative.me: bronze y silver (PQ-128)"
    )
    actions = sentiment.add_subparsers(dest="action", required=True)
    actions.add_parser("descargar", help="Baja la historia completa, la guarda y rehace el silver")


def run(
    args: argparse.Namespace, data_dir: Path, client_factory: Callable[[], httpx.Client]
) -> int:
    if args.action != "descargar":  # pragma: no cover - argparse ya lo impide
        return 2
    try:
        with client_factory() as client:
            request, raw = FearGreedSource(client).history()
    except FearGreedError as exc:
        print(f"no se pudo descargar: {exc}")
        return 1
    path = write_bronze(data_dir / "bronze", raw, request, SystemClock().now())
    try:
        quality = build_silver(data_dir / "bronze", data_dir / "silver")
    except SentimentValidationError as exc:
        print(f"silver no se construyó: {exc}")
        return 1
    print(f"bronze: {path.name} ({quality.downloads} descargas guardadas)")
    print(f"silver: {quality.days} días, de {quality.first} a {quality.last}")
    print(f"huecos: {quality.gaps or 'ninguno'}")
    if quality.revised:
        print(f"AVISO: valores que cambiaron entre descargas: {quality.revised}")
    print(ATTRIBUTION)
    return 0
