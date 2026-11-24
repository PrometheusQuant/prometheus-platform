"""Ping a una verificación externa de disponibilidad (PQ-97), tipo *dead man's switch*.

El vigilante (``pq paper watchdog``) llama a la URL de ping en cada revisión: la URL a secas si el
runner está sano y ``<URL>/fail`` si no (convención de Healthchecks.io). Si la VM se apaga, se
queda sin red o el vigilante muere, los pings dejan de llegar y el servicio externo avisa: es la
única alerta que no depende de la propia VM. La VM no abre ningún puerto para esto.

La URL es un secreto (con ella cualquiera podría fingir que la VM vive): nunca se escribe en
logs ni en mensajes de error, solo el tipo de error o el código HTTP.
"""

from __future__ import annotations

import contextlib
import sys
from typing import TextIO

import httpx
from pydantic import SecretStr


class UptimePinger:
    def __init__(
        self, client: httpx.Client, url: SecretStr, *, fallback: TextIO | None = None
    ) -> None:
        self._client = client
        self._url = url
        self._fallback = fallback

    def ping(self, *, healthy: bool) -> bool:
        """Avisa al servicio externo. Nunca lanza: un ping perdido no tumba al vigilante."""
        base = self._url.get_secret_value().rstrip("/")
        try:
            response = self._client.get(base if healthy else f"{base}/fail")
        except httpx.HTTPError as exc:
            self._warn(f"error de red ({type(exc).__name__})")
            return False
        if response.status_code != httpx.codes.OK:
            self._warn(f"HTTP {response.status_code}")
            return False
        return True

    def _warn(self, reason: str) -> None:
        stream = self._fallback if self._fallback is not None else sys.stderr
        with contextlib.suppress(OSError, ValueError):
            stream.write(f"uptime_ping_failed: {reason}\n")
