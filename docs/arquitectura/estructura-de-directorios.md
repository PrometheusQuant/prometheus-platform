# Estructura de directorios

Referencia de dónde va cada cosa. Si algo no encaja en ninguna carpeta, se discute en un ticket
antes de crear una nueva.

```text
prometheus-platform/
├── .github/                    # CI (Actions), CodeQL, Dependabot, plantilla de PR, CODEOWNERS
├── config/                     # configuración versionada no secreta (entornos, universos, riesgo)
├── data/                       # lakehouse local: bronze/silver/gold. Ignorado por git
├── deploy/                     # infraestructura como código por fases de presupuesto
├── docs/
│   ├── academico/              # mapa capítulos del Proyecto Integrador → evidencia
│   ├── adr/                    # decisiones de arquitectura (formato MADR)
│   ├── arquitectura/           # estructura, módulos y diagramas C4
│   ├── compliance/             # acceso a exchanges, regulación y tributación
│   ├── estrategias/            # pre-registro, evaluación, holdout y decisión por estrategia
│   ├── investigacion/          # investigación base y notas con fuentes
│   ├── metodologia/            # CRISP-ML(Q), Definición de Listo/Terminado
│   └── runbooks/               # procedimientos de operación
├── notebooks/                  # exploración; salidas eliminadas por nbstripout
├── scripts/                    # utilidades de desarrollo, no funcionalidad del producto
├── src/prometheus_platform/    # el producto (ver abajo)
└── tests/                      # espejo de src/: unit/<paquete>/, integration/
```

## El paquete: `src/prometheus_platform/`

Monolito modular con arquitectura hexagonal ([ADR-0001](../adr/0001-monolito-modular-hexagonal.md)).
Las dependencias solo apuntan hacia el dominio; `import-linter` lo verifica en CI.

| Paquete | Capa | Responsabilidad | Puede importar |
|---|---|---|---|
| `domain/` | Núcleo | Value objects, eventos de dominio y puertos (`Protocol`). Solo librería estándar | Nada del proyecto |
| `ops/` | Transversal | Configuración, logging, métricas, alertas | `domain` |
| `strategies/` | Aplicación | Datos → señales (`Signal`). No conoce órdenes ni riesgo | `domain`, `ops` |
| `portfolio_risk/` | Aplicación | Dimensionado, límites pre-trade, kill-switch | `domain`, `ops` |
| `execution/` | Aplicación | Objetivos de cartera → órdenes vía `OrderGateway` | `domain`, `ops` |
| `data_platform/` | Aplicación | Ingesta y transformaciones del lakehouse | `domain`, `ops` |
| `research/` | Aplicación | Backtests, validación purgada, registro de experimentos | `domain`, `ops` |
| `adapters/` | Infraestructura | Implementaciones de los puertos: Binance, paper, persistencia | Aplicación, `ops`, `domain` |
| `api/` | Entrada | CLI `pq` y servicios de lectura para dashboards | Todos los anteriores |

`strategies`, `portfolio_risk` y `execution` son independientes entre sí: una estrategia nunca
envía órdenes ni decide su propio tamaño.

Los subpaquetes (por ejemplo `strategies/carry/` o `adapters/binance/`) se crean con el ticket que
les da contenido, no por adelantado.

## Tests

`tests/unit/<paquete>/` espeja `src/prometheus_platform/<paquete>/`. Los tests que tocan red,
disco o bases de datos van en `tests/integration/` y no corren contra servicios reales en CI.

## Qué nunca entra al repositorio

- Secretos (`.env`, claves, tokens): ver [SECURITY.md](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/SECURITY.md).
- Datos (`data/`, Parquet, DuckDB, CSV) y artefactos de MLflow.
- Material con copyright (libros y papers en PDF): se cita en APA 7 con enlace.
- Salidas de notebooks.
