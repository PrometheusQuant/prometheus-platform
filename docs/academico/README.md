# Proyecto Integrador: mapa de capítulos a evidencia

La estructura única del Proyecto Integrador (capítulos 0–9) se cumple con artefactos de este
repositorio y de Jira, no con un documento paralelo. Esta tabla dice dónde está, o dónde estará,
la evidencia de cada ítem. Los entregables escritos (informe, presentación) se redactan en esta
carpeta a partir de esa evidencia.

| Ítem | Contenido exigido | Evidencia | Épica |
|---|---|---|---|
| 0.1–0.3 | Título, equipo, línea temática, resumen ejecutivo | `README.md`, este documento, `informe/` | PQ-10 |
| 1.1 | Antecedentes y contexto | [`investigacion/`](../investigacion/README.md) | PQ-2 |
| 1.2 | Causas (Ishikawa, 5 porqués) y solución actual | [Planteamiento del problema](planteamiento-del-problema.md) | PQ-2 (PQ-45) |
| 1.3 | Pregunta de investigación y objetivos (matriz de consistencia) | [Planteamiento del problema](planteamiento-del-problema.md), `estrategias/*/pre-registro.md` | PQ-2 (PQ-45) |
| 1.4 | Alcance, limitaciones y supuestos; matriz de riesgos | [Planteamiento del problema](planteamiento-del-problema.md), ADR-0005, [`compliance/`](../compliance/README.md) | PQ-2 (PQ-45) |
| 1.5 | Auditoría de fuentes (≥ 5.000 registros) | Spike de Data Vision | PQ-2 (PQ-19) |
| 2.1 | Estado del arte (APA 7) | `academico/marco-de-referencia.md` | PQ-2 (PQ-28) |
| 2.2–2.3 | PESTEL; marco normativo y ético | `academico/marco-de-referencia.md`, `compliance/` | PQ-2 (PQ-28) |
| 3.1 | Stakeholders e Impact Mapping | `academico/impact-map.md` | PQ-10 |
| 3.2 | Historias de usuario y backlog | Jira, proyecto `PQ` | PQ-1 |
| 3.3 | Orquestación de repositorios | GitHub, [`CONTRIBUTING.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/CONTRIBUTING.md), reglas de rama | PQ-1 |
| 4.1–4.3 | Extracción, limpieza, feature engineering | `src/prometheus_platform/data_platform/` | PQ-3 |
| 5.1–5.3 | Selección de algoritmos, entrenamiento, evaluación | `research/`, `estrategias/*/evaluacion.md` | PQ-4, PQ-5, PQ-6, PQ-12 |
| 6.1–6.2 | Pseudoaleatorios con bondad de ajuste; simulación y optimización | `research/`, `academico/simulacion.md` | PQ-9 |
| 6.3 | Rediseño del proceso con PDCA | `metodologia/`, ciclo de `estrategias/` | PQ-9 |
| 7.1 | Modelado de datos y ETL | Lakehouse gold, modelo tabular de BI | PQ-3, PQ-10 |
| 7.2 | Dashboard interactivo y KPIs | [Dashboard en Streamlit](../runbooks/dashboard.md) (PQ-34); Grafana para la operación | PQ-10 |
| 7.3 | Despliegue (TRL 5) | Imagen Docker del dashboard; paper trading en testnet | PQ-7 |
| 7.4 | Validación estadística | Deflated Sharpe, PBO, pruebas de hipótesis | PQ-4 |
| 8.1–8.4 | Competencia, Canvas, costes cloud, ROI | `academico/modelo-de-negocio.md`, [`deploy/`](https://github.com/PrometheusQuant/prometheus-platform/tree/develop/deploy) | PQ-10 |
| 9.1–9.4 | Conclusiones, pitch, code review, evaluación 360 | `academico/informe/`, historial de PRs | PQ-10 |

## Marcos de referencia

- **CRISP-ML(Q)** como ciclo de vida: [ADR-0004](../adr/0004-crisp-mlq-con-protocolo-financiero.md).
- **ABET Criterio 3 (SO1–SO7)** y **CDIO**: el mapeo de resultados a artefactos está en la
  [investigación base](../investigacion/2026-10-16-plataforma-multiestrategia.md).
- **TRL 4–5**: backtests reproducibles (TRL 4) y paper trading con datos en vivo en testnet (TRL 5).

## Qué no va aquí

Material con copyright (libros, papers en PDF) ni datos personales: se citan en APA 7 con enlace.

## Evidencia entregada en el Sprint 2 (2026-10-30)

| Capítulo | Evidencia |
|---|---|
| 1.2–1.4 Planteamiento del problema | [Planteamiento del problema](planteamiento-del-problema.md) (PQ-45, 2026-11-06): Ishikawa con 5 porqués, matriz de consistencia, registro de supuestos y matriz de riesgos |
| 1.5 Auditoría de fuentes | [Auditoría de Data Vision](../investigacion/2026-10-23-auditoria-binance-data-vision.md): 2.903 archivos y ≈1,1 M filas |
| 2.1–2.3 Marco de referencia | [Marco de referencia](marco-de-referencia.md): estado del arte en APA 7, PESTEL aplicado y marco normativo y ético |
| 4.1–4.2 Extracción y limpieza | Ingesta bronze (`pq ingest`) y capa silver con checks (`pq silver build`, `specs/PQ-21-capa-silver/`) |
| 4.3 Feature engineering | [EDA de las features](../investigacion/2026-10-30-eda-features-funding.md) |
| 5.1–5.3 Modelado | [Modelo predictivo del funding](../investigacion/2026-10-30-modelo-predictivo-funding.md) y [evaluación del carry](../estrategias/01-carry/evaluacion.md) |
| 6.1–6.3 Simulación y optimización | [Simulación del carry](../investigacion/2026-11-05-simulacion-carry.md): Markov estimada, KS/χ², Monte Carlo validado, optimización con CVaR y PDCA |
| 7.2–7.3 Dashboard y despliegue | [Dashboard en Streamlit + Docker](../runbooks/dashboard.md) ([ADR-0009](../adr/0009-streamlit-y-docker-para-el-dashboard.md)) |
| 9.2 Pitch | [Informe ejecutivo en PDF](informe-ejecutivo.pdf), generado con `make report` (Quarto) desde los JSON de resultados |
| 9.2 Preparación de la defensa | `uv run python scripts/export_sessions.py`: las sesiones de trabajo con Claude Code en Markdown, con secretos enmascarados, para cargarlas en NotebookLM y ensayar preguntas del jurado |
