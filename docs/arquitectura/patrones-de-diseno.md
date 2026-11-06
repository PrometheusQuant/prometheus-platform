# Patrones de diseño y SOLID en el código

Este documento nombra los patrones que **ya existen** en el código, con su ruta, para el code
review (cap. 9.3). Lo que todavía no existe se marca como *planeado*. Si un patrón no aparece aquí,
no lo usamos.

## Arquitectura

| Patrón | Dónde | Qué resuelve |
|---|---|---|
| **Puertos y adaptadores** (hexagonal) | Puertos en `domain/ports.py`; adaptadores en `adapters/` | El núcleo no conoce Binance, Parquet ni MLflow. `import-linter` lo verifica en la CI ([ADR-0001](../adr/0001-monolito-modular-hexagonal.md)) |
| **Monolito modular por capas** | `pyproject.toml` (`[tool.importlinter]`) | Entrada → infraestructura → aplicación → base de datos → transversal → dominio |
| **Medallion** (bronze/silver/gold) | `data_platform/ingest.py`, `data_platform/silver.py`, `research/panel.py` | Separar lo crudo, lo validado y las features ([ADR-0003](../adr/0003-lakehouse-parquet-duckdb.md)) |

## Patrones GoF y afines

| Patrón | Dónde | Qué resuelve |
|---|---|---|
| **Adapter** | `adapters/binance_data_vision.py` (`BinanceDataVisionSource`), `adapters/mlflow_registry.py` (`MlflowRegistry`) | Traducir una API externa (HTTP de Data Vision, cliente de MLflow) al puerto que espera el núcleo |
| **Repository** | `domain/ports.py` (`BronzeStore`, `EventJournal`); `adapters/parquet_bronze.py`, `adapters/in_memory.py` | Guardar y consultar sin que el núcleo sepa si es Parquet o memoria |
| **Strategy** | `research/backtest.py` (`CostModel`: `MAIN_COSTS`, `ALT_COSTS`, `MAKER_COSTS`); `research/funding_model.py` (`ModelSpec`); `research/simulation.py` (simuladores v1, v2 y v3) | Algoritmos intercambiables con la misma interfaz: costes, modelos de ML, generadores de trayectorias |
| **State** (máquina de estados) | `research/backtest.py` (`_CarryBook`) | La histéresis del carry: plano → orden pendiente → abierto → rebalanceo → salida |
| **Facade** | `api/cli.py` (`pq`); `research/carry_evaluation.py` (`evaluate_hypothesis`) | Un solo comando o función para un flujo de muchos pasos |
| **Value Object** | `domain/model.py` (`Bar`, `FundingRate`, `Signal`, `InstrumentId`); `domain/datasets.py` (`ArchiveRef`, `RawArchive`) | Objetos inmutables (`frozen=True`) que validan sus invariantes al crearse: un `Bar` con `high < low` no puede existir |
| **Data Contract** | `data_platform/silver.py` (`KlineSchema`, `FundingSchema` con pandera) | Esquema y rangos declarativos entre bronze y silver |
| **Inyección de dependencias** | `ingest(refs, source, store)`; `ParquetBronzeStore(clock=…)`; `BinanceDataVisionSource(sleep=…)` | Probar sin red ni reloj real: los tests inyectan `httpx.MockTransport`, `FixedClock` y un `sleep` falso |
| **Observer** | *Planeado (PQ-38)* | Enrutar logs ERROR a notificadores (consola, Telegram) |

**Un patrón que evitamos a propósito: Singleton.** OmniVoC usaba Singletons para la base de datos y
el logger. Aquí se inyectan las dependencias: un Singleton es estado global y complica los tests. La
única configuración global es la de structlog (`ops/logging.py`), que se configura una vez al arrancar.

## SOLID

| Principio | Ejemplo concreto |
|---|---|
| **S**: responsabilidad única | `BinanceDataVisionSource` solo descarga y verifica; `ParquetBronzeStore` solo guarda; `ingest()` solo orquesta |
| **O**: abierto/cerrado | Un nuevo exchange es un adaptador nuevo que cumple `HistoricalDataSource`, sin tocar `ingest()` |
| **L**: sustitución de Liskov | `InMemoryEventJournal` y cualquier journal persistente son intercambiables: los tests de puertos lo comprueban con mypy |
| **I**: segregación de interfaces | Puertos pequeños: `Clock` tiene un solo método; `HistoricalDataSource`, dos |
| **D**: inversión de dependencias | `domain/` no importa nada de terceros (contrato de `import-linter`); `data_platform` depende de los puertos, no de los adaptadores |
