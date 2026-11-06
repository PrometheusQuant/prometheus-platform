"""Pruebas de punta a punta del dashboard en un navegador real (PQ-41).

Solo corren con el grupo ``e2e`` instalado y una URL explícita, por ejemplo:

    uv run --group e2e pytest tests/e2e --no-cov --base-url http://127.0.0.1:8501

Sin ``--base-url`` se omiten, así que ``make test`` y la CI de calidad no las ejecutan.
"""

import pytest


@pytest.fixture(autouse=True)
def _requires_base_url(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("base_url", default=None):
        pytest.skip("pruebas e2e: pasa --base-url con el dashboard levantado")
