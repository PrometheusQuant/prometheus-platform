# Plan de implementación: capa silver

- **Ticket:** PQ-21 · **Fecha:** 2026-10-30 · **Spec:** [spec.md](spec.md)
- **Formato:** plantilla `plan-template.md` de Spec Kit v1.2.5, adaptada (spike PQ-30)

## Resumen

Transformar bronze (texto crudo) en dos tablas tipadas y validadas por símbolo, con un informe de
calidad. Polars por velocidad y tipado; un Parquet por tabla.

## Contexto técnico

| | |
|---|---|
| Lenguaje | Python 3.12 |
| Dependencias nuevas | `polars` (ADR-0003 ya lo contempla junto a DuckDB) |
| Almacenamiento | `data/silver/klines/market=<m>/interval=<i>/<S>.parquet`, `data/silver/funding/<S>.parquet`, `data/silver/_quality/*.json` |
| Pruebas | pytest con DataFrames sintéticos; un test por hallazgo de la auditoría |
| Restricción | ~5,7 GB de RAM: se procesa símbolo a símbolo |

## Verificación contra la "constitución"

En este repo la constitución son `CONTRIBUTING.md`, los ADR y la Definición de Terminado.

| Regla | Cumplimiento |
|---|---|
| ADR-0001: el dominio no depende de librerías | Silver vive en `data_platform/` y el dominio no importa polars (contrato de import-linter) |
| ADR-0003: point-in-time | `knowledge_time` obligatorio en cada fila (FR-003) |
| DoD, fase 2: checks de esquema y checksums | FR-006 y FR-007; los checksums ya se verifican en bronze |

## Estructura

```text
src/prometheus_platform/data_platform/silver.py      # build_klines, build_funding, checks, informe
src/prometheus_platform/api/cli.py                   # subcomando `pq silver build`
tests/unit/data_platform/test_silver.py              # un test por hallazgo y por check
tests/integration/test_silver_build.py               # bronze sintético → silver en tmp_path
```

## Tareas

1. Leer bronze por (dataset, mercado, símbolo, intervalo) con partición Hive.
2. Tipar, normalizar µs → ms, calcular `event_time` y `knowledge_time`.
3. Deduplicar, aplicar los checks y calcular los huecos.
4. Escribir Parquet e informe JSON. Añadir la CLI.
5. Tests y `make check`. Construir silver real de los 5 símbolos y anotar el resultado en el PR.

Las tareas se siguen en Jira y en commits atómicos, no en un `tasks.md` aparte (ver ADR-0008).
