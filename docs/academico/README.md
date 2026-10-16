# Proyecto Integrador: mapa de capítulos a evidencia

La estructura única del Proyecto Integrador (capítulos 0–9) se cumple con artefactos de este
repositorio y de Jira, no con un documento paralelo. Esta tabla dice dónde está, o dónde estará,
la evidencia de cada ítem. Los entregables escritos (informe, presentación) se redactan en esta
carpeta a partir de esa evidencia.

| Ítem | Contenido exigido | Evidencia | Épica |
|---|---|---|---|
| 0.1–0.3 | Título, equipo, línea temática, resumen ejecutivo | `README.md`, este documento, `informe/` | PQ-10 |
| 1.1–1.2 | Antecedentes, causas y solución actual | [`investigacion/`](../investigacion/) | PQ-2 |
| 1.3 | Pregunta de investigación y objetivos | `estrategias/*/pre-registro.md` | PQ-2 |
| 1.4 | Alcance, limitaciones y supuestos | ADR-0005, [`compliance/`](../compliance/) | PQ-2 |
| 1.5 | Auditoría de fuentes (≥ 5.000 registros) | Spike de Data Vision | PQ-2 (PQ-19) |
| 2.1 | Estado del arte (APA 7) | `academico/marco-de-referencia.md` | PQ-2 (PQ-28) |
| 2.2–2.3 | PESTEL; marco normativo y ético | `academico/marco-de-referencia.md`, `compliance/` | PQ-2 (PQ-28) |
| 3.1 | Stakeholders e Impact Mapping | `academico/impact-map.md` | PQ-10 |
| 3.2 | Historias de usuario y backlog | Jira, proyecto `PQ` | PQ-1 |
| 3.3 | Orquestación de repositorios | GitHub, [`CONTRIBUTING.md`](../../CONTRIBUTING.md), reglas de rama | PQ-1 |
| 4.1–4.3 | Extracción, limpieza, feature engineering | `src/prometheus_platform/data_platform/` | PQ-3 |
| 5.1–5.3 | Selección de algoritmos, entrenamiento, evaluación | `research/`, `estrategias/*/evaluacion.md` | PQ-4, PQ-5, PQ-6, PQ-12 |
| 6.1–6.2 | Pseudoaleatorios con bondad de ajuste; simulación y optimización | `research/`, `academico/simulacion.md` | PQ-9 |
| 6.3 | Rediseño del proceso con PDCA | `metodologia/`, ciclo de `estrategias/` | PQ-9 |
| 7.1 | Modelado de datos y ETL | Lakehouse gold, modelo tabular de BI | PQ-3, PQ-10 |
| 7.2 | Dashboard interactivo y KPIs | Power BI (archivo fuera de git), Grafana | PQ-10 |
| 7.3 | Despliegue (TRL 5) | Paper trading en testnet, app de demostración | PQ-7 |
| 7.4 | Validación estadística | Deflated Sharpe, PBO, pruebas de hipótesis | PQ-4 |
| 8.1–8.4 | Competencia, Canvas, costes cloud, ROI | `academico/modelo-de-negocio.md`, [`deploy/`](../../deploy/) | PQ-10 |
| 9.1–9.4 | Conclusiones, pitch, code review, evaluación 360 | `academico/informe/`, historial de PRs | PQ-10 |

## Marcos de referencia

- **CRISP-ML(Q)** como ciclo de vida: [ADR-0004](../adr/0004-crisp-mlq-con-protocolo-financiero.md).
- **ABET Criterio 3 (SO1–SO7)** y **CDIO**: el mapeo de resultados a artefactos está en la
  [investigación base](../investigacion/2026-10-16-plataforma-multiestrategia.md).
- **TRL 4–5**: backtests reproducibles (TRL 4) y paper trading con datos en vivo en testnet (TRL 5).

## Qué no va aquí

Material con copyright (libros, papers en PDF) ni datos personales: se citan en APA 7 con enlace.
