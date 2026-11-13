# Mapa de historias y cortes de entrega de PrometheusQuant

**Ticket:** [PQ-108](https://prometheusquant.atlassian.net/browse/PQ-108)\
**Responsable:** Boris Igor Miranda Prieto.\
**Versión propuesta:** 10 de noviembre de 2026.\
**Evidencia consultada:** auditoría original realizada el 9 de noviembre de 2026; estados de Jira y GitHub reconsultados el 10 de noviembre de 2026.\
**Estado:** aprobado por Boris el 10 de noviembre de 2026; pendiente de revisión de David.

## 1. Propósito y recorrido del usuario

PrometheusQuant permite comprender datos de mercado, evaluar estrategias con costes y controles estadísticos, explorar escenarios de inversión y observar una operación simulada con controles de riesgo.

Usuarios considerados:

- **Profesor y jurado:** comprueban funcionamiento, evidencias y limitaciones.
- **Investigador cuantitativo:** necesita datos reproducibles y evaluaciones trazables.
- **Operador del equipo:** observa posiciones, riesgos, alertas y continuidad.

El mapa sigue este recorrido:

**Entender el mercado → Evaluar estrategias → Simular inversiones → Operar en paper trading → Vigilar riesgos → Decidir sobre capital real.**

## 2. Cortes y prioridades

Los cortes son acumulativos. Una funcionalidad propuesta para un corte no se considera entregada hasta acreditar su aceptación.

| Corte | Propósito |
|---|---|
| **Existente** | Base integrada de datos, investigación, simulación, dashboard, controles de riesgo y runner simulado. Su disponibilidad operativa debe acreditarse por separado. |
| **MVP — 13-nov-2026** | Entrega al profesor según el compromiso original. Se documenta también una alternativa reducida, todavía sin acuerdo de David. |
| **MMP — fecha pendiente** | Incremento con mayor continuidad, usabilidad y capacidades aceptadas para presentación y uso recurrente. |
| **Posterior** | Extensiones condicionadas y eventual decisión humana sobre capital real. |

La fecha del MMP permanece pendiente: existen referencias al **27 de noviembre** y al **4 de diciembre**. Este mapa no resuelve esa discrepancia.

La clasificación MoSCoW corresponde al corte propuesto:

| Clasificación | Significado |
|---|---|
| **Must Have** | Necesaria para cumplir el propósito del corte. |
| **Should Have** | Importante; admite una alternativa temporal explícita. |
| **Could Have** | Deseable si existe capacidad y se cumplen sus dependencias. |
| **Won’t Have** | Fuera del MVP/MMP propuesto; reconsiderable posteriormente. |

**Estas prioridades son una propuesta. No sustituyen los compromisos originales ni modifican Jira.**

## 3. Niveles de evidencia

| Nivel | Qué acredita | Qué evidencia requiere |
|---|---|---|
| **Código integrado** | La implementación forma parte de la rama de integración. | PR fusionado y archivos identificables. Para entregables documentales se indica «documentación integrada». |
| **Funcionalidad verificada** | El comportamiento fue comprobado para una versión y condiciones concretas. | Pruebas, CI o comprobaciones funcionales identificadas por versión, alcance y resultado. |
| **Funcionalidad demostrable** | Puede presentarse mediante un recorrido reproducible con los datos, configuración y servicios necesarios. | Ensayo de la demo, versión, escenario y respaldo identificados. |

Los niveles no son equivalentes:

- Un PR fusionado no acredita por sí solo el funcionamiento completo.
- Las pruebas automatizadas no acreditan por sí solas una demo preparada.
- Una demo satisfactoria no acredita continuidad 24/7 ni aprobación científica de una estrategia.

En esta revisión se comprobaron estados, integración y artefactos documentales. **No se ejecutaron pruebas ni demos.** Las pruebas mencionadas en PR constituyen evidencia histórica declarada; no certifican automáticamente la versión que se presentará el 13 de noviembre.

En las tablas:

- **F:** Jira «Finalizada».
- **EC:** Jira «En curso».
- **TP:** Jira «Tareas por hacer».
- **Sin aceptación localizada:** no se encontró evidencia suficiente de entrega aceptada; no demuestra ausencia de trabajo privado.
- Para todas las capacidades, el nivel **demostrable para el MVP** debe confirmarse mediante un ensayo autorizado.

## 4. Mapa de historias

### 4.1. Entender el mercado

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-19](https://prometheusquant.atlassian.net/browse/PQ-19) | Consultar cobertura y limitaciones de históricos. | Elegir fuentes adecuadas. | F | Documentación integrada: [PR #13](https://github.com/PrometheusQuant/prometheus-platform/pull/13), auditoría de Data Vision. | Existente / Must |
| [PQ-20](https://prometheusquant.atlassian.net/browse/PQ-20) | Obtener históricos reproducibles. | Evitar descargas manuales y duplicados. | F | Código integrado: [PR #14](https://github.com/PrometheusQuant/prometheus-platform/pull/14), ingesta bronze. | Existente / Must |
| [PQ-21](https://prometheusquant.atlassian.net/browse/PQ-21) | Consultar datos validados y reportes de calidad. | Reconocer huecos y errores temporales. | F | Código integrado: [PR #20](https://github.com/PrometheusQuant/prometheus-platform/pull/20), `data_platform/silver.py`. | Existente / Must |
| [PQ-31](https://prometheusquant.atlassian.net/browse/PQ-31) | Explorar funding, precios y correlaciones. | Comprender las variables de investigación. | F | Código e informe integrados: [PR #24](https://github.com/PrometheusQuant/prometheus-platform/pull/24), panel y EDA. | Existente / Must |
| [PQ-65](https://prometheusquant.atlassian.net/browse/PQ-65) | Incorporar datos públicos recientes. | Mantener actualizado el análisis. | F | Código integrado: [PR #54](https://github.com/PrometheusQuant/prometheus-platform/pull/54), ingesta REST. | Existente / Must |
| [PQ-32](https://prometheusquant.atlassian.net/browse/PQ-32), [PQ-58](https://prometheusquant.atlassian.net/browse/PQ-58) | Consultar el modelo y la predicción reciente de funding. | Interpretar el régimen estimado. | Ambos F | Código integrado: [PR #25](https://github.com/PrometheusQuant/prometheus-platform/pull/25), [#58](https://github.com/PrometheusQuant/prometheus-platform/pull/58), `nowcast.py`. | Existente / Should |
| [PQ-74](https://prometheusquant.atlassian.net/browse/PQ-74) | Explicar la influencia de las variables. | Comprender predicciones y límites. | TP | Ampliación explicativa sin aceptación localizada. | MMP / Should |
| [PQ-78](https://prometheusquant.atlassian.net/browse/PQ-78), [PQ-92](https://prometheusquant.atlassian.net/browse/PQ-92) | Comprobar viabilidad e incorporar históricos de Polymarket. | Ampliar las fuentes de investigación. | Ambos TP | Spike e ingesta pendientes; elegibilidad documentada no equivale a histórico disponible. | MMP / Could |

### 4.2. Evaluar estrategias

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-18](https://prometheusquant.atlassian.net/browse/PQ-18) | Consultar las reglas pre-registradas del carry. | Identificar cambios posteriores a la evaluación. | F | Pre-registro integrado; evidencia histórica de aprobación formal pendiente de aclaración. | Existente / Must |
| [PQ-23](https://prometheusquant.atlassian.net/browse/PQ-23), [PQ-25](https://prometheusquant.atlassian.net/browse/PQ-25) | Comparar carry y benchmarks con costes y controles estadísticos. | Evaluar evidencia económica y sobreajuste. | Ambos F | Código e informes integrados: [PR #24](https://github.com/PrometheusQuant/prometheus-platform/pull/24). Correcciones metodológicas pendientes. | Existente / Must |
| [PQ-24](https://prometheusquant.atlassian.net/browse/PQ-24) | Registrar configuraciones y resultados. | Contabilizar lo investigado. | F | Código integrado: PR #24, registro MLflow local. | Existente / Must |
| [PQ-48](https://prometheusquant.atlassian.net/browse/PQ-48) | Consultar pruebas estadísticas y tamaños de efecto. | Valorar la evidencia disponible. | F | Código e informe integrados: [PR #50](https://github.com/PrometheusQuant/prometheus-platform/pull/50). | Existente / Should |
| [PQ-64](https://prometheusquant.atlassian.net/browse/PQ-64) | Consultar las reglas de tendencia antes de evaluar. | Preservar la hipótesis ex ante. | F | Documentación integrada: [PR #53](https://github.com/PrometheusQuant/prometheus-platform/pull/53). | Existente / Must |
| [PQ-112](https://prometheusquant.atlassian.net/browse/PQ-112) | Contabilizar ensayos de ambos carriles. | Mantener trazabilidad conjunta. | EC | [PR #64](https://github.com/PrometheusQuant/prometheus-platform/pull/64) aprobado, abierto; código todavía sin integrar. | MVP / Must antes de nuevos ensayos compartidos |
| [PQ-67](https://prometheusquant.atlassian.net/browse/PQ-67) | Disponer del motor de tendencia con volatilidad objetivo y costes. | Preparar simulaciones reproducibles. | TP | Pre-registro integrado; motor sin aceptación localizada. | MVP / Should en alternativa propuesta |
| [PQ-68](https://prometheusquant.atlassian.net/browse/PQ-68) | Evaluar tendencia mediante CPCV, DSR, PBO y gates. | Obtener una decisión documentada, favorable o de descarte. | TP | Depende de PQ-67; evaluación sin aceptación localizada. | MMP / Should, condicionada |
| [PQ-66](https://prometheusquant.atlassian.net/browse/PQ-66) | Corregir la evaluación de desarrollo del carry. | Disponer de una base metodológica actualizada. | TP | KE-014 documentado; coordinación con KE-016 según decisión en PQ-50. | MMP / Must antes de validar nuevamente H2 |
| [PQ-50](https://prometheusquant.atlassian.net/browse/PQ-50) | Obtener la decisión fuera de muestra de H2. | Contrastar la hipótesis bajo el protocolo. | TP | Dependencias PQ-17/PQ-66 pendientes; evaluación sin aceptación. | MMP / Should, condicionada |
| [PQ-69](https://prometheusquant.atlassian.net/browse/PQ-69), [PQ-87](https://prometheusquant.atlassian.net/browse/PQ-87), [PQ-93](https://prometheusquant.atlassian.net/browse/PQ-93) | Investigar H3 y Polymarket con hipótesis propias. | Decidir si aportan valor adicional. | Todos TP | Pre-registros, datos o evaluaciones pendientes según ticket. | Posterior / Won’t para MVP/MMP básico |
| [PQ-94](https://prometheusquant.atlassian.net/browse/PQ-94), [PQ-103](https://prometheusquant.atlassian.net/browse/PQ-103), [PQ-114](https://prometheusquant.atlassian.net/browse/PQ-114) | Investigar carry multiexchange, sentimiento y momentum transversal. | Explorar nuevas alternativas sin alterar hipótesis anteriores. | Todos TP | Investigación pendiente. | Posterior / Won’t para MVP/MMP |

**Separación obligatoria de tendencia:**

| Ticket | Entrega | Lo que no acredita por sí sola |
|---|---|---|
| **PQ-67** | Motor y pruebas. | Rentabilidad, gates aprobados o paper operativo. |
| **PQ-68** | Evaluación y decisión documentada. | Resultado favorable ni integración en paper. |
| **PQ-82** | Integración en paper cuando proceda. | Autorización para capital real. |

El mapa no promete resultados favorables. El descarte documentado es un resultado válido.

### 4.3. Simular inversiones

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-33](https://prometheusquant.atlassian.net/browse/PQ-33) | Explorar escenarios de funding y quiebra del exchange. | Comprender pérdidas posibles. | F | Código integrado: [PR #28](https://github.com/PrometheusQuant/prometheus-platform/pull/28), `simulation.py`. | Existente / Must |
| [PQ-58](https://prometheusquant.atlassian.net/browse/PQ-58) | Modificar capital, horizonte y supuestos del what-if. | Comparar distribuciones y benchmarks. | F | Código integrado: [PR #58](https://github.com/PrometheusQuant/prometheus-platform/pull/58), `what_if.py`. | Existente / Must |
| [PQ-34](https://prometheusquant.atlassian.net/browse/PQ-34) | Navegar resultados en un dashboard. | Comprenderlos sin leer código. | F | Código integrado: [PR #31](https://github.com/PrometheusQuant/prometheus-platform/pull/31), Streamlit y Docker. | Existente / Must |
| [PQ-46](https://prometheusquant.atlassian.net/browse/PQ-46) | Consultar datos y resultados organizados para BI. | Mantener trazabilidad de los indicadores. | F | Código integrado: [PR #49](https://github.com/PrometheusQuant/prometheus-platform/pull/49), modelo gold. | Existente / Must |
| [PQ-47](https://prometheusquant.atlassian.net/browse/PQ-47) | Navegar KPIs en Power BI. | Comparar datos, estrategia y riesgo. | TP; entrega parcial | [PR #51](https://github.com/PrometheusQuant/prometheus-platform/pull/51) integró guía, consultas, DAX y tema; `.pbix` terminado y validado sin acreditar. | MVP / Should |
| [PQ-76](https://prometheusquant.atlassian.net/browse/PQ-76) | Validar tareas con usuarios no técnicos. | Comprobar que los paneles se entienden. | TP | Informe de usabilidad sin aceptación localizada. | MMP / Must para acreditar usabilidad |

El what-if ejecuta simulación. Su existencia no autoriza ejecutarlo durante tareas limitadas a lectura.

### 4.4. Operar en paper trading

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-54](https://prometheusquant.atlassian.net/browse/PQ-54) | Ejecutar carry con precios públicos y fills simulados. | Observar el proceso sin dinero real. | F | Código integrado: [PR #62](https://github.com/PrometheusQuant/prometheus-platform/pull/62), runner, diario y bróker simulado. | Existente / Must |
| [PQ-55](https://prometheusquant.atlassian.net/browse/PQ-55) | Consultar posiciones, PnL, heartbeat y alertas. | Seguir la operación. | EC | [PR #63](https://github.com/PrometheusQuant/prometheus-platform/pull/63) abierto, con cambios solicitados. | MVP / Must |
| [PQ-56](https://prometheusquant.atlassian.net/browse/PQ-56), [PQ-57](https://prometheusquant.atlassian.net/browse/PQ-57) | Mantener paper sin depender de una laptop. | Obtener continuidad operativa. | EC / TP | [PR #66](https://github.com/PrometheusQuant/prometheus-platform/pull/66): guía con cambios solicitados; no acredita VM ni servicio desplegado. | MVP / Should en alternativa; 24/7 sigue comprometido originalmente |
| [PQ-51](https://prometheusquant.atlassian.net/browse/PQ-51), [PQ-52](https://prometheusquant.atlassian.net/browse/PQ-52) | Conectar Binance Demo. | Contrastar ejecución con el entorno del exchange. | Ambos TP | Adaptador aceptado sin localizar; acceso y decisiones pendientes. | MMP / Should |
| [PQ-113](https://prometheusquant.atlassian.net/browse/PQ-113) | Conectar estrategias mediante un contrato común. | Evitar cambios al núcleo por cada estrategia. | EC | [PR #65](https://github.com/PrometheusQuant/prometheus-platform/pull/65) aprobado, abierto; sin integrar. | MVP / Should |
| [PQ-116](https://prometheusquant.atlassian.net/browse/PQ-116), [PQ-82](https://prometheusquant.atlassian.net/browse/PQ-82) | Ejecutar señales genéricas e integrar tendencia cuando proceda. | Ampliar paper conservando diario y controles. | Ambos TP | Ejecutor e integración pendientes. | MMP / Could, condicionada |
| [PQ-70](https://prometheusquant.atlassian.net/browse/PQ-70) | Desplegar y recuperar versiones de forma controlada. | Reducir errores operativos. | TP | Automatización aceptada sin localizar. | MMP / Should; traslado propuesto, no aprobado |
| [PQ-100](https://prometheusquant.atlassian.net/browse/PQ-100), [PQ-101](https://prometheusquant.atlassian.net/browse/PQ-101) | Operar otro exchange o H3 en paper. | Ampliar alternativas aprobadas. | Ambos TP | Implementación y condiciones previas pendientes. | Posterior / Won’t para MVP/MMP básico |

### 4.5. Vigilar riesgos

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-53](https://prometheusquant.atlassian.net/browse/PQ-53) | Aplicar límites y kill-switch. | Controlar la operación. | F | Código integrado: [PR #57](https://github.com/PrometheusQuant/prometheus-platform/pull/57), `portfolio_risk/`. | Existente / Must |
| [PQ-38](https://prometheusquant.atlassian.net/browse/PQ-38) | Recibir avisos de errores relevantes. | Facilitar intervención. | F | Código integrado: [PR #30](https://github.com/PrometheusQuant/prometheus-platform/pull/30); entrega real del canal por verificar. | Existente / Must |
| [PQ-36](https://prometheusquant.atlassian.net/browse/PQ-36) | Consultar procedimientos de incidentes y continuidad. | Responder consistentemente. | F | Documentación presente: KEDB, incidentes y BIA. | Existente / Must |
| [PQ-71](https://prometheusquant.atlassian.net/browse/PQ-71) | Consultar métricas en Prometheus/Grafana. | Detectar degradación. | TP | Servicios y tablero aceptados sin localizar. | MVP / Should |
| [PQ-72](https://prometheusquant.atlassian.net/browse/PQ-72) | Consultar estado/PnL y solicitar kill desde Telegram. | Operar remotamente con control de acceso. | TP | Bot de comandos sin aceptación; diferente del notificador PQ-38. | MVP / Should |
| [PQ-73](https://prometheusquant.atlassian.net/browse/PQ-73) | Respaldar y restaurar el diario. | Conservar continuidad y trazabilidad. | TP | Respaldo y simulacro aceptados sin localizar. | MVP / Must si se ofrece 24/7 |
| [PQ-85](https://prometheusquant.atlassian.net/browse/PQ-85) | Recibir informes periódicos del paper. | Revisar desempeño e incidentes. | TP | Automatización semanal pendiente. | MMP / Should |
| [PQ-86](https://prometheusquant.atlassian.net/browse/PQ-86), [PQ-96](https://prometheusquant.atlassian.net/browse/PQ-96), [PQ-97](https://prometheusquant.atlassian.net/browse/PQ-97) | Detectar drift, señales de contraparte y disponibilidad. | Investigar degradaciones. | Todos TP | Implementación aceptada sin localizar. | MMP / Should |
| [PQ-98](https://prometheusquant.atlassian.net/browse/PQ-98) | Responder a claves comprometidas, desconexiones y datos atrasados. | Limitar incidentes. | TP | Procedimientos específicos y simulacros pendientes. | MMP / Must antes de ofrecer Demo recurrente |
| [PQ-83](https://prometheusquant.atlassian.net/browse/PQ-83), [PQ-84](https://prometheusquant.atlassian.net/browse/PQ-84) | Distribuir riesgo y visualizar varias estrategias. | Comprender exposición y contribuciones. | Ambos TP | Asignación y dashboard multiestrategia pendientes. | MMP / Could, condicionada |
| [PQ-81](https://prometheusquant.atlassian.net/browse/PQ-81), [PQ-99](https://prometheusquant.atlassian.net/browse/PQ-99) | Reforzar suministro de software y detección de defectos. | Mejorar controles técnicos. | Ambos TP | Extensiones pendientes. | Posterior / Won’t para MVP básico |

### 4.6. Decidir sobre capital real

| Jira | Descripción funcional | Beneficio para el usuario | Estado comprobado | Evidencia | Corte / MoSCoW |
|---|---|---|---|---|---|
| [PQ-28](https://prometheusquant.atlassian.net/browse/PQ-28), [PQ-26](https://prometheusquant.atlassian.net/browse/PQ-26) | Consultar contexto normativo y restricciones. | Reconocer condiciones pendientes. | Ambos F | Documentación integrada: [PR #26](https://github.com/PrometheusQuant/prometheus-platform/pull/26). No constituye autorización individual. | Existente / Must |
| [PQ-44](https://prometheusquant.atlassian.net/browse/PQ-44), [PQ-49](https://prometheusquant.atlassian.net/browse/PQ-49) | Comparar valor, costes y escenarios económicos. | Valorar viabilidad. | Ambos F | Modelo de negocio y [PR #52](https://github.com/PrometheusQuant/prometheus-platform/pull/52), fusionado. | Existente / Must |
| [PQ-39](https://prometheusquant.atlassian.net/browse/PQ-39) | Consultar un informe ejecutivo reproducible. | Revisar evidencia disponible. | F | Código y reporte integrados: [PR #32](https://github.com/PrometheusQuant/prometheus-platform/pull/32). | Existente / Should |
| [PQ-17](https://prometheusquant.atlassian.net/browse/PQ-17) | Confirmar productos y comisiones de la cuenta. | Determinar viabilidad de ejecución. | EC | Documentación pública parcial; comprobaciones desde la cuenta pendientes. | MMP / Must antes de actividades dependientes |
| [PQ-27](https://prometheusquant.atlassian.net/browse/PQ-27) | Documentar consulta tributaria. | Conocer obligaciones antes de capital real. | TP | Consulta aceptada sin localizar. | Posterior / Must antes de capital real |
| [PQ-95](https://prometheusquant.atlassian.net/browse/PQ-95) | Comparar costes observados con supuestos. | Revisar validez económica. | TP | Requiere fills; informe aceptado sin localizar. | MMP / Should |
| [PQ-104](https://prometheusquant.atlassian.net/browse/PQ-104) | Consultar un checklist de go/no-go. | Evitar decisiones prematuras. | TP | Checklist y decisión firmada pendientes. | MMP / Must para documentar condiciones |
| [PQ-91](https://prometheusquant.atlassian.net/browse/PQ-91) | Revisar resultados y condiciones del siguiente incremento. | Planificar con evidencia. | TP | Retrospectiva y roadmap pendientes. | Posterior / Should |

**La operación con capital real queda fuera de los cortes MVP y MMP propuestos.** Documentar condiciones no significa cumplirlas ni autorizar operaciones.

## 5. Habilitadores de entrega y comunicación

| Jira | Historia y beneficio | Estado y evidencia | Corte / MoSCoW |
|---|---|---|---|
| [PQ-22](https://prometheusquant.atlassian.net/browse/PQ-22) | Orquestar actualizaciones y checks para reducir trabajo manual. | F; código integrado en [PR #56](https://github.com/PrometheusQuant/prometheus-platform/pull/56). Despliegue 24/7 no acreditado. | Existente / Must |
| [PQ-107](https://prometheusquant.atlassian.net/browse/PQ-107) | Explicar usuarios y propuesta de valor. | TP; documento aceptado sin localizar. | MVP / Must |
| [PQ-108](https://prometheusquant.atlassian.net/browse/PQ-108) | Hacer visibles recorrido, prioridades y cortes. | TP; documento aprobado por Boris, creado localmente en la rama de PQ-108 y pendiente de publicación y revisión de David. | MVP / Must |
| [PQ-109](https://prometheusquant.atlassian.net/browse/PQ-109) | Comunicar oferta actual y próximos incrementos. | TP; roadmap aceptado sin localizar. | MVP / Must |
| [PQ-110](https://prometheusquant.atlassian.net/browse/PQ-110) | Presentar demo y notas coherentes con la entrega. | TP; entrega del 13-nov pendiente. | MVP / Must |
| [PQ-75](https://prometheusquant.atlassian.net/browse/PQ-75) | Sustentar diferenciación con alternativas y fuentes. | TP; ampliación competitiva pendiente. | MMP / Should |
| [PQ-59](https://prometheusquant.atlassian.net/browse/PQ-59), [PQ-60](https://prometheusquant.atlassian.net/browse/PQ-60), [PQ-61](https://prometheusquant.atlassian.net/browse/PQ-61) | Comunicar conclusiones y acreditar calidad y trazabilidad. | Todos TP; entregables finales pendientes. | MMP / Must |
| [PQ-77](https://prometheusquant.atlassian.net/browse/PQ-77), [PQ-88](https://prometheusquant.atlassian.net/browse/PQ-88), [PQ-63](https://prometheusquant.atlassian.net/browse/PQ-63) | Preparar material, ensayos y plan alternativo. | Todos TP; video, ensayos y release pendientes. | MMP / Must |
| [PQ-89](https://prometheusquant.atlassian.net/browse/PQ-89), [PQ-102](https://prometheusquant.atlassian.net/browse/PQ-102) | Facilitar consulta pública y presentación. | Ambos TP; implementación aceptada sin localizar. | MMP / Could |
| [PQ-115](https://prometheusquant.atlassian.net/browse/PQ-115) | Compartir datos y herramientas entre carriles. | TP; servidor común pendiente. | MMP / Should |

## 6. Cortes horizontales

| Recorrido | Existente | MVP: alternativa propuesta | MMP propuesto | Posterior |
|---|---|---|---|---|
| Entender el mercado | Históricos, calidad, EDA, ingesta reciente y modelo. | Presentación comprensible con limitaciones. | Explicabilidad y nuevas fuentes condicionadas. | Ampliaciones según evidencia. |
| Evaluar estrategias | Carry, registro local y pre-registro de tendencia. | Registro compartido; PQ-67 como Should. | PQ-68 y correcciones del carry, según condiciones. | Nuevas hipótesis. |
| Simular inversiones | Monte Carlo, what-if y dashboard. | Recorrido demostrable; Power BI como Should. | Usabilidad acreditada. | Mejoras por feedback. |
| Operar en paper | Runner simulado integrado. | Monitoreo aceptado; demo local si David acepta esa alternativa. | Demo del exchange y continuidad; PQ-82 si procede. | Más estrategias y exchanges. |
| Vigilar riesgos | Límites, kill-switch y notificadores. | Controles ofrecidos verificados; respaldo si se ofrece 24/7. | Observabilidad y procedimientos ampliados. | Refuerzos técnicos. |
| Decidir capital real | Informes y restricciones documentadas. | Explicar condiciones pendientes. | Checklist y evidencia adicional. | Decisión humana condicionada. |

Esta tabla describe **la alternativa propuesta**, no una reducción ya aceptada.

## 7. MVP original frente a alternativa reducida

El compromiso original se reconstruye desde los objetivos y tickets de Sprint 3/4. Estos incluyen paper 24/7 desplegado con CI/CD, monitoreo y respaldos; avance de tendencia, H3 y Polymarket; riesgo multiestrategia; y entrega al profesor.

La planificación no define con igual precisión el grado de terminación de todas las estrategias. Esa ambigüedad requiere acuerdo, sin prometer aprobación científica.

| Área | Alcance original planificado | Situación comprobada | Alternativa reducida propuesta |
|---|---|---|---|
| Operación | Paper 24/7 en Oracle, despliegue y respaldos. | PQ-56 EC; PQ-57/PQ-70/PQ-73 TP. | Demo local de paper simulado; continuidad 24/7 expresamente pendiente. |
| Monitoreo | Pestaña operativa, alertas y observabilidad. | PQ-55 EC; PQ-71 TP. | Monitoreo aceptado como Must; observabilidad ampliada como Should. |
| Telegram | Consultas de estado/PnL y kill. | PQ-72 TP. | Diferir comandos si se acepta; conservar controles disponibles y verificar el canal ofrecido. |
| Tendencia | Motor en Sprint 3; evaluación y paper en Sprint 4. | PQ-67/PQ-68/PQ-82 TP. | PQ-67 como Should del MVP; PQ-68/PQ-82 separados y condicionados. |
| H3 y Polymarket | Investigación y datos en marcha. | PQ-69/PQ-87/PQ-92 TP; spike PQ-78 pendiente. | Diferir del MVP básico. |
| Multiestrategia | Asignación de riesgo y dashboard. | PQ-83/PQ-84 TP. | Mantener una demostración del carry simulado. |
| Registro y contratos | Registro compartido, puerto y ejecutor. | PQ-112/PQ-113 EC; PR aprobados abiertos; PQ-116 TP. | Priorizar registro antes de nuevos ensayos; resto según alcance acordado. |
| Power BI y usabilidad | Compromisos de Sprint 3. | PQ-47/PQ-76 TP; materiales parciales integrados. | Power BI como Should; usabilidad para MMP. |
| Entrega al cliente | Visión, mapa, roadmap y revisión. | PQ-107/PQ-108/PQ-109/PQ-110 TP. | Mantenerlos como Must. |

**Mientras David no acuerde otra cosa, el compromiso original permanece como referencia.** La alternativa reducida no debe anunciarse al profesor como alcance acordado.

## 8. Brechas adicionales que deben permanecer visibles

| Tickets | Brecha | Tratamiento propuesto |
|---|---|---|
| PQ-50, PQ-66, PQ-17 | Evaluación fuera de muestra y condiciones previas pendientes. | No improvisar ejecuciones para completar la demo; mantener el protocolo y las autorizaciones. |
| PQ-74, PQ-75 | Explicabilidad y comparación competitiva pendientes. | Negociar su prioridad sin presentarlas como terminadas. |
| PQ-85, PQ-86, PQ-96, PQ-97, PQ-98 | Informes, drift, contraparte, logs y procedimientos pendientes. | Ajustar las afirmaciones de cobertura al nivel realmente aceptado. |
| PQ-115, PQ-102 | Servidor compartido y modo presentación pendientes. | Traslado propuesto al MMP, sujeto a consenso. |
| PQ-78, PQ-79, PQ-80 | Spikes y extensiones stretch pendientes. | Su presencia en el sprint no los convierte automáticamente en Must. |

## 9. Aceptación y demostración

Antes de declarar una capacidad entregada deben distinguirse:

1. **Integración:** versión y PR identificados.
2. **Verificación:** pruebas y resultados aplicables a esa versión.
3. **Demostración:** escenario reproducible y recursos disponibles.

Para el MVP se propone preparar una matriz de verificación con:

| Campo | Contenido requerido |
|---|---|
| Historia | Ticket y capacidad que se ofrece. |
| Versión | Commit o versión presentada. |
| Verificación | Prueba, alcance y resultado. |
| Demo | Pasos, datos y servicios necesarios. |
| Limitaciones | Restricciones conocidas y dependencias pendientes. |
| Respaldo | Evidencia alternativa si falla el escenario principal. |

La demostración debe identificar el bróker simulado y separar resultados históricos, simulaciones y operación actual. Cualquier ensayo que ejecute investigación o simulación requiere autorización y tratamiento metodológico correspondiente.

## 10. Matriz de decisiones pendientes Boris–David

| Decisión | Responsable de preparar o confirmar | Acuerdo requerido | Consecuencia |
|---|---|---|---|
| Mantener el MVP original o aceptar la alternativa reducida. | Boris prepara diferencias; David confirma viabilidad del carril operativo. | Boris y David. | Sin acuerdo no se modifica el compromiso ni se comunica la reducción como aprobada. |
| Definir si el 13-nov exige 24/7 o admite demo local. | David. | Ambos. | Determina obligatoriedad de VM, despliegue, respaldo y evidencia de continuidad. |
| Precisar entrega de tendencia: PQ-67, PQ-68 y PQ-82. | Boris. | Ambos. | Evita confundir motor con evaluación o paper; no compromete resultados favorables. |
| Ratificar MoSCoW y diferimientos. | Boris propone; ambos contrastan capacidad. | Ambos. | Fija qué se entrega y qué debe declararse pendiente. |
| Completar `.pbix` y validación de Power BI. | Boris propone responsable; David confirma reparto. | Ambos. | Evita considerar suficientes los materiales preparatorios. |
| Acordar evidencia de verificación y escenario de demo. | Cada responsable aporta su capacidad; ambos revisan el recorrido. | Ambos. | Permite afirmar qué está integrado, verificado y demostrable. |
| Resolver fecha y alcance del MMP. | Ambos contrastan calendario del curso. | Ambos. | Permite fijar entregables y ensayos sin elegir arbitrariamente entre 27-nov y 4-dic. |
| Aprobar y registrar PQ-108. | Boris presenta; David revisa; Boris autoriza el registro al asistente. | Revisión de David y autorización expresa para registrar. | El documento está aprobado por Boris y creado en la rama local feature/PQ-108-mapa-de-historias; quedan pendientes su publicación y la revisión de David. |

## 11. Fuentes y límites

Fuentes consultadas:

- [PQ-108](https://prometheusquant.atlassian.net/browse/PQ-108), historias relacionadas y planificación de Sprint 3/4.
- Estados, integración y revisiones de los PR enlazados.
- Documentación metodológica, runbooks, pre-registros y componentes del repositorio.
- [Funcionalidades diferidas](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/docs/arquitectura/funcionalidades-diferidas.md).

La consulta original corresponde al **9 de noviembre de 2026**. El **10 de noviembre de 2026** se reconsultaron, en modo de solo lectura, los estados de los 86 tickets Jira citados en el documento mediante el MCP oficial de Atlassian, los 24 PR enlazados mediante la conexión de GitHub y las revisiones de los PR #63, #64, #65 y #66. No se comprobaron cambios en esos estados: los PR #64 y #65 siguen aprobados pero abiertos, y los PR #63 y #66 permanecen abiertos con cambios solicitados. Se conservan los estados de las tablas; PQ-108 sigue en Tareas por hacer en Jira, aunque su documento ya está aprobado por Boris y creado localmente. Las fuentes son los tickets y PR enlazados en las tablas. Esta reconsulta no actualiza otras evidencias de la auditoría original ni acredita una nueva verificación funcional u operativa.

No se ejecutaron aplicaciones, pruebas, simulaciones, backtests ni experimentos para elaborar el mapa. No se consultaron datos del holdout.
