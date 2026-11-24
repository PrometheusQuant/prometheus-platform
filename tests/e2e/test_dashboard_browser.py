"""El dashboard, tal como lo ve un usuario: abre, muestra todas las páginas y ninguna falla.

Funciona con o sin artefactos: cada página debe mostrar datos o el aviso de que faltan (la CI lo
prueba con un lakehouse vacío; en local, con los datos reales). Desde PQ-127 las páginas van en el
menú lateral (``st.navigation``) y no en pestañas.
"""

import re

import pytest

pytest.importorskip("playwright", reason="instala el grupo e2e: uv sync --group e2e")

from playwright.sync_api import Page, expect

TABS = {
    "Inicio: ¿cómo va?": "¿Cómo va?",
    "¿Funciona? Carry y gates": "Carry de funding",
    "¿Qué predice? Modelo": "Modelo predictivo del funding (cap. 5)",
    "¿Qué riesgo hay? Simulación": "Simulación de Markov y Monte Carlo (cap. 6)",
    "¿Y si invierto? Simula tu inversión": "Simula tu inversión en el carry (H2)",
    "¿Qué predice hoy? Funding en vivo": "¿Habrá funding alto en la próxima liquidación?",
    "¿Cómo va en vivo? Paper trading": "Paper trading del carry H2 en vivo",
    "¿Cómo se reparte? Cartera": "Cartera multiestrategia: capital, PnL y riesgo",
    "Datos y calidad (técnico)": "Calidad de la capa silver",
}
TIMEOUT_MS = 30_000


@pytest.fixture
def dashboard(page: Page, base_url: str) -> Page:
    page.set_default_timeout(TIMEOUT_MS)
    page.goto(base_url)
    expect(page.get_by_test_id("stSidebarNavLink").first).to_be_visible()
    return page


def test_opens_with_title_and_all_the_pages(dashboard: Page) -> None:
    expect(dashboard).to_have_title(re.compile("PrometheusQuant"))
    expect(dashboard.get_by_role("heading", level=1)).to_have_text("PrometheusQuant")
    # Los enlaces llevan delante el nombre del icono Material: se busca el título dentro.
    expect(dashboard.get_by_test_id("stSidebarNavLink")).to_contain_text(list(TABS))


@pytest.mark.parametrize(("tab", "heading"), TABS.items(), ids=range(len(TABS)))
def test_each_page_shows_data_or_says_what_is_missing(
    dashboard: Page, tab: str, heading: str
) -> None:
    dashboard.get_by_test_id("stSidebarNavLink").filter(has_text=tab).click()
    main = dashboard.get_by_test_id("stMain")
    expect(main.get_by_role("heading", name=heading)).to_be_visible()
    content = main.locator(  # la portada (PQ-127) muestra cifras en texto y el glosario
        '[data-testid="stDataFrame"], [data-testid="stAlert"], [data-testid="stMetric"],'
        ' [data-testid="stExpander"]'
    )
    expect(content.first).to_be_visible()
    expect(dashboard.locator('[data-testid="stException"]')).to_have_count(0)


def test_fits_a_375_px_phone(page: Page, base_url: str) -> None:
    """PQ-127, hallazgo 11: el título no se parte y nada obliga a desplazarse en horizontal."""
    page.set_default_timeout(TIMEOUT_MS)
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(base_url)
    title = page.get_by_role("heading", level=1)
    expect(title).to_have_text("PrometheusQuant")
    expect(title).to_have_css("font-size", "32px")  # la regla de pantallas estrechas ya se aplicó
    line = title.evaluate("e => parseFloat(getComputedStyle(e).lineHeight)")
    text = title.locator("[data-heading-text]")  # el h1 suma padding: se mide el texto
    box = text.bounding_box()
    assert box is not None
    assert box["height"] < 1.6 * line  # una sola línea
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)


def test_fair_mode_shows_the_guided_tour_with_big_type(page: Page, base_url: str) -> None:
    """PQ-102: ``?modo=feria`` abre el recorrido de 7 pasos y agranda la tipografía."""
    page.set_default_timeout(TIMEOUT_MS)
    page.goto(f"{base_url}/?modo=feria")
    sidebar = page.get_by_test_id("stSidebar")
    expect(sidebar).to_contain_text("paso 1 de 7")
    sidebar.get_by_role("button", name="Siguiente").click()  # el nombre incluye el icono
    expect(sidebar).to_contain_text("paso 2 de 7")
    expect(sidebar).to_contain_text("Datos y calidad (técnico)")
    title = page.get_by_role("heading", level=1)
    size = title.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
    assert size >= 60  # 3rem sobre 22 px; el modo normal ronda los 44 px
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
