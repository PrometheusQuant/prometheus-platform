"""Cliente del Crypto Fear & Greed Index de alternative.me (PQ-128).

API pública sin clave: ``https://api.alternative.me/fng/?limit=0&format=json`` devuelve toda la
historia diaria desde el 2018-02-01. Licencia: uso libre, también comercial, **con la atribución
junto al dato** (``ATTRIBUTION``). El spike de PQ-103 comprobó que los valores publicados no se
revisan y que el del día D aparece a las 00:00 UTC de D.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

FNG_URL = "https://api.alternative.me/fng/"
ATTRIBUTION = "Fuente: Crypto Fear & Greed Index de alternative.me"
_HTTP_OK = 200
_RETRY_STATUS = {429, 500, 502, 503, 504}


class FearGreedError(RuntimeError):
    """La API no respondió con un JSON válido tras reintentar."""


class FearGreedSource:
    def __init__(
        self,
        client: httpx.Client,
        *,
        url: str = FNG_URL,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._url = url
        self._retries = retries
        self._sleep = sleep

    def history(self) -> tuple[str, str]:
        """Toda la historia. Devuelve la URL pedida y el cuerpo crudo, sin interpretar."""
        last = ""
        for attempt in range(self._retries + 1):
            try:
                response = self._client.get(self._url, params={"limit": 0, "format": "json"})
            except httpx.TransportError as exc:
                last = type(exc).__name__
            else:
                if response.status_code == _HTTP_OK:
                    return str(response.request.url), response.text
                if response.status_code not in _RETRY_STATUS:
                    raise FearGreedError(f"{self._url}: HTTP {response.status_code}")
                last = f"HTTP {response.status_code}"
            if attempt < self._retries:
                self._sleep(2.0 * (attempt + 1))
        raise FearGreedError(f"{self._url}: sin respuesta válida tras reintentar ({last})")
