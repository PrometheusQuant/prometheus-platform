# PrometheusQuant Platform

Plataforma de trading **multiestrategia** para un equipo pequeño de quants: ingesta de datos,
investigación, backtesting con controles contra el sobreajuste, paper trading y ejecución en vivo.
Es también el Proyecto Integrador de la carrera (Ciencias de Datos / Ingeniería Industrial), pero
está diseñada para seguir creciendo después del semestre.

📖 **Documentación:** <https://prometheusquant.github.io/prometheus-platform/> (arquitectura y
diagramas C4, ADR, metodología e investigación).

> **Aviso.** Este repositorio es material de investigación y desarrollo. No es asesoramiento
> financiero ni promete rentabilidad. Operar con apalancamiento puede causar pérdidas mayores al
> capital invertido.

## Qué debilidades de mercado se explotan

Orden de implementación acordado (ver [ADR-0005](docs/adr/0005-orden-de-estrategias.md)):

| # | Estrategia | Debilidad del mercado | Estado |
|---|---|---|---|
| 1 | Carry de funding en perpetuos (delta neutral) | Demanda minorista de apalancamiento que mantiene el funding positivo | Pendiente |
| 2 | Tendencia con *volatility targeting* (BTC/ETH) | Subreacción y tendencias persistentes en cripto | Pendiente |
| 3 | Mercados de predicción (Polymarket, maker) | Sesgo favorito–longshot; riesgo no correlacionado con cripto | Pendiente |
| 4 | Capas de ML y sentimiento | Meta-labeling y régimen como filtros, no como fuente de alfa | Pendiente |

El fundamento de cada decisión está en la investigación:
[`docs/investigacion/`](docs/investigacion/).

## Arquitectura

**Monolito modular hexagonal** (puertos y adaptadores), con bus de eventos en proceso y un
journal append-only para auditoría. Ver [ADR-0001](docs/adr/0001-monolito-modular-hexagonal.md).

```text
api                             ← puntos de entrada (CLI, servicios de lectura)
adapters                        ← Binance, paper, persistencia (implementan los puertos)
strategies | portfolio_risk | execution | data_platform | research
ops                             ← configuración, logging y métricas (transversal)
domain                          ← value objects, eventos y puertos; solo librería estándar
```

Los límites entre capas se verifican en CI con `import-linter` (contratos en `pyproject.toml`).

## Estructura del repositorio

| Carpeta | Para qué |
|---|---|
| `src/prometheus_platform/` | El producto: dominio, estrategias, riesgo, ejecución, datos, investigación |
| `tests/` | Espejo de `src/`: `unit/<paquete>/` e `integration/` |
| `config/` | Configuración versionada no secreta (entornos, universos, límites de riesgo) |
| `data/` | Lakehouse local bronze/silver/gold; **fuera de git** |
| `notebooks/` | Exploración e investigación, sin salidas |
| `deploy/` | Infraestructura como código por fases de presupuesto |
| `scripts/` | Utilidades de desarrollo |
| `docs/` | ADRs, arquitectura, metodología, estrategias, compliance, runbooks y académico |

Detalle y reglas: [docs/arquitectura/estructura-de-directorios.md](docs/arquitectura/estructura-de-directorios.md).

## Metodología

- **Ciclo de vida:** CRISP-ML(Q), con un protocolo financiero de control de calidad (registro de
  todos los ensayos, validación purgada, Deflated Sharpe, PBO y holdout de un solo uso).
  Ver [ADR-0004](docs/adr/0004-crisp-mlq-con-protocolo-financiero.md).
- **Ritmo:** Scrum en sprints de 2 semanas en Jira (proyecto `PQ`); cada hipótesis es un ciclo PDCA.
- **Código:** GitFlow simplificado, Conventional Commits y smart commits de Jira.
  Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Empezar

Requisitos: [uv](https://docs.astral.sh/uv/) y git. `uv` instala la versión de Python correcta.

```bash
git clone git@github.com:PrometheusQuant/prometheus-platform.git
cd prometheus-platform
make setup     # entorno + hooks de pre-commit
make check     # lint, tipos, arquitectura y tests (lo mismo que corre CI)
make docs      # documentación en http://127.0.0.1:8000 con recarga en vivo
```

## Seguridad

Nunca se suben claves al repositorio. Ver [SECURITY.md](SECURITY.md).

## Licencia

[Apache-2.0](LICENSE). Permite el uso, la modificación y la distribución, incluido el uso
comercial, conservando el aviso de copyright y el archivo [NOTICE](NOTICE).
