# data/: lakehouse local

Esta carpeta **no se versiona** (solo este README). Aquí viven los datos del lakehouse en la
máquina de cada desarrollador o en el servidor. Ver [ADR-0003](../docs/adr/0003-lakehouse-parquet-duckdb.md).

```text
data/
├── bronze/     # crudo, tal como llega de la fuente (Parquet), particionado por fuente/símbolo/intervalo/año/mes
├── silver/     # limpio y validado: UTC, sin duplicados, con event_time y knowledge_time
├── gold/       # features y tablas listas para modelos, backtests y BI
├── catalog/    # catálogo de DuckLake (metadatos de tablas y versiones)
└── raw/        # descargas temporales (zips de Data Vision) antes de pasar a bronze
```

## Reglas

- Los datos se **regeneran** con el pipeline (`data_platform`), nunca se editan a mano.
- Nada de esta carpeta se sube a git: ni Parquet, ni bases DuckDB, ni CSV.
- Las rutas se configuran con `PQ_DATA_DIR` (por defecto, esta carpeta).
