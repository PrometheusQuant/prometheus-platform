# Decisiones de arquitectura (ADR)

Cada decisión difícil de revertir se registra como un ADR en formato
[MADR](https://adr.github.io/madr/), en el mismo PR que la implementa. Para una nueva, copia la
[plantilla](0000-plantilla.md) con el siguiente número libre.

| ADR | Decisión | Estado |
|---|---|---|
| [0001](0001-monolito-modular-hexagonal.md) | Monolito modular con arquitectura hexagonal | Aceptada |
| [0002](0002-uv-como-gestor-de-entornos.md) | uv como gestor de entornos y dependencias | Aceptada |
| [0003](0003-lakehouse-parquet-duckdb.md) | Lakehouse medallion con Parquet y DuckDB | Aceptada |
| [0004](0004-crisp-mlq-con-protocolo-financiero.md) | CRISP-ML(Q) con protocolo financiero anti-sobreajuste | Aceptada |
| [0005](0005-orden-de-estrategias.md) | Orden de implementación de las estrategias | Aceptada |
| [0006](0006-nautilustrader-para-ejecucion.md) | NautilusTrader para backtest event-driven, paper y vivo | Reemplazada por 0014 |
| [0007](0007-mkdocs-material-para-la-documentacion.md) | MkDocs Material para el sitio de documentación | Aceptada |
| [0008](0008-spec-kit-solo-para-historias-grandes.md) | Plantillas de Spec Kit solo para historias de ≥ 5 puntos | Aceptada |
| [0009](0009-streamlit-y-docker-para-el-dashboard.md) | Streamlit y Docker para el dashboard de investigación | Aceptada |
| [0010](0010-dagster-para-orquestar-el-lakehouse.md) | Dagster orquesta el lakehouse batch; research queda fuera | Aceptada |
| [0011](0011-contrato-de-estrategia.md) | Puerto `Strategy` con instantáneas point-in-time | Aceptada |
| [0012](0012-presupuesto-de-capital-con-cvar.md) | Presupuesto de capital entre estrategias con tope de CVaR y por exchange | Aceptada |
| [0013](0013-asistente-de-solo-lectura.md) | Asistente de LLM que solo explica y no opera | Aceptada |
| [0014](0014-ccxt-detras-de-los-puertos-para-ejecutar.md) | CCXT detrás de los puertos propios para ejecutar en Binance Demo y Bybit testnet | Aceptada |

Próximo número libre: **0015**.
