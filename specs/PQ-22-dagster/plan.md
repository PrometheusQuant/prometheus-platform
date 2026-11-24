# Plan de implementación: orquestación con Dagster

- **Ticket:** PQ-22 · **Fecha:** 2026-11-06 · **Spec:** [spec.md](spec.md)

## Verificación previa (hecha antes de programar)

| Pregunta | Resultado |
|---|---|
| ¿Dagster convive con nuestras fijaciones? | Sí: 1.13.29 resuelve con pyarrow 26.0.0, pydantic 2.14.1 y Python 3.12 sin cambiar ninguna versión existente del `uv.lock` |
| ¿Cuánto pesa? | ~105 MB en el entorno; la imagen Docker no cambia (`--no-default-groups`) |
| ¿Cabe en la máquina? | La interfaz (`dagster dev`) usa ~790 MB en reposo, medido con el lakehouse real |

## Contexto técnico

| | |
|---|---|
| Ubicación | `api/orquestacion/`: es un punto de entrada, como la CLI y el dashboard |
| Reutilización | Los assets llaman a las funciones puras existentes: `ingest`, `silver.build_symbol` (nueva, extraída de la CLI) y `gold.build_gold` |
| Contrato nuevo | import-linter: solo `api.orquestacion` importa `dagster` |
| Recurso | `Lakehouse(data_dir)`, por defecto `PQ_DATA_DIR`, igual que la CLI |

## Verificación contra la «constitución»

| Regla | Cumplimiento |
|---|---|
| ADR-0001 (capas) | La orquestación vive en `api` y solo depende hacia abajo |
| ADR-0003 (Dagster solo batch) | Contrato de import-linter que lo hace verificable |
| Pre-registro §10 (N) | Research como assets externos, no materializables |
| Holdout cerrado | Check bloqueante sobre gold |

## Riesgos

| Riesgo | Mitigación |
|---|---|
| La interfaz compite por RAM con el runner en la VM | Ejecutar los jobs con `dagster job execute` desde cron, sin interfaz (ADR-0010) |
| Dagster cambia su API entre versiones | Tests de las definiciones y `Definitions.validate_loadable` en la CI |
