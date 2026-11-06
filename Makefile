.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck arch test check audit docs docs-build dashboard report e2e screenshots

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## Crea el entorno e instala los hooks de git
	uv sync
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

lint: ## Lint y formato (sin modificar archivos)
	uv run ruff check .
	uv run ruff format --check .

format: ## Corrige formato e imports
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Tipado estricto con mypy
	uv run mypy

arch: ## Verifica los límites de la arquitectura hexagonal
	uv run lint-imports

test: ## Tests con cobertura
	uv run pytest

dashboard: ## Abre el dashboard de investigación en http://localhost:8501 (solo lectura)
	uv run streamlit run src/prometheus_platform/api/dashboard/app.py

e2e: ## Pruebas en navegador real contra el dashboard en Docker (Playwright)
	docker compose up -d --build --wait
	uv run --group e2e playwright install chromium
	uv run --group e2e pytest tests/e2e --no-cov --base-url http://127.0.0.1:8501

screenshots: ## Captura cada pestaña del dashboard en reports/storytelling/_img/dashboard/
	docker compose up -d --build --wait
	uv run --group e2e python scripts/capture_dashboard.py

report: ## Genera el informe ejecutivo en PDF desde los resultados (Quarto + Typst)
	@command -v quarto >/dev/null || { echo "Falta Quarto: https://quarto.org/docs/get-started/"; exit 1; }
	uv run pq report inputs --out reports/storytelling
	cd reports/storytelling && quarto render informe.qmd --to typst
	cp reports/storytelling/informe.pdf docs/academico/informe-ejecutivo.pdf
	@echo "Informe en docs/academico/informe-ejecutivo.pdf"

audit: ## Busca vulnerabilidades conocidas en las dependencias del uv.lock (pip-audit)
	uv export --frozen --no-emit-project --format requirements-txt -o .audit-requirements.txt
	uvx pip-audit==2.10.1 --requirement .audit-requirements.txt --require-hashes --disable-pip --progress-spinner off
	rm -f .audit-requirements.txt

check: lint typecheck arch test ## Todo lo que corre CI

docs: ## Sirve la documentación en http://127.0.0.1:8000 con recarga en vivo
	uv run mkdocs serve

docs-build: ## Construye el sitio en site/ (falla ante cualquier advertencia)
	uv run mkdocs build --strict
