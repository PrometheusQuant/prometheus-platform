import hashlib
import io
import zipfile
from collections.abc import Callable

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
