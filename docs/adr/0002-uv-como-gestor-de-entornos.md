# ADR-0002: uv como gestor de entorno y dependencias de Python

- **Estado:** Aceptada
- **Fecha:** 2026-10-16

## Contexto y problema

El entorno debe ser aislado, reproducible y rápido en CI. Se evaluaron micromamba, pixi y uv.

## Decisión

**uv** con `pyproject.toml` y `uv.lock`. El lockfile fija versiones exactas y CI instala con
`uv sync --locked`. uv descarga su propio intérprete (no toca el Python del sistema).
TA-Lib publica wheels con la librería C incluida desde la versión 0.6.5, que era la razón principal
para usar conda.

## Consecuencias

- Positivas: un solo estándar (PEP 621), instalaciones de segundos, mismo comando en local y CI.
- Negativas: paquetes de R o binarios que solo existen en conda-forge no se instalan con uv.
- Qué la revertiría: si el análisis en R (p. ej. `rugarch`) tiene que convivir en el mismo
  entorno, se añade **pixi** para esa parte, sin cambiar el `pyproject.toml`.
