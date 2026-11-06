import hashlib
import importlib.util
import io
import os
import zipfile
from collections.abc import Callable, Iterator

import pytest

ZipFactory = Callable[[str, str], tuple[bytes, str]]


def zip_csv(name: str, text: str) -> tuple[bytes, str]:
    """Empaqueta un CSV como lo publica Data Vision y devuelve (bytes, sha256)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(name, text)
    payload = buffer.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


@pytest.fixture
def make_zip() -> ZipFactory:
    return zip_csv


@pytest.fixture(autouse=True)
def _isolate_from_local_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test lee el ``.env`` ni las variables ``PQ_*`` de quien los ejecuta (KE-013).

    Con un ``.env`` real (token de Telegram, claves de Binance) un test podría elegir el canal real
    o enviar una alerta. Los tests que prueban la lectura de ``.env`` la reactivan explícitamente.

    El import es diferido: el job e2e de la CI instala solo Playwright, sin el paquete, y este
    conftest se carga también allí.
    """
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    if importlib.util.find_spec("prometheus_platform") is None:
        return
    from prometheus_platform.ops.settings import Settings  # noqa: PLC0415 (ver docstring)

    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def _reset_logging_after_each_test() -> Iterator[None]:
    """Un test que llama a ``cli.main`` configura structlog sobre el stderr capturado por pytest.

    Al cerrarse ese stream, los tests siguientes fallaban con «I/O operation on closed file».
    Se restablece structlog después de cada test, en lugar de repetir el fixture en cada módulo.
    """
    yield
    if importlib.util.find_spec("structlog") is not None:
        import structlog  # noqa: PLC0415 (el job e2e no lo instala)

        structlog.reset_defaults()
