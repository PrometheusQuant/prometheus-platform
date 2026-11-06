# PrometheusQuant — Impact Mapping

**Proyecto Integrador · Capítulo 3.1**  
**Estado:** plan aprobado en Jira; documento presentado para revisión de código.  
**Fecha:** 2026-11-06.  
**Épica relacionada:** PQ-10. **Ticket:** PQ-43 (asignado a Boris Igor Miranda Prieto).

## 1. Objetivo de impacto

**Objetivo central:** desarrollar y demostrar, de forma reproducible y auditable, una plataforma de investigación de estrategias cuantitativas que permita decidir si una hipótesis de trading merece avanzar desde la investigación hacia pruebas simuladas y, únicamente cuando supere controles de calidad y riesgo, considerar su operación con capital propio.

La meta inicial **no es maximizar operaciones ni prometer rentabilidad**. Es evitar la aprobación de estrategias aparentemente atractivas que en realidad provienen de sobreajuste, sesgo temporal o subestimación de costes y riesgos.

### Resultados observables propuestos

| Dimensión | Resultado buscado | Evidencia o indicador |
|---|---|---|
| Rigor estadístico | Las estrategias se aceptan o descartan con un protocolo previo y verificable | Hipótesis pre-registrada; número de ensayos; validación purgada; DSR, PBO y holdout final controlado |
| Viabilidad económica | La comparación incorpora comisiones, riesgo de contraparte y alternativas | Retorno neto, costes, drawdown, CVaR, escenario de referencia y sensibilidad |
| Reproducibilidad | Otro integrante puede reconstruir resultados con la misma versión del código | Commit, configuración, semilla, resultados versionados y pruebas automáticas |
| Seguridad operativa | No se opera en vivo sin controles aprobados | Paper trading, límites de exposición, kill-switch y procedimiento de incidentes |
| Defensa académica | El jurado puede rastrear las evidencias del proyecto | Documentación por capítulos, Jira, PRs, informe y dashboard |

Los indicadores son **criterios de seguimiento propuestos**, no una afirmación de que todos estén implementados hoy.

## 2. Actores, cambios de conducta y entregables

La lógica de Impact Mapping es: **¿por qué? → ¿quién? → ¿cómo debe cambiar su actuación? → ¿qué entregaremos?**

| Actor (¿quién?) | Cambio de conducta esperado (¿cómo?) | Entregable habilitador (¿qué?) | Medición |
|---|---|---|---|
| Equipo cuantitativo (dos investigadores/desarrolladores) | Formula hipótesis económicas antes de observar resultados y documenta todos los ensayos, incluidos los fallidos | Plantilla de pre-registro; pipeline de investigación; registro de experimentos | Proporción de experimentos registrados; trazabilidad del holdout |
| Responsable de gestión de riesgo | Rechaza operaciones que excedan límites, aunque la señal sea positiva | Módulo `portfolio_risk`, escenarios de estrés, límites y kill-switch | Exposición máxima, CVaR y cumplimiento de límites |
| Responsable de datos | Entrega información reproducible sin anticipar hechos que aún no eran conocidos | Lakehouse bronze/silver/gold, `knowledge_time`, controles de esquema y checksums | Datos sin filtraciones temporales y pruebas de calidad satisfactorias |
| Operador de la plataforma (capital propio) | Primero valida en entorno simulado y solo considera producción después de aprobar controles | Paper trading, adaptadores de exchange, bitácora de eventos y procedimientos | Incidentes, alertas y decisiones de pasar/no pasar a vivo |
| Docente y jurado | Evalúan evidencias verificables, no solo capturas de rentabilidad | Informe académico, dashboard de solo lectura, documentación, pruebas y PRs | Trazabilidad capítulo → evidencia → versión del código |

**Alcance actual:** herramienta de investigación para capital propio y evaluación académica. La oferta a clientes externos, manejo de fondos de terceros o venta de señales no se considera una actividad aprobada; requeriría un análisis normativo y comercial específico.

## 3. Mapa de impactos priorizado

