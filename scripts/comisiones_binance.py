"""Lee de la cuenta real de Binance el nivel VIP, los productos y las comisiones (PQ-17).

No opera, no mueve fondos y no guarda nada. Usa una clave de API de **solo lectura**, que se pide
por teclado sin mostrarse:

    uv run python scripts/comisiones_binance.py

Antes de consultar nada comprueba los permisos de la propia clave. Si tiene cualquier permiso
además de lectura (trading, futuros, margin, retiro, transferencias), se niega a seguir: así un
error al crear la clave no se convierte en una clave peligrosa en uso.

Al terminar imprime una tabla en Markdown para pegar en `docs/compliance/binance.md` §3. Guía
completa: `docs/compliance/pasos-del-titular.md`.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

SPOT = "https://api.binance.com"
FUTUROS = "https://fapi.binance.com"
SIMBOLOS = ("BTCUSDT", "ETHUSDT")
# Los únicos permisos que puede tener la clave. Cualquier otro `enable*`/`permits*` en true,
# incluidos los que Binance añada en el futuro, hace que el script se detenga.
PERMITIDOS = frozenset({"enableReading", "enableFixReadOnly"})


class BinanceError(RuntimeError):
    """Respuesta de error de la API (código y mensaje de Binance, nunca la clave)."""


class PermisoPeligrosoError(RuntimeError):
    """La clave tiene permisos además de lectura: no se consulta nada."""

    def __init__(self, permisos: list[str]) -> None:
        super().__init__(", ".join(permisos))
        self.permisos = permisos


def firmar(params: dict[str, str | int], secreto: str) -> str:
    """Query string con la firma HMAC-SHA256 que exigen los endpoints USER_DATA."""
    query = urlencode(params)
    firma = hmac.new(secreto.encode(), query.encode(), hashlib.sha256).hexdigest()
    return f"{query}&signature={firma}"


def permisos_de_mas(restricciones: dict[str, Any]) -> list[str]:
    """Permisos activos de la clave que no son de lectura."""
    return sorted(
        clave
        for clave, valor in restricciones.items()
        if clave.startswith(("enable", "permits")) and clave not in PERMITIDOS and valor is True
    )


def porcentaje(tasa: str | Decimal) -> str:
    """'0.00100000' → '0,100 %'."""
    return f"{Decimal(tasa) * 100:.3f} %".replace(".", ",")


@dataclass
class Cliente:
    clave: str
    secreto: str
    http: httpx.Client
    desfase_ms: int = 0

    def sincronizar(self) -> None:
        """Usa la hora del servidor para que la firma no caduque (error -1021)."""
        servidor = self.http.get(f"{SPOT}/api/v3/time").json()["serverTime"]
        self.desfase_ms = int(servidor) - int(time.time() * 1000)

    def firmado(self, base: str, ruta: str, **params: str) -> Any:
        todos: dict[str, str | int] = {
            **params,
            "recvWindow": 10_000,
            "timestamp": int(time.time() * 1000) + self.desfase_ms,
        }
        respuesta = self.http.get(
            f"{base}{ruta}?{firmar(todos, self.secreto)}", headers={"X-MBX-APIKEY": self.clave}
        )
        try:
            cuerpo = respuesta.json()
        except ValueError:
            # Bloqueo de la CDN o página de error en HTML: no es la API.
            raise BinanceError(
                f"{ruta}: HTTP {respuesta.status_code}, respuesta que no es JSON"
            ) from None
        if respuesta.status_code != 200:
            codigo = cuerpo.get("code") if isinstance(cuerpo, dict) else None
            mensaje = cuerpo.get("msg") if isinstance(cuerpo, dict) else respuesta.text[:200]
            raise BinanceError(f"{ruta}: HTTP {respuesta.status_code}, código {codigo}: {mensaje}")
        return cuerpo


@dataclass
class Informe:
    fecha: str
    vip: int
    margin: bool
    futuros: bool
    spot: dict[str, dict[str, Any]] = field(default_factory=dict)
    usdm: dict[str, dict[str, str]] = field(default_factory=dict)
    usdm_error: str | None = None

    def markdown(self) -> str:
        filas = [
            "| Comprobación | Resultado | Fecha |",
            "|---|---|---|",
            f"| Nivel VIP | VIP {self.vip} | {self.fecha} |",
            f"| Margin habilitado | {'sí' if self.margin else 'no'} | {self.fecha} |",
            f"| Futuros USDⓈ-M habilitados | {'sí' if self.futuros else 'no'} | {self.fecha} |",
        ]
        for simbolo, datos in self.spot.items():
            std = datos["standardCommission"]
            desc = datos.get("discount", {})
            bnb = (
                # `discount` es el multiplicador que se paga con BNB (0.75 = se paga el 75 %),
                # no la fracción descontada (doc de Query Commission Rates).
                f"con BNB se paga el {porcentaje(desc['discount'])}: "
                f"{porcentaje(1 - Decimal(desc['discount']))} de descuento"
                if desc.get("enabledForAccount") and desc.get("enabledForSymbol")
                else "sin descuento BNB activo"
            )
            filas.append(
                f"| Comisión spot {simbolo} maker / taker | {porcentaje(std['maker'])} / "
                f"{porcentaje(std['taker'])} ({bnb}) | {self.fecha} |"
            )
        for simbolo, tasas in self.usdm.items():
            filas.append(
                f"| Comisión USDⓈ-M {simbolo} maker / taker | "
                f"{porcentaje(tasas['makerCommissionRate'])} / "
                f"{porcentaje(tasas['takerCommissionRate'])} | {self.fecha} |"
            )
        if self.usdm_error:
            filas.append(
                f"| Comisión USDⓈ-M | no legible con clave de solo lectura ({self.usdm_error}); "
                "mirarla en la web (guía, paso 3) | " + self.fecha + " |"
            )
        return "\n".join(filas)


def consultar(cliente: Cliente, simbolos: tuple[str, ...] = SIMBOLOS) -> Informe:
    """Comprueba los permisos de la clave y lee lo que pide PQ-17. Solo peticiones GET."""
    cliente.sincronizar()
    restricciones = cliente.firmado(SPOT, "/sapi/v1/account/apiRestrictions")
    if not restricciones.get("enableReading"):
        raise BinanceError("la clave no tiene permiso de lectura")
    de_mas = permisos_de_mas(restricciones)
    if de_mas:
        raise PermisoPeligrosoError(de_mas)

    cuenta = cliente.firmado(SPOT, "/sapi/v1/account/info")
    informe = Informe(
        fecha=datetime.now(UTC).date().isoformat(),
        vip=int(cuenta["vipLevel"]),
        margin=bool(cuenta["isMarginEnabled"]),
        futuros=bool(cuenta["isFutureEnabled"]),
    )
    for simbolo in simbolos:
        informe.spot[simbolo] = cliente.firmado(SPOT, "/api/v3/account/commission", symbol=simbolo)
    if informe.futuros:
        try:
            for simbolo in simbolos:
                informe.usdm[simbolo] = cliente.firmado(
                    FUTUROS, "/fapi/v1/commissionRate", symbol=simbolo
                )
        except BinanceError as error:
            # Binance puede exigir el permiso de futuros incluso para leer: no se pide nunca.
            informe.usdm = {}
            informe.usdm_error = str(error)
    return informe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simbolos", nargs="+", default=list(SIMBOLOS))
    args = parser.parse_args(argv)

    clave = os.environ.get("PQ_BINANCE_LECTURA_API_KEY") or getpass.getpass("API Key: ")
    secreto = os.environ.get("PQ_BINANCE_LECTURA_API_SECRET") or getpass.getpass("Secret Key: ")
    if not clave.strip() or not secreto.strip():
        print("Faltan la API Key o la Secret Key.", file=sys.stderr)
        return 2

    with httpx.Client(timeout=15) as http:
        try:
            informe = consultar(Cliente(clave.strip(), secreto.strip(), http), tuple(args.simbolos))
        except PermisoPeligrosoError as error:
            print(
                "ALTO: la clave tiene permisos además de lectura: "
                f"{', '.join(error.permisos)}.\n"
                "No consulté nada. Bórrala en Binance (Gestión de API) y crea otra solo con "
                "«Enable Reading».",
                file=sys.stderr,
            )
            return 3
        except (BinanceError, httpx.HTTPError) as error:
            print(f"Binance respondió con un error: {error}", file=sys.stderr)
            return 1

    print(informe.markdown())
    print(
        "\nListo. Copia la tabla de arriba (no contiene claves ni datos personales) y, cuando "
        "termines, borra la clave de solo lectura en Binance.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
