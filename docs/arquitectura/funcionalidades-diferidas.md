# Funcionalidades diferidas

Lo que decidimos **no hacer todavía**, y por qué. Nada se pierde: cada entrada dice qué la
reactivaría. Las decisiones grandes tienen su ADR; aquí está la lista completa.

| Funcionalidad | Estado | Por qué no ahora | Qué la reactivaría |
|---|---|---|---|
| Microservicios, Kubernetes | Descartado por ahora | Somos dos personas con una laptop de 5,7 GB; añadiría red y operación sin beneficio ([ADR-0001](../adr/0001-monolito-modular-hexagonal.md)) | Un módulo que necesite escalar o desplegarse aparte (p. ej. un nodo de ejecución cerca del exchange) |
| Mensajería (Kafka, NATS JetStream) | Diferido a la fase 2 de `deploy/` | Con un solo proceso no hay a quién enviar mensajes | Separar el proceso live y el de research en dos nodos |
| Base de series temporales (TimescaleDB, QuestDB) | Diferido | Parquet y DuckDB alcanzan para el research batch ([ADR-0003](../adr/0003-lakehouse-parquet-duckdb.md)) | Captura de ticks en vivo desde varios procesos |
| PySpark y Delta Lake | Descartado | En OmniVoC causaron errores de compatibilidad Scala y de falta de memoria con 5,7 GB; Polars y DuckDB cubren nuestro volumen | Datos que no quepan en una máquina |
| Orquestación con Dagster (PQ-22) | Sprint 3 | La CLI `pq` cubre hoy la ingesta y el research | Ingesta diaria automática del mes en curso |
| Ejecución con NautilusTrader | Propuesta ([ADR-0006](../adr/0006-nautilustrader-para-ejecucion.md)) | Primero hay que validar la estrategia fuera de muestra | Holdout de H2 aprobado (requiere PQ-17) |
| Señal del carry con ML (H3) | Pendiente de pre-registro | El clasificador mejora el AUC, pero adoptarlo tras verlo funcionar sería sobreajuste ([informe del modelo](../investigacion/2026-10-30-modelo-predictivo-funding.md)) | Su propio pre-registro con N actualizado |
| Carry siempre activo en BTC y ETH | Pendiente de pre-registro | Surgió al mirar los resultados de H1 ([decisión](../estrategias/01-carry/decision.md)) | Su propio pre-registro |
| Estrategia de Polymarket (épica PQ-11) | Después del carry | Orden de [ADR-0005](../adr/0005-orden-de-estrategias.md) | Carry en paper trading |
| Agentes LLM y sentimiento (CryptoBERT) | Después de las estrategias base | Son capas encima de estrategias que ya funcionen (ADR-0005) | Una estrategia en vivo a la que aportar una señal |
| Servidor completo de MLflow (con UI) | Usamos `mlflow-skinny` + SQLite | El paquete completo exige `pyarrow < 24`; nosotros usamos la 26 | Que MLflow acepte pyarrow ≥ 26; mientras tanto, la UI se abre con `uvx mlflow ui` |
| CLI y skills de Spec Kit | Descartado | Chocan con nuestras ramas y duplicarían Jira ([ADR-0008](../adr/0008-spec-kit-solo-para-historias-grandes.md)) | — |
| Migración a Zensical | Diferido | Aún está en 0.0.x ([ADR-0007](../adr/0007-mkdocs-material-para-la-documentacion.md)) | Una versión estable que construya el sitio sin advertencias |
| Infraestructura como código (Terraform) | Fase 1 de `deploy/` | No hay servidores que describir: todo corre en local | El primer VPS |
