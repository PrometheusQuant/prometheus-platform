"""El dashboard, tal como lo ve un usuario: abre, muestra las 4 pestañas y ninguna falla.

Funciona con o sin artefactos: cada pestaña debe mostrar datos o el aviso con el comando que
los genera (la CI lo prueba con un lakehouse vacío; en local, con los datos reales).
"""

import pytest

pytest.importorskip("playwright", reason="instala el grupo e2e: uv sync --group e2e")

from playwright.sync_api import Page, expect

TABS = {
    "¿Qué pasó? Datos y calidad": "Calidad de la capa silver",
    "¿Funciona? Carry y gates": "Carry de funding: periodo de desarrollo",
    "¿Qué predice? Modelo": "Modelo predictivo del funding (cap. 5)",
    "¿Qué riesgo hay? Simulación": "Simulación de Markov y Monte Carlo (cap. 6)",
}
TIMEOUT_MS = 30_000


@pytest.fixture
def dashboard(page: Page, base_url: str) -> Page:
    page.set_default_timeout(TIMEOUT_MS)
    page.goto(base_url)
    expect(page.get_by_role("tab").first).to_be_visible()
    return page


def test_opens_with_title_and_the_four_tabs(dashboard: Page) -> None:
    expect(dashboard).to_have_title("PrometheusQuant")
    expect(dashboard.get_by_role("heading", level=1)).to_contain_text("tablero de investigación")
    expect(dashboard.get_by_role("tab")).to_have_text(list(TABS))


@pytest.mark.parametrize(("tab", "heading"), TABS.items(), ids=range(len(TABS)))
def test_each_tab_shows_data_or_how_to_generate_it(dashboard: Page, tab: str, heading: str) -> None:
    dashboard.get_by_role("tab", name=tab).click()
    panel = dashboard.get_by_role("tabpanel")
    expect(panel.get_by_role("heading", name=heading)).to_be_visible()
    content = panel.locator('[data-testid="stDataFrame"], [data-testid="stAlert"]')
    expect(content.first).to_be_visible()
    expect(dashboard.locator('[data-testid="stException"]')).to_have_count(0)
