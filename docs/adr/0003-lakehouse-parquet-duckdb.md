# ADR-0003: Lakehouse medallion con Parquet y DuckDB

- **Estado:** Aceptada
- **Fecha:** 2026-10-16

## Contexto y problema

Se necesitan años de velas, funding y métricas de Binance para investigar, con datos
*point-in-time* para evitar el sesgo de anticipación, sin servidores de base de datos pesados.

## Decisión

- Archivos **Parquet** en capas **bronze** (crudo), **silver** (limpio y validado) y **gold**
  (features listas para modelos), catalogados con **DuckLake** y consultados con **DuckDB** o Polars.
- Cada registro guarda `event_time` y `knowledge_time`; las features se unen con *as-of joins*
  sobre `knowledge_time`.
- **PostgreSQL** para el journal de eventos y el backend de MLflow/Optuna.
- **Dagster** orquesta los assets batch (nunca el proceso en vivo).

## Consecuencias

- Positivas: cero servidores en fase 0; formato abierto; consultas SQL rápidas en una laptop.
- Negativas: DuckDB es de un solo escritor; no sirve para la captura en tiempo real de varios procesos.
- Qué la revertiría: captura de ticks en vivo de varios procesos → QuestDB o TimescaleDB.
