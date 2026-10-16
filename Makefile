.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck arch test check

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

check: lint typecheck arch test ## Todo lo que corre CI
