# data/: lakehouse local

Esta carpeta **no se versiona** (solo este README). Aquí viven los datos del lakehouse en la
máquina de cada desarrollador o en el servidor. Ver [ADR-0003](../docs/adr/0003-lakehouse-parquet-duckdb.md).

```text
data/
├── bronze/     # crudo, tal como llega de la fuente (Parquet), particionado por fuente/símbolo/intervalo/año/mes
├── silver/     # limpio y validado: UTC, sin duplicados, con event_time y knowledge_time
├── gold/       # features y tablas listas para modelos, backtests y BI
├── catalog/    # catálogo de DuckLake (metadatos de tablas y versiones)
└── raw/        # reservado: hoy los zips se procesan en memoria y no pasan por disco
```

## Bronze

Se llena con la CLI `pq` (PQ-20). Es idempotente: volver a ejecutar un rango solo descarga lo
que falta o lo que el proveedor republicó con otro checksum.

```bash
uv run pq ingest klines --market um --symbol BTCUSDT --interval 1h --start 2020-01
uv run pq ingest klines --market spot --symbol BTCUSDT --interval 1h --start 2020-01
uv run pq ingest funding --symbol BTCUSDT --start 2020-01
```

```text
bronze/source=binance_data_vision/dataset=klines/market=um/symbol=BTCUSDT/interval=1h/year=2024/month=01/BTCUSDT-1h-2024-01.parquet
bronze/_rejections.jsonl   # archivos rechazados (checksum inválido, CSV malformado) con motivo y fecha
```

- Todas las columnas del CSV se guardan **como texto, sin transformar**. Por ejemplo, spot usa
  microsegundos desde 2025-01 y así queda en bronze. Los tipos y las unidades se normalizan en
  silver (ver la [auditoría de Data Vision](../docs/investigacion/2026-10-23-auditoria-binance-data-vision.md)).
- Linaje en cada fila: `_source_file`, `_source_sha256`, `_source_row`, `_ingested_at`.
- Consulta rápida: `duckdb -c "select * from read_parquet('data/bronze/**/*.parquet', hive_partitioning=true) limit 5"`.

## Reglas

- Los datos se **regeneran** con el pipeline (`data_platform`), nunca se editan a mano.
- Nada de esta carpeta se sube a git: ni Parquet, ni bases DuckDB, ni CSV.
- Las rutas se configuran con `PQ_DATA_DIR` (por defecto, esta carpeta).
