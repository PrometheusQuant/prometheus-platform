"""Captura cada página del dashboard en PNG para el informe y la presentación (PQ-41).

No modifica nada: abre el dashboard en un Chromium sin ventana y guarda una imagen por pestaña.

    docker compose up -d --build        # o: make dashboard
    uv run --group e2e python scripts/capture_dashboard.py \
        --url http://127.0.0.1:8501 --out reports/storytelling/_img/dashboard

Requiere el navegador una vez: ``uv run --group e2e playwright install chromium``.
"""

import argparse
import re
import unicodedata
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

VIEWPORT = {"width": 1440, "height": 2400}  # alto para que entre la página entera
MOBILE = {"width": 375, "height": 812}  # un teléfono pequeño (PQ-127)
TIMEOUT_MS = 180_000  # la primera carga entrena los modelos del simulador y la predicción
SETTLE_MS = 5_000  # los gráficos se pintan después del DOM (el de paper tiene miles de puntos)


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def capture(url: str, out: Path, *, mobile: bool = False, only_first: bool = False) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        viewport = MOBILE if mobile else VIEWPORT
        page = browser.new_page(viewport=viewport, device_scale_factor=2)
        page.set_default_timeout(TIMEOUT_MS)
        page.goto(url)
        links = page.get_by_test_id("stSidebarNavLink")
        expect(links.first).to_be_attached(timeout=TIMEOUT_MS)
        # Cada enlace del menú (PQ-127) tiene el título de su página y una ruta propia.
        targets = [
            (link.get_attribute("href") or "", link.inner_text().split("\n")[-1].strip())
            for link in links.all()
        ]
        for i, (href, name) in enumerate(targets, start=1):
            page.goto(href if href.startswith("http") else f"{url.rstrip('/')}/{href.lstrip('/')}")
            expect(page.get_by_test_id("stMain")).to_be_visible(timeout=TIMEOUT_MS)
            page.wait_for_timeout(SETTLE_MS)
            path = out / f"{'movil-' if mobile else ''}{i:02d}-{slug(name)}.png"
            target = page if mobile else page.get_by_test_id("stMainBlockContainer")
            target.screenshot(path=path, **({"full_page": True} if mobile else {}))
            written.append(path)
            if only_first:
                break
        browser.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--out", type=Path, default=Path("reports/storytelling/_img/dashboard"))
    parser.add_argument("--movil", action="store_true", help="a 375 px de ancho, página completa")
    parser.add_argument("--solo-inicio", action="store_true", help="solo la primera página")
    args = parser.parse_args()
    for path in capture(args.url, args.out, mobile=args.movil, only_first=args.solo_inicio):
        print(path)


if __name__ == "__main__":
    main()
