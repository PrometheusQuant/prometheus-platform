"""Captura cada pestaña del dashboard en PNG para el informe y la presentación (PQ-41).

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

VIEWPORT = {"width": 1440, "height": 2400}  # alto para que entre la pestaña entera
TIMEOUT_MS = 30_000
SETTLE_MS = 2_000  # los gráficos de Streamlit terminan de pintarse después del DOM


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def capture(url: str, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.set_default_timeout(TIMEOUT_MS)
        page.goto(url)
        tabs = page.get_by_role("tab")
        expect(tabs.first).to_be_visible()
        for i, name in enumerate(tabs.all_inner_texts(), start=1):
            page.get_by_role("tab", name=name).click()
            page.wait_for_timeout(SETTLE_MS)
            path = out / f"{i:02d}-{slug(name)}.png"
            page.get_by_role("tabpanel").screenshot(path=path)
            written.append(path)
        browser.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--out", type=Path, default=Path("reports/storytelling/_img/dashboard"))
    args = parser.parse_args()
    for path in capture(args.url, args.out):
        print(path)


if __name__ == "__main__":
    main()
