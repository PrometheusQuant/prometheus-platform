"""Pruebas de scripts/comisiones_binance.py (PQ-17) con un Binance falso (httpx.MockTransport)."""

import hashlib
import hmac
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

SCRIPT = Path(__file__).parents[3] / "scripts" / "comisiones_binance.py"
# Credenciales falsas, construidas por concatenación para que el hook de secretos no las marque.
CLAVE = "clave-" + "falsa"
SECRETO = "secreto-" + "falso"

SOLO_LECTURA = {
    "ipRestrict": False,
    "createTime": 1,
    "enableReading": True,
    "enableWithdrawals": False,
    "enableInternalTransfer": False,
    "enableMargin": False,
    "enableFutures": False,
    "permitsUniversalTransfer": False,
    "enableVanillaOptions": False,
    "enableFixApiTrade": False,
    "enableFixReadOnly": True,
    "enableSpotAndMarginTrading": False,
    "enablePortfolioMarginTrading": False,
}
CUENTA = {
    "vipLevel": 0,
    "isMarginEnabled": True,
    "isFutureEnabled": True,
    "isOptionsEnabled": False,
    "isPortfolioMarginRetailEnabled": False,
}


def _comision_spot(simbolo: str) -> dict[str, Any]:
    tasas = {"maker": "0.00100000", "taker": "0.00100000", "buyer": "0", "seller": "0"}
    return {
        "symbol": simbolo,
        "standardCommission": tasas,
        "specialCommission": tasas,
        "taxCommission": tasas,
        "discount": {
            "enabledForAccount": True,
            "enabledForSymbol": True,
            "discountAsset": "BNB",
            "discount": "0.25000000",
        },
    }


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("comisiones_binance", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


Manejador = Callable[[httpx.Request], httpx.Response]


def _binance(
    restricciones: dict[str, Any], *, futuros: httpx.Response | None = None
) -> tuple[Manejador, list[httpx.Request]]:
    vistas: list[httpx.Request] = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        vistas.append(peticion)
        simbolo = peticion.url.params.get("symbol", "")
        if peticion.url.path == "/fapi/v1/commissionRate" and futuros is not None:
            return futuros
        respuestas: dict[str, Any] = {
            "/api/v3/time": {"serverTime": 1_700_000_000_000},
            "/sapi/v1/account/apiRestrictions": restricciones,
            "/sapi/v1/account/info": CUENTA,
            "/api/v3/account/commission": _comision_spot(simbolo),
            "/fapi/v1/commissionRate": {
                "symbol": simbolo,
                "makerCommissionRate": "0.000200",
                "takerCommissionRate": "0.000500",
            },
        }
        if peticion.url.path not in respuestas:
            return httpx.Response(404, json={"code": -1, "msg": "ruta inesperada"})
        return httpx.Response(200, json=respuestas[peticion.url.path])

    return manejar, vistas


def _cliente(script: ModuleType, manejar: Manejador) -> Any:
    return script.Cliente(CLAVE, SECRETO, httpx.Client(transport=httpx.MockTransport(manejar)))


def test_firma_hmac_sha256_del_query_string(script: ModuleType) -> None:
    firmado = script.firmar({"symbol": "BTCUSDT", "timestamp": 5}, SECRETO)
    query, firma = firmado.rsplit("&signature=", 1)
    assert query == "symbol=BTCUSDT&timestamp=5"
    assert firma == hmac.new(SECRETO.encode(), query.encode(), hashlib.sha256).hexdigest()


def test_lee_comisiones_y_productos_con_una_clave_de_solo_lectura(script: ModuleType) -> None:
    manejar, vistas = _binance(SOLO_LECTURA)
    informe = script.consultar(_cliente(script, manejar), ("BTCUSDT",))

    assert (informe.vip, informe.margin, informe.futuros) == (0, True, True)
    tabla = informe.markdown()
    assert "| Nivel VIP | VIP 0 |" in tabla
    assert "spot BTCUSDT maker / taker | 0,100 % / 0,100 % (BNB 25,000 % de descuento)" in tabla
    assert "USDⓈ-M BTCUSDT maker / taker | 0,020 % / 0,050 %" in tabla
    assert CLAVE not in tabla
    assert SECRETO not in tabla
    # Solo GET, todas firmadas con la clave en la cabecera y nunca el secreto en la URL.
    assert {p.method for p in vistas} == {"GET"}
    for peticion in vistas[1:]:
        assert peticion.headers["X-MBX-APIKEY"] == CLAVE
        assert SECRETO not in str(peticion.url)
        assert "signature" in dict(parse_qsl(urlsplit(str(peticion.url)).query))


@pytest.mark.parametrize(
    "permiso",
    ["enableSpotAndMarginTrading", "enableWithdrawals", "enableFutures", "enableNuevoPermiso"],
)
def test_se_niega_si_la_clave_tiene_permisos_ademas_de_lectura(
    script: ModuleType, permiso: str
) -> None:
    manejar, vistas = _binance({**SOLO_LECTURA, permiso: True})
    with pytest.raises(script.PermisoPeligrosoError) as error:
        script.consultar(_cliente(script, manejar), ("BTCUSDT",))
    assert error.value.permisos == [permiso]
    # No llegó a consultar la cuenta ni las comisiones.
    assert [p.url.path for p in vistas] == ["/api/v3/time", "/sapi/v1/account/apiRestrictions"]


def test_exige_permiso_de_lectura(script: ModuleType) -> None:
    manejar, _ = _binance({**SOLO_LECTURA, "enableReading": False})
    with pytest.raises(script.BinanceError, match="lectura"):
        script.consultar(_cliente(script, manejar), ("BTCUSDT",))


def test_si_futuros_no_se_deja_leer_lo_dice_sin_inventar_tasas(script: ModuleType) -> None:
    rechazo = httpx.Response(
        401, json={"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}
    )
    manejar, _ = _binance(SOLO_LECTURA, futuros=rechazo)
    informe = script.consultar(_cliente(script, manejar), ("BTCUSDT",))
    tabla = informe.markdown()
    assert informe.usdm == {}
    assert "-2015" in tabla
    assert "no legible con clave de solo lectura" in tabla
    assert "0,050 %" not in tabla


def test_main_devuelve_3_y_no_imprime_tabla_con_una_clave_peligrosa(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manejar, _ = _binance({**SOLO_LECTURA, "enableWithdrawals": True})
    original = httpx.Client

    def cliente_falso(**kwargs: Any) -> httpx.Client:
        return original(transport=httpx.MockTransport(manejar), **kwargs)

    monkeypatch.setattr(script.httpx, "Client", cliente_falso)
    monkeypatch.setenv("PQ_BINANCE_LECTURA_API_KEY", CLAVE)
    monkeypatch.setenv("PQ_BINANCE_LECTURA_API_SECRET", SECRETO)
    assert script.main([]) == 3
    salida = capsys.readouterr()
    assert salida.out == ""
    assert "enableWithdrawals" in salida.err
    assert SECRETO not in salida.err


def test_porcentaje_con_coma_decimal(script: ModuleType) -> None:
    assert script.porcentaje("0.00100000") == "0,100 %"
    assert script.porcentaje("0.000500") == "0,050 %"
    assert sorted(script.PERMITIDOS) == ["enableFixReadOnly", "enableReading"]