| Prioridad | Objetivo | Actor clave | Impacto esperado | Producto o evidencia |
|---|---|---|---|---|
| **P1** | Decidir con evidencia estadística | Equipo cuantitativo | Rechazar estrategias sobreajustadas o no robustas | Research del carry, protocolo CRISP-ML(Q), backtests, validación anti-sobreajuste |
| **P1** | Medir rentabilidad neta y riesgo | Investigador económico / riesgo | Contrastar el retorno con alternativas y escenarios severos | Simulación Monte Carlo, costes, matriz de regímenes, CVaR y análisis de sensibilidad |
| **P1** | Conservar datos verificables | Responsable de datos | Evitar sesgo de anticipación | Ingesta bronze, transformación silver y features gold con controles point-in-time |
| **P2** | Preparar un uso operativo controlado | Operador | Separar señales, riesgo y ejecución; probar sin dinero real | Paper trading, límites y kill-switch, sujetos a validación pendiente |
| **P2** | Defender el proyecto | Equipo y docente | Mostrar resultados replicables | Dashboard, informe ejecutivo, mapa académico y evidencias de Jira/GitHub |
| **P3** | Considerar crecimiento posterior | Equipo promotor | Evaluar condiciones técnicas, legales y financieras antes de escalar | Estudio de viabilidad, arquitectura modular y seguimiento de decisiones ADR |

## 4. Hipótesis de impacto y pruebas de aceptación

1. **H-IM1 (calidad):** si cada estrategia incluye hipótesis previa, costes y validación temporal, el equipo podrá distinguir resultados defendibles de hallazgos por búsqueda excesiva. **Prueba:** expediente de una estrategia con N, benchmark, DSR/PBO, ventana de validación y decisión documentada.
2. **H-IM2 (economía):** si se incorporan escenarios de riesgo de contraparte y una alternativa comparable, una estrategia con retorno esperado positivo puede resultar no conveniente bajo límites de riesgo. **Prueba:** comparación de escenarios y decisión justificada para el carry.
3. **H-IM3 (academia):** si cada capítulo enlaza evidencias verificables, el evaluador podrá reconstruir la conclusión sin depender de una exposición oral. **Prueba:** enlaces funcionales entre rúbrica, documentación, commits y reportes.

## 5. Límites y riesgos

- **No equivalencia entre backtest y operación real:** latencia, liquidez, deslizamiento, indisponibilidad del exchange y riesgos regulatorios podrían cambiar los resultados.
- **Dependencia de documentación y datos externos:** los términos, comisiones y disponibilidades por país pueden cambiar y deben comprobarse antes de operar.
- **Conflicto entre objetivos:** un modelo puede mejorar métricas predictivas sin mejorar la utilidad económica neta; la decisión final debe incorporar riesgo y costes.
- **Estado de implementación:** el mapa representa impactos deseados; solo se consideran terminados los componentes que tengan evidencia verificable en código, pruebas y Jira.

## 6. Referencias internas de trazabilidad

- [`README.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/README.md): alcance y estrategias.
- [`docs/academico/README.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/academico/README.md): rúbrica y evidencias.
- [`docs/arquitectura/c4.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/arquitectura/c4.md): actores, sistemas y contenedores.
- [`docs/adr/0001-monolito-modular-hexagonal.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/adr/0001-monolito-modular-hexagonal.md): separación técnica de responsabilidades.
- [`docs/adr/0004-crisp-mlq-con-protocolo-financiero.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/adr/0004-crisp-mlq-con-protocolo-financiero.md): metodología y controles estadísticos.
- [`docs/investigacion/2026-11-05-simulacion-carry.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/investigacion/2026-11-05-simulacion-carry.md): evaluación del riesgo y decisiones PDCA.

## 7. Criterios de aceptación propuestos para Jira

- [x] Objetivo central de impacto formulado.
- [x] Actores y cambios de conducta identificados.
- [x] Relación impactos → entregables → indicadores.
- [x] Priorización y límites documentados.
- [x] Enlaces a fuentes internas del proyecto.
- [x] Aprobación del plan de implementación por el compañero en Jira.
- [ ] Revisión y aprobación del PR.
- [ ] Integración en `develop` con CI satisfactoria.
