# ADR-0010: Dagster orquesta el lakehouse batch; research queda fuera de su alcance

- **Estado:** Aceptada
- **Fecha:** 2026-11-06
- **Ticket:** PQ-22

## Contexto y problema

[ADR-0003](0003-lakehouse-parquet-duckdb.md) ya decidió que Dagster orquesta los assets batch y nunca
el proceso en vivo. Faltaba concretarlo, con tres restricciones:

- **Máquina.** La laptop tiene 5,7 GB de RAM, y la VM de Oracle Always Free 2 OCPU y 12 GB.
- **Fijaciones.** Hay que respetar las versiones que ya usamos: pyarrow ≥ 26, pydantic ≥ 2.14 y Python 3.12.
- **Protocolo.** Cada ejecución de una evaluación de research suma ensayos a N (pre-registro §10).
  Un schedule o un clic que la relance contamina el Deflated Sharpe.

## Opciones consideradas

1. **Dagster 1.13** con assets, asset checks y schedules (lo previsto en ADR-0003).
2. **Seguir solo con la CLI `pq` y cron**: sin linaje, sin checks visibles y sin interfaz.
3. **Prefect o Airflow**: orientados a tareas y no a assets. Airflow es demasiado pesado para la VM.

## Decisión

Dagster 1.13 (verificado el 2026-11-06), con estas reglas:

- **Dependencias.**
  - Va en el grupo `orquestacion` de uv, que es un grupo por defecto para que la CI y mypy lo vean.
  - No está en `[project.dependencies]`: la librería no depende de él, y la imagen Docker no lo instala.
  - La resolución no cambió ninguna versión existente.
  - Un contrato de import-linter impide que cualquier módulo fuera de `api.orquestacion` lo importe.
    Así, el trading en vivo no puede depender de Dagster.
- **Assets.**
  - `bronze` se particiona por mes × símbolo, como publica Data Vision.
  - `silver` y `gold` se reconstruyen enteros: los checks de duplicados, huecos y outliers necesitan
    la historia completa, y tardan unos 8 s con los datos reales.
- **Research como assets externos.** Aparecen en el linaje, pero **no se pueden materializar desde
  Dagster** y ningún schedule los toca: cada ejecución suma a N. Se corren a mano con `pq research`.
- **Asset checks bloqueantes.**
  - Tablas y claves de silver.
  - Holdout cerrado en gold.
  - Integridad de gold.

  Si fallan, gold no se reconstruye en esa ejecución. Los huecos de silver dan una advertencia y no bloquean: se informan y no se imputan (KE-007).
- **Schedules diarios detenidos por defecto.** Los activa el titular desde la interfaz.
- **DuckLake se difiere.** `gold.duckdb` (PQ-46) ya da SQL sobre gold. DuckLake necesita descargar
  su extensión en tiempo de ejecución y no aporta mientras haya un solo proceso escribiendo.

## Consecuencias

- **Positivas:**
  - Linaje visible de bronze a gold, con research en el medio.
  - Resultados de calidad en la interfaz.
  - Ingesta diaria sin intervención cuando se active.
- **Negativas y riesgos:**
  - La interfaz consume unos 790 MB en reposo (servidor web, daemon y servidor de código). En la laptop se abre solo cuando se usa.
  - Agrega unos 105 MB al entorno de desarrollo.
  - Dagster inspecciona las anotaciones en tiempo de ejecución, así que el módulo no usa `from __future__ import annotations`.
- **Qué la revertiría:**
  - Que Dagster deje de convivir con nuestras fijaciones.
  - Que la VM no tenga memoria para la interfaz junto al runner de paper trading. En ese caso se ejecutan los jobs con `dagster job execute` desde cron, sin la interfaz.
