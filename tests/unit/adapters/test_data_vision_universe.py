"""Listado del bucket y volumen mensual de Data Vision (PQ-114), con un servidor falso."""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date

import httpx
import pytest

from prometheus_platform.adapters.binance_data_vision import BinanceDataVisionSource
from prometheus_platform.adapters.data_vision_universe import (
    USDM_KLINES_PREFIX,
    list_usdm_symbols,
    monthly_quote_volume,
)


def _page(symbols: list[str], next_marker: str | None) -> str:
    prefixes = "".join(
        f"<CommonPrefixes><Prefix>{USDM_KLINES_PREFIX}{s}/</Prefix></CommonPrefixes>"
        for s in symbols
    )
    truncated = "true" if next_marker else "false"
    marker = f"<NextMarker>{next_marker}</NextMarker>" if next_marker else ""
    return (
        f"<ListBucketResult><Prefix>{USDM_KLINES_PREFIX}</Prefix>{marker}"
        f"<IsTruncated>{truncated}</IsTruncated>{prefixes}</ListBucketResult>"
    )


def test_lista_todas_las_paginas_incluidos_deslistados() -> None:
    markers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        marker = request.url.params.get("marker", "")
        markers.append(marker)
        if marker == "":
            return httpx.Response(200, text=_page(["BTCUSDT", "AAAUSDT"], "p2"))
        return httpx.Response(200, text=_page(["DESLISTADOUSDT"], None))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert list_usdm_symbols(client, url="https://bucket") == [
        "AAAUSDT",
        "BTCUSDT",
        "DESLISTADOUSDT",
    ]
    assert markers == ["", "p2"]


def test_un_listado_truncado_sin_marcador_falla() -> None:
    page = _page(["BTCUSDT"], None).replace("false", "true")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page)))
    with pytest.raises(RuntimeError, match="NextMarker"):
        list_usdm_symbols(client, url="https://bucket")


def _zip(rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("BTCUSDT-1d-2020-12.csv", "\n".join(rows))
    return buffer.getvalue()


def test_suma_el_volumen_en_usdt_y_none_si_no_cotizaba() -> None:
    # CSV de futuros anterior a 2022, sin cabecera: quote_volume es la columna 8.
    payload = _zip(
        [
            "1606780800000,1,2,0,1,10,1606867199999,1500.5,7,5,700,0",
            "1606867200000,1,2,0,1,10,1606953599999,2499.5,7,5,700,0",
        ]
    )
    digest = hashlib.sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "NUEVOUSDT" in path:
            return httpx.Response(404)
        if path.endswith(".CHECKSUM"):
            return httpx.Response(200, text=f"{digest}  BTCUSDT-1d-2020-12.zip")
        return httpx.Response(200, content=payload)

    source = BinanceDataVisionSource(
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None
    )
    assert monthly_quote_volume(source, "BTCUSDT", date(2020, 12, 1)) == pytest.approx(4000.0)
    assert monthly_quote_volume(source, "NUEVOUSDT", date(2020, 12, 1)) is None
