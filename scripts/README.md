# scripts/: utilidades de desarrollo y mantenimiento

Tareas puntuales que **no forman parte del producto**: preparar un entorno, migrar datos una vez,
generar un informe ad hoc o automatizar algo del repositorio.

## Reglas

- La funcionalidad del sistema (ingesta, backtests, ejecución) **no** va aquí: va en
  `src/prometheus_platform/` y se expone con la CLI `pq` (`prometheus_platform.api`).
- Cada script empieza con un docstring o comentario que dice qué hace, cómo se ejecuta y si
  modifica algo.
- Se ejecutan dentro del entorno del proyecto: `uv run python scripts/<script>.py` o
  `bash scripts/<script>.sh`.
- Idempotentes cuando sea posible: ejecutarlos dos veces no debe romper nada.
- Sin secretos ni rutas absolutas de una máquina concreta.
