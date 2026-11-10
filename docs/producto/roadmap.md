# Roadmap de producto de PrometheusQuant

## 1. Propósito, usuarios y estado de aprobación

PrometheusQuant reúne datos de mercado, investigación cuantitativa, simulación y controles de riesgo para tomar decisiones trazables sobre estrategias de cripto. Su valor actual es permitir comprender y contrastar hipótesis con costes y limitaciones explícitos, sin prometer rentabilidad ni viabilidad comercial.

El roadmap comunica qué base existe, qué se propone entregar y qué condiciones deben resolverse antes de avanzar. Sus destinatarios son el profesor y jurado, que necesitan evidencias evaluables; el investigador, que necesita reproducibilidad; y el operador del equipo, que necesita conocer posiciones, riesgos y límites del entorno simulado.

- **Ticket:** [PQ-109](https://prometheusquant.atlassian.net/browse/PQ-109).
- **Estado:** Contenido documental aprobado por Boris el 10 de noviembre de 2026; pendiente de verificación directa en Jira y revisión de David.
- **Aprobación expresa del contenido documental por Boris:** 10 de noviembre de 2026. Esta aprobación no sustituye el consenso con David ni el cumplimiento de la DoD.
- **Revisión de David:** pendiente.
- **Contraste directo de Jira:** pendiente en esta sesión; el MCP de Atlassian no está disponible.
- **Base documental:** [mapa de PQ-108](https://github.com/PrometheusQuant/prometheus-platform/blob/d05369c352db1412415ed32e782fac9b5b1c0545/docs/producto/mapa-de-historias.md), publicado en el [PR #67](https://github.com/PrometheusQuant/prometheus-platform/pull/67), abierto y pendiente de revisión de David; todavía no integrado en `develop`.

La reducción del MVP y las decisiones Boris–David siguen pendientes de consenso. Este borrador no modifica compromisos, sprints ni tickets.

## 2. Cómo leer el roadmap

Los horizontes organizan capacidades y condiciones de avance; no convierten propuestas en entregas aceptadas.

| Horizonte | Significado |
|---|---|
| **NOW** | Base integrada y brechas conocidas al consultar las fuentes. |
| **NEXT — MVP** | Compromiso original y alternativa propuesta para la revisión académica del 13 de noviembre de 2026. |
| **NEXT — Feria/MMP** | Incrementos para presentación y uso recurrente, con aceptación y calendario pendientes de acuerdo. Incluye el seguimiento del hito académico del 20 de noviembre. |
| **LATER** | Capacidades futuras condicionadas a evidencia, capacidad del equipo y decisiones humanas. |

La oferta de valor evoluciona con la evidencia y los acuerdos de cada incremento:

| Horizonte | Valor principal para el usuario | Decisiones que permite tomar | Limitaciones o condiciones para avanzar |
|---|---|---|---|
| **NOW** | Comprender datos, contrastar el carry y explorar escenarios con controles de riesgo. | Valorar hipótesis, costes y limitaciones a partir de la base integrada. | Integración no equivale a demo acreditada; KE-014 y KE-016 siguen pendientes. |
| **NEXT — MVP** | Revisar con el profesor el alcance y las evidencias del producto. | Acordar qué capacidades se ofrecen y qué queda pendiente para el hito del 13 de noviembre. | El compromiso original sigue como referencia; la alternativa reducida y la demo local frente a 24/7 requieren consenso Boris–David y aceptación verificable. |
| **NEXT — Feria/MMP** | Presentar un recorrido comprensible y avanzar hacia uso recurrente con trazabilidad y continuidad. | Aceptar incrementos según usabilidad, evidencia científica y preparación operativa. | Conservar el hito académico del 20 de noviembre; confirmar fecha entre 27 de noviembre y 4 de diciembre, dependencias y alcance conjunto. |
| **LATER** | Explorar nuevas hipótesis, fuentes y capacidades de cartera e infraestructura. | Decidir qué investigar o ampliar y si corresponde considerar capital propio. | Opciones condicionadas, sin compromiso aprobado; capital real exige decisión humana expresa y controles aplicables. |

La priorización MoSCoW es una **propuesta por corte**, tomada del mapa de PQ-108: **Must Have** es necesario para su propósito; **Should Have** admite una alternativa temporal explícita; **Could Have** depende de capacidad y prerrequisitos; **Won’t Have** queda fuera del corte propuesto. Su ratificación conjunta está pendiente.

| Nivel de evidencia | Qué acredita | Qué falta acreditar por separado |
|---|---|---|
| **Código integrado** | Implementación identificable en una versión de `develop`, con PR fusionado. Para documentos: documentación integrada. | Comportamiento funcional y preparación operativa. |
| **Funcionalidad verificada** | Comprobación identificada por versión, alcance, condiciones y resultado. | Escenario completo de presentación y disponibilidad de sus recursos. |
| **Funcionalidad demostrable** | Recorrido reproducible ensayado con versión, datos, servicios y respaldo identificados. | Continuidad 24/7, validación científica o autorización para capital real. |

La fecha de consulta documental y de GitHub es el **10 de noviembre de 2026**. La base local es el commit `1d98331e08c94db54fe4ff457283958e2c195371`. Los datos de Jira proceden de la auditoría previa de PQ-108, realizada el 9 de noviembre y cuya reconsulta del 10 de noviembre está declarada en ese documento; **no hubo nueva consulta directa de Jira en esta sesión**. Los tickets enlazados sirven para trazabilidad y requieren contraste actual.

No se ejecutaron pruebas funcionales, demos, simulaciones, experimentos ni backtests para elaborar este borrador. Una prueba o resultado citado en una fuente es evidencia histórica de su alcance, no una certificación nueva de todo el producto.

## 3. NOW — Base integrada y brechas actuales

| Capacidad y valor para el usuario | Base integrada identificada | Límite o pendiente |
|---|---|---|
| Históricos reproducibles, validación y modelo gold: consultar datos y reconocer problemas de calidad. | Ingesta bronze, silver y gold; [PQ-20](https://prometheusquant.atlassian.net/browse/PQ-20), [PQ-21](https://prometheusquant.atlassian.net/browse/PQ-21) y [PQ-46](https://prometheusquant.atlassian.net/browse/PQ-46), según PQ-108. [Modelo gold](../arquitectura/modelo-gold.md). | Los datos locales no se distribuyen en Git. Deben acreditarse disponibilidad, actualización y escenario de consulta. |
| Investigación del carry y modelo predictivo: comparar hipótesis y comprender regímenes de funding. | [Evaluación del carry](../estrategias/01-carry/evaluacion.md), [modelo de funding](../investigacion/2026-10-30-modelo-predictivo-funding.md) y nowcast; [PQ-23](https://prometheusquant.atlassian.net/browse/PQ-23), [PQ-25](https://prometheusquant.atlassian.net/browse/PQ-25), [PQ-32](https://prometheusquant.atlassian.net/browse/PQ-32) y [PQ-58](https://prometheusquant.atlassian.net/browse/PQ-58) según el mapa. | Correcciones KE-014 y KE-016 pendientes; el modelo predictivo no equivale a H3 aprobada ni a una señal operativa aceptada. |
| Monte Carlo y what-if: explorar escenarios, pérdidas y supuestos de inversión. | [Informe de simulación](../investigacion/2026-11-05-simulacion-carry.md), `research/simulation.py` y `research/what_if.py`; [PQ-33](https://prometheusquant.atlassian.net/browse/PQ-33) y PQ-58. | Resultados simulados, condicionados a supuestos. La demo y sus artefactos deben prepararse sin improvisar ensayos de investigación. |
| Dashboard de investigación: explorar resultados sin leer código. | Streamlit y Docker; [PQ-34](https://prometheusquant.atlassian.net/browse/PQ-34) y PQ-58. [Runbook del dashboard](../runbooks/dashboard.md). | No acredita monitoreo operativo integrado ni usabilidad validada. |
| Riesgo, kill-switch y runner: observar una ejecución simulada con límites. | `portfolio_risk/`, runner y bróker simulado; [PQ-53](https://prometheusquant.atlassian.net/browse/PQ-53) y [PQ-54 / PR #62](https://github.com/PrometheusQuant/prometheus-platform/pull/62), fusionado. [Runbook de paper](../runbooks/paper-trading.md). | Precios públicos y fills simulados. No se acredita Binance Demo, operación 24/7 ni uso de dinero real. Persisten limitaciones del runbook. |
| Viabilidad económica: valorar costes y alternativas antes de arriesgar capital. | [Modelo de negocio e informes económicos](../academico/modelo-de-negocio.md); [PQ-44](https://prometheusquant.atlassian.net/browse/PQ-44) y [PQ-49](https://prometheusquant.atlassian.net/browse/PQ-49) según PQ-108. | Son análisis históricos bajo supuestos, no previsiones de ingresos. Comisiones reales de cuenta pendientes de [PQ-17](https://prometheusquant.atlassian.net/browse/PQ-17) según la evidencia previa. |

La CI del HEAD base registra comprobaciones satisfactorias de calidad y construcción de la imagen Docker, así como [construcción estricta de documentación](https://github.com/PrometheusQuant/prometheus-platform/actions/runs/42693444421). La [ejecución de calidad](https://github.com/PrometheusQuant/prometheus-platform/actions/runs/42693444428) es evidencia automatizada de esa versión; no demuestra por sí sola una demo ni continuidad operativa.

**Brechas metodológicas del carry:** [KE-014](../runbooks/errores-conocidos.md#ke-014-la-evaluación-de-desarrollo-incluye-la-liquidación-del-2024-07-01-0000-holdout) documenta una liquidación de la frontera del holdout incluida en desarrollo; la capa gold la excluye, pero la corrección de la evaluación sigue pendiente. **KE-016**, en el mismo registro, documenta ejecución del backtest en la vela que abre en *t* en lugar de *t* + 1 h; su impacto figura por medir. No corresponde presentar la evaluación como corregida ni afirmar que el holdout estuvo completamente intacto. Cualquier reevaluación se rige por el pre-registro, cuenta en N y requiere las condiciones y autorizaciones aplicables.

El monitoreo [PQ-55](https://prometheusquant.atlassian.net/browse/PQ-55) y la guía de infraestructura [PQ-56](https://prometheusquant.atlassian.net/browse/PQ-56) tienen PR abiertos con cambios solicitados. El registro compartido [PQ-112](https://prometheusquant.atlassian.net/browse/PQ-112) y el puerto [PQ-113](https://prometheusquant.atlassian.net/browse/PQ-113) tienen PR aprobados pero abiertos. Los materiales de [Power BI](../academico/dashboard-power-bi.md) están integrados; un `.pbix` terminado y validado no está acreditado por las fuentes consultadas.

## 4. NEXT — MVP

El **13 de noviembre de 2026 es un hito de revisión académica al cierre del Sprint 4**; no implica que todas las funcionalidades estén terminadas. El calendario se recoge en la [guía inicial](../metodologia/prompt-inicial-codex.md). PQ-108 reconstruye el compromiso original desde los objetivos y tickets de Sprint 3/4: paper 24/7 desplegado con CI/CD, monitoreo y respaldos; avance de tendencia, H3 y Polymarket; riesgo multiestrategia y entrega al profesor. El grado de terminación exigido a cada estrategia debe confirmarse en Jira y entre ambos responsables.

Mientras no haya consenso, **el compromiso original permanece como referencia**. La alternativa reducida siguiente es una propuesta, incluida la demo local frente a operación 24/7.

| Área y beneficio | Compromiso original según PQ-108 | Alternativa propuesta / prioridad | Dependencias y responsable de preparación | Condición de aceptación y riesgo pendiente |
|---|---|---|---|---|
| Paper: observar operación sin dinero real. | Operación 24/7 en Oracle, despliegue y respaldo. | Demo local del bróker simulado si ambos la aceptan; controles ofrecidos como Must. | David: [PQ-56](https://prometheusquant.atlassian.net/browse/PQ-56), [PQ-57](https://prometheusquant.atlassian.net/browse/PQ-57), [PQ-70](https://prometheusquant.atlassian.net/browse/PQ-70) y [PQ-73](https://prometheusquant.atlassian.net/browse/PQ-73). | Para 24/7: servicio, recuperación y evidencia de continuidad; para demo local: recorrido ensayado y limitación declarada. No se sustituye una opción por otra sin acuerdo. |
| Monitoreo: interpretar posiciones, PnL y estado. | Panel operativo, alertas y observabilidad. | [PQ-55](https://prometheusquant.atlassian.net/browse/PQ-55) Must; [PQ-71](https://prometheusquant.atlassian.net/browse/PQ-71) y comandos [PQ-72](https://prometheusquant.atlassian.net/browse/PQ-72) Should. | David prepara PQ-55; Boris prepara observabilidad según su carril. Coordinar Telegram y confirmar asignación en Jira. | PR de monitoreo aceptado e integrado; contrastar panel y diario. Verificar el canal ofrecido; el notificador existente no equivale al bot de comandos. |
| Tendencia: preparar otra hipótesis reproducible. | Motor en Sprint 3; evaluación y paper en Sprint 4. | [PQ-67](https://prometheusquant.atlassian.net/browse/PQ-67) Should; [PQ-68](https://prometheusquant.atlassian.net/browse/PQ-68) y [PQ-82](https://prometheusquant.atlassian.net/browse/PQ-82) como entregas separadas posteriores, condicionadas. | Boris prepara motor y evaluación; integración coordinada con David mediante contrato común. | Motor probado y costes identificados; evaluación con decisión documentada; paper solo cuando proceda. No se promete resultado favorable. |
| Trazabilidad: contabilizar investigación compartida. | Registro, puerto y ejecutor común. | [PQ-112](https://prometheusquant.atlassian.net/browse/PQ-112) Must antes de nuevos ensayos compartidos; [PQ-113](https://prometheusquant.atlassian.net/browse/PQ-113) Should; [PQ-116](https://prometheusquant.atlassian.net/browse/PQ-116) según corte acordado. | Aportaciones de ambos carriles; responsable formal por confirmar en Jira. | Integración y comprobaciones del registro/contrato. Un PR aprobado abierto no satisface integración. |
| Comprensión: consultar KPIs y escenarios. | Power BI y validación con usuarios. | [PQ-47](https://prometheusquant.atlassian.net/browse/PQ-47) Should; [PQ-76](https://prometheusquant.atlassian.net/browse/PQ-76) propuesto para MMP. | Boris prepara Power BI; reparto final acordado con David. | `.pbix`, fuentes, KPIs y validación identificados. La guía preparatoria no basta. |
| Amplitud de estrategias: diversificar investigación. | Avance de H3, Polymarket y riesgo multiestrategia. | Diferir del MVP básico; Won’t en esta alternativa. | David prepara carry/H3; Boris prepara Polymarket; riesgo depende del carril de David. | Diferimiento ratificado y comunicado. No anunciar reducción como aceptada. |
| Entrega académica: entender qué se ofrece y con qué evidencia. | Visión, mapa, roadmap y revisión con el profesor. | [PQ-107](https://prometheusquant.atlassian.net/browse/PQ-107), PQ-108, PQ-109 y [PQ-110](https://prometheusquant.atlassian.net/browse/PQ-110) Must. | Boris prepara documentación; ambos aportan evidencias y guion. | Documentos revisados, escenario identificado y pendientes comunicados. PQ-108 requiere revisión de David y el roadmap su propia aceptación. |

Las entregas de tendencia mantienen contratos distintos: [PQ-67](https://prometheusquant.atlassian.net/browse/PQ-67) entrega **motor y pruebas**; [PQ-68](https://prometheusquant.atlassian.net/browse/PQ-68) entrega **evaluación y decisión**, favorable o de descarte; [PQ-82](https://prometheusquant.atlassian.net/browse/PQ-82) entrega **integración en paper cuando proceda**. Ninguna autoriza capital real.

Los riesgos del corte son falta de consenso, PR pendientes, recursos operativos sin acreditar, disponibilidad de artefactos y confusión entre resultados históricos y operación actual. Antes de comunicar el alcance al profesor deben acordarse las capacidades ofrecidas y sus evidencias.

## 5. NEXT — Feria/MMP

El incremento busca una presentación comprensible y un uso recurrente con trazabilidad y continuidad acordes con lo que se ofrezca. **La fecha de Feria/MMP sigue pendiente entre el 27 de noviembre y el 4 de diciembre de 2026.** La guía inicial cita el 4 de diciembre; PQ-108 conserva ambas referencias. Este documento no resuelve la discrepancia.

**El compromiso académico del 20 de noviembre permanece visible:** la guía inicial fija el capítulo 9 para esa fecha. El [mapa académico](../academico/README.md) exige conclusiones, pitch, revisión de código y evaluación 360. Deben confirmarse en Jira su desglose, responsables y aceptación; proponer un MMP posterior no difiere automáticamente este hito. PQ-108 relaciona [PQ-59](https://prometheusquant.atlassian.net/browse/PQ-59), [PQ-60](https://prometheusquant.atlassian.net/browse/PQ-60) y [PQ-61](https://prometheusquant.atlassian.net/browse/PQ-61) con entregables finales y [PQ-77](https://prometheusquant.atlassian.net/browse/PQ-77), [PQ-88](https://prometheusquant.atlassian.net/browse/PQ-88) y [PQ-63](https://prometheusquant.atlassian.net/browse/PQ-63) con material, ensayos y release; su calendario concreto está por contrastar.

| Incremento y valor | Prioridad propuesta | Dependencias | Condición de aceptación |
|---|---|---|---|
| Capítulo 9 y material de presentación: permitir evaluación académica trazable. | Must; hito del 20-nov conservado. | Evidencias por capítulo, revisión cruzada, informe y calendario confirmado. | Artefactos revisados y enlazados a versiones; alcance y fecha de cada entrega confirmados. |
| Continuidad y Binance Demo: observar el comportamiento con el entorno del exchange. | Should: [PQ-51](https://prometheusquant.atlassian.net/browse/PQ-51), [PQ-52](https://prometheusquant.atlassian.net/browse/PQ-52) y [PQ-70](https://prometheusquant.atlassian.net/browse/PQ-70); operación según acuerdo. | Acceso y productos habilitados, adaptador, controles de riesgo, infraestructura y respaldos. David prepara ejecución/despliegue. | Evidencia del entorno usado, fills y recuperación. No confundir bróker simulado con Binance Demo. |
| Correcciones del carry y decisión fuera de muestra. | [PQ-66](https://prometheusquant.atlassian.net/browse/PQ-66) Must antes de validar nuevamente H2; [PQ-50](https://prometheusquant.atlassian.net/browse/PQ-50) Should condicionado. | [PQ-17](https://prometheusquant.atlassian.net/browse/PQ-17), KE-014, KE-016, protocolo y presencia/autorización del titular cuando corresponda. | Evaluación corregida, ensayos registrados y decisión documentada. El roadmap no autoriza abrir el holdout. |
| Evaluación de tendencia e integración eventual. | [PQ-68](https://prometheusquant.atlassian.net/browse/PQ-68) Should; [PQ-82](https://prometheusquant.atlassian.net/browse/PQ-82) y [PQ-116](https://prometheusquant.atlassian.net/browse/PQ-116) Could. | Motor [PQ-67](https://prometheusquant.atlassian.net/browse/PQ-67), registro y contratos; evaluación previa y coordinación con David. | Decisión de evaluación trazable; paper solo si procede, con diario y riesgo comprobados. |
| Usabilidad y explicación: permitir que usuarios no técnicos completen tareas. | [PQ-76](https://prometheusquant.atlassian.net/browse/PQ-76) Must; [PQ-74](https://prometheusquant.atlassian.net/browse/PQ-74) y [PQ-75](https://prometheusquant.atlassian.net/browse/PQ-75) Should. | Paneles disponibles, tareas, participantes y fuentes identificados. | Informe de usabilidad, límites de explicación y comparación competitiva sustentada. |
| Observabilidad y respuesta: reconocer degradaciones y recuperar operación. | [PQ-85](https://prometheusquant.atlassian.net/browse/PQ-85), [PQ-86](https://prometheusquant.atlassian.net/browse/PQ-86), [PQ-96](https://prometheusquant.atlassian.net/browse/PQ-96) y [PQ-97](https://prometheusquant.atlassian.net/browse/PQ-97) Should; [PQ-98](https://prometheusquant.atlassian.net/browse/PQ-98) Must antes de ofrecer Demo recurrente. | Telemetría, diario, canales y procedimientos. Boris prepara observabilidad; David coordina operación. | Alertas e informes contrastados; procedimientos y simulacros con evidencias para el alcance ofrecido. |
| Preparación de feria: presentar un recorrido reproducible y una alternativa si falla. | Material, ensayos y release Must; modo presentación [PQ-102](https://prometheusquant.atlassian.net/browse/PQ-102) Could; servidor compartido [PQ-115](https://prometheusquant.atlassian.net/browse/PQ-115) Should. | Fecha consensuada, artefactos, recursos y versión candidata. | Guion ensayado, respaldo, notas de versión y revisión cruzada. |

Estas prioridades y traslados son propuestas de PQ-108, sujetas a consenso. Su inclusión no acredita finalización ni cambia fechas de Jira.

## 6. LATER

| Capacidad futura | Valor esperado | Condición para reconsiderarla |
|---|---|---|
| H3 y nuevas hipótesis del carry, incluida H4. | Investigar alternativas sin alterar retrospectivamente hipótesis previas. | Pre-registro propio, datos adecuados, costes y registro completo de ensayos; David prepara el carril de carry. |
| Polymarket: viabilidad, históricos y estrategia. | Ampliar fuentes e hipótesis de investigación. | Spike [PQ-78](https://prometheusquant.atlassian.net/browse/PQ-78), datos [PQ-92](https://prometheusquant.atlassian.net/browse/PQ-92) y pre-registros/evaluaciones pertinentes; elegibilidad documental no equivale a datos disponibles. Boris prepara este carril. |
| Multiexchange, [PQ-94](https://prometheusquant.atlassian.net/browse/PQ-94) y [PQ-100](https://prometheusquant.atlassian.net/browse/PQ-100). | Contrastar costes, contraparte y ejecución en otros entornos. | Datos y acceso comprobados, hipótesis propia, adaptadores y riesgo aceptados. |
| Sentimiento y momentum, [PQ-103](https://prometheusquant.atlassian.net/browse/PQ-103) y [PQ-114](https://prometheusquant.atlassian.net/browse/PQ-114). | Explorar señales adicionales. | Estrategias base, hipótesis ex ante y evaluación incremental neta de costes. |
| Cartera multiestrategia, [PQ-83](https://prometheusquant.atlassian.net/browse/PQ-83) y [PQ-84](https://prometheusquant.atlassian.net/browse/PQ-84). | Comprender asignación de riesgo y contribuciones. | Estrategias elegibles, contrato/ejecutor común y controles de cartera. PQ-108 la sitúa como Could del MMP condicionado; pasa a LATER si esas condiciones no se cumplen, sin diferimiento aprobado por este texto. |
| Evolución de infraestructura. | Facilitar colaboración, recuperación y crecimiento según necesidades reales. | Revisar [funcionalidades diferidas](../arquitectura/funcionalidades-diferidas.md) y ADR aplicables; infraestructura como código, mensajería o servicios separados solo cuando exista el problema que los justifique. |
| Eventual operación con capital real. | Evaluar una decisión de capital propio sustentada. | Decisión humana expresa, controles aplicables, condiciones de cuenta/comisiones [PQ-17](https://prometheusquant.atlassian.net/browse/PQ-17), consulta tributaria [PQ-27](https://prometheusquant.atlassian.net/browse/PQ-27), checklist [PQ-104](https://prometheusquant.atlassian.net/browse/PQ-104) y evidencia científica/operativa aceptada. |

Son opciones condicionadas, no compromisos futuros aprobados. El [orden de estrategias de ADR-0005](../adr/0005-orden-de-estrategias.md) y el [protocolo de ADR-0004](../adr/0004-crisp-mlq-con-protocolo-financiero.md) siguen como referencia. Capital real queda fuera del MVP y MMP propuestos; el roadmap no autoriza operaciones ni manejo de fondos de terceros.

## 7. Dependencias y decisiones Boris–David

Los responsables de preparación se proponen según los carriles de AGENTS.md y PQ-108; la asignación formal de cada ticket debe confirmarse en Jira.

| Decisión pendiente | Responsable de preparación | Consenso requerido | Consecuencia de no resolverla |
|---|---|---|---|
| MVP original frente a alternativa reducida. | Boris presenta diferencias; David confirma viabilidad operativa. | Boris y David. | Se conserva el compromiso original como referencia y no se comunica reducción aprobada. |
| Operación 24/7 frente a demo local. | David prepara recursos, continuidad y recuperación. | Ambos. | No se puede cerrar el alcance operativo ni ofrecer continuidad acreditada. |
| Monitoreo e infraestructura: [PQ-55](https://prometheusquant.atlassian.net/browse/PQ-55), [PQ-56](https://prometheusquant.atlassian.net/browse/PQ-56) y dependientes. | David atiende revisiones; Boris prepara observabilidad de su carril. | Ambos aceptan el recorrido y sus límites. | PR pendientes y capacidades sin integración/aceptación completa. |
| Entregas de tendencia: [PQ-67](https://prometheusquant.atlassian.net/browse/PQ-67), [PQ-68](https://prometheusquant.atlassian.net/browse/PQ-68) y [PQ-82](https://prometheusquant.atlassian.net/browse/PQ-82). | Boris prepara motor/evaluación; David prepara conexión al núcleo mediante contrato. | Ambos. | No se conoce qué entrega entra en cada corte; se mantiene separación sin prometer resultados. |
| MoSCoW y diferimientos. | Boris propone; ambos contrastan capacidad y compromisos. | Ambos. | Prioridades permanecen propuestas; no cambian los sprints. |
| Power BI y validación del `.pbix`. | Boris prepara artefactos y propone reparto. | Ambos. | Materiales preparatorios no acreditan dashboard terminado. |
| Fecha y alcance de Feria/MMP; relación con el 20-nov. | Ambos contrastan calendario del curso y tickets. | Ambos. | No se elige entre 27-nov y 4-dic; el capítulo 9 del 20-nov permanece visible. |
| Evidencia, aceptación y guion de demostración. | Cada responsable aporta versión, comprobaciones, recursos y respaldo. | Ambos revisan recorrido completo. | Integración no puede presentarse como demo acreditada. |
| Revisión de PQ-108 y del roadmap PQ-109. | Boris presenta; David revisa. | Contenido documental de PQ-109 aprobado expresamente por Boris el 10 de noviembre de 2026; revisión cruzada de David pendiente. | PQ-109 mantiene pendientes la verificación directa en Jira y la revisión de David; no se declara aceptado por el equipo. PQ-108 conserva su estado de revisión. |
| Condiciones de investigación y avance del carry. | David prepara correcciones y condiciones de [PQ-17](https://prometheusquant.atlassian.net/browse/PQ-17); ambos mantienen trazabilidad de N. | Titular y responsables según protocolo. | No se improvisan reevaluaciones ni apertura del holdout para completar una presentación. |

## 8. Aceptación, evidencias y mantenimiento

Para declarar una capacidad **integrada**, identificar PR fusionado, commit y archivos en `develop`. Para declararla **verificada**, añadir prueba o comprobación con versión, condiciones, alcance y resultado; una CI satisfactoria solo sustenta lo que comprueba. Para declararla **demostrable**, añadir ensayo reproducible del recorrido, datos, configuración, servicios disponibles, limitaciones y respaldo. Si falta evidencia, registrar «por verificar».

| Campo de aceptación | Evidencia requerida |
|---|---|
| Capacidad e historia | Beneficio ofrecido, ticket y corte acordado. |
| Versión e integración | Commit y PR fusionado; documentos identificados por versión. |
| Verificación | Comprobación aplicable a esa versión, condiciones y resultado. |
| Demostración | Pasos, artefactos y recursos del ensayo autorizado; resultado y respaldo. |
| Límites y decisión | Pendientes, incidentes, responsable y aceptación expresa del alcance. |

La [DoD del proyecto](../metodologia/definicion-de-listo-y-terminado.md) exige revisión cruzada, integración, CI y documentación, además de las condiciones específicas de datos e investigación. El roadmap no sustituye esa DoD. Un descarte científico documentado es un resultado válido y no una entrega fallida por carecer de rentabilidad favorable.

| Fuente | Estado de consulta y utilidad |
|---|---|
| AGENTS.md, CONTRIBUTING.md y [metodología](../metodologia/README.md). | Leídos en la base local; reglas de carriles, calidad, evidencia y flujo de trabajo. |
| [PQ-108, versión d05369c](https://github.com/PrometheusQuant/prometheus-platform/blob/d05369c352db1412415ed32e782fac9b5b1c0545/docs/producto/mapa-de-historias.md). | Leído mediante `git show` desde `feature/PQ-108-mapa-de-historias`, sin cambiar de rama. Auditoría original del 9-nov; reconsulta Jira del 10-nov declarada por esa fuente. No reproducida en esta sesión. |
| [PR #67](https://github.com/PrometheusQuant/prometheus-platform/pull/67). | GitHub consultado el 10-nov: abierto, sin revisiones registradas y pendiente de David. Corrige la referencia histórica de PQ-108 a publicación pendiente; no está integrado. |
| [PR #62](https://github.com/PrometheusQuant/prometheus-platform/pull/62). | GitHub consultado el 10-nov: fusionado; base integrada del runner simulado. |
| [PR #63](https://github.com/PrometheusQuant/prometheus-platform/pull/63) y [PR #66](https://github.com/PrometheusQuant/prometheus-platform/pull/66). | GitHub consultado el 10-nov: abiertos con cambios solicitados; monitoreo e infraestructura pendientes. |
| [PR #64](https://github.com/PrometheusQuant/prometheus-platform/pull/64) y [PR #65](https://github.com/PrometheusQuant/prometheus-platform/pull/65). | GitHub consultado el 10-nov: aprobados y abiertos; registro y puerto sin integrar. |
| [Impact Mapping](../academico/impact-map.md), [modelo de negocio](../academico/modelo-de-negocio.md) y [mapa académico](../academico/README.md). | Documentación local consultada: usuarios, valor, límites económicos y evidencias por capítulo. No se actualizaron cotizaciones ni se recalcularon resultados. |
| ADR-0004, ADR-0005 y [funcionalidades diferidas](../arquitectura/funcionalidades-diferidas.md). | Consultados como reglas y condiciones de evolución. |
| [Paper trading](../runbooks/paper-trading.md), [dashboard](../runbooks/dashboard.md) y [errores conocidos](../runbooks/errores-conocidos.md). | Consultados para alcance, preparación y limitaciones, incluidas KE-014 y KE-016. |
| [Calendario documental](../metodologia/prompt-inicial-codex.md). | Consultado: revisión MVP 13-nov, capítulo 9 el 20-nov y referencia a Feria 4-dic, pendiente de conciliar con PQ-108. |
| [PQ-109 en Jira](https://prometheusquant.atlassian.net/browse/PQ-109) y tickets relacionados. | Sin consulta directa nueva: requisitos, criterios de aceptación, estados, asignaciones y calendario actuales pendientes de contraste. |

**Límites de esta elaboración:** no hubo nueva consulta directa de Jira; su información procede de evidencia documental previa con fecha identificada. Los estados de GitHub se citan según lo comprobado el 10 de noviembre de 2026. No se ejecutaron pruebas funcionales, demos, simulaciones, backtests ni experimentos. No se modificaron compromisos, sprints ni tickets de Jira.

El mantenimiento deberá conservar fecha, versión y procedencia de cada actualización, distinguir propuesta de acuerdo y volver a contrastar los estados antes de comunicar una entrega. Cambiar prioridades o fechas requiere registrar el consenso correspondiente; modificar investigación exige el protocolo aplicable. Boris aprobó expresamente el contenido documental el 10 de noviembre de 2026; las acciones posteriores, incluida cualquier preparación de commit o publicación, requieren las autorizaciones correspondientes.
