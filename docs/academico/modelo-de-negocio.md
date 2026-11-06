# PrometheusQuant — Modelo de negocio y viabilidad económica preliminar

**Proyecto Integrador · Capítulo 8 (competencia, Canvas, costes y ROI)**  
**Estado:** plan aprobado en Jira; documento presentado para revisión de código.  
**Fecha:** 2026-11-06.  
**Épica relacionada:** PQ-10. **Ticket:** PQ-44 (asignado a Boris Igor Miranda Prieto).

## 1. Resumen ejecutivo

PrometheusQuant es, en su fase actual, una **plataforma de investigación y evaluación cuantitativa para el equipo**, no un servicio financiero ofrecido al público. Su valor diferencial consiste en transformar ideas de trading en decisiones reproducibles: datos históricos con controles temporales, hipótesis pre-registradas, backtests con costes, pruebas contra el sobreajuste, simulaciones de riesgo y evidencia auditable.

El principal resultado económico no es una promesa de ganancias, sino la posibilidad de **descartar estrategias no suficientemente robustas antes de poner en riesgo capital propio**. La viabilidad de una eventual actividad comercial se mantiene abierta, condicionada a evaluación legal, comercial y tecnológica.

## 2. Problema y propuesta de valor

**Problema:** los inversores e investigadores minoristas pueden sobreestimar la rentabilidad de un algoritmo por seleccionar retrospectivamente parámetros, usar información futura, ignorar comisiones o modelar de manera insuficiente eventos extremos.

**Propuesta de valor:** una plataforma que reúne ingeniería de datos, investigación, validación económica y controles de riesgo en un flujo trazable: *formular → experimentar → medir neto de costes → decidir → simular → monitorizar*.

**Beneficiarios iniciales:** equipo investigador, operador de capital propio y evaluador académico. **No se presume una cartera de clientes de pago ni ingresos comerciales actuales.**

## 3. Business Model Canvas — versión inicial

| Bloque | Contenido propuesto |
|---|---|
| **1. Segmentos de usuarios** | Equipo cuantitativo que usa capital propio; investigadores y evaluadores académicos. Eventuales usuarios externos son una hipótesis futura sujeta a habilitación legal. |
| **2. Propuesta de valor** | Investigación reproducible, prevención del sobreajuste, comparación neta de costes, control del riesgo y documentación verificable. |
| **3. Canales** | Repositorio GitHub, sitio de documentación, dashboard local y presentación académica. No se identifican canales de comercialización en la fase actual. |
| **4. Relación con usuarios** | Trabajo colaborativo mediante tickets de Jira, revisión de cambios, manuales y reportes reproducibles. |
| **5. Fuentes de valor/ingresos** | **Hoy:** aprendizaje, evidencia académica y decisiones más informadas para capital propio; no ingresos recurrentes confirmados. **Futuro hipotético:** licencias o servicios solo después de evaluar demanda y requisitos normativos. |
| **6. Recursos clave** | Código Python, fuentes de datos históricos, documentación de estrategias, experimentos y tiempo especializado del equipo. |
| **7. Actividades clave** | Ingesta y depuración de datos, experimentación, backtesting, validación estadística, gestión de riesgo, pruebas de software y documentación. |
| **8. Socios/proveedores clave** | Proveedores de datos y acceso a mercado, herramientas abiertas y servicios de infraestructura. No se afirma que existan alianzas contractuales. |
| **9. Estructura de costes** | Tiempo de desarrollo/investigación, electricidad y equipo local, infraestructura opcional, comisiones de negociación y riesgos financieros. |

## 4. Alternativas y competencia funcional

La comparación se hace por **función**, no como afirmación de cuota de mercado ni de precios actuales.

| Alternativa | Ventaja para el usuario | Limitación frente al objetivo de PrometheusQuant |
|---|---|---|
| Análisis manual en hojas de cálculo | Bajo coste inicial y comprensión directa | Mayor esfuerzo de reproducción, validación temporal y auditoría de experimentos |
| Notebooks aislados de Python | Flexibilidad para probar ideas | Pueden carecer de contratos de arquitectura, control de versiones y validación integral |
| Plataformas comerciales de backtesting | Interfaces, datos y ejecución integrados según proveedor | Dependencia externa, restricciones de personalización y posibles costes de suscripción |
| Bots de trading de terceros | Puesta en marcha potencialmente rápida | Transparencia limitada sobre hipótesis, pruebas, costes, riesgo y control del código |
| **PrometheusQuant** | Proceso controlado, modular, auditable y adaptado al capital propio | Alta carga de desarrollo para un equipo pequeño; estrategia y ejecución en vivo aún no consolidadas |

**Posicionamiento recomendado para la defensa:** presentar el proyecto como una plataforma científica de decisión y control de riesgo, no como un producto que garantiza rentabilidad superior.

## 5. Estructura económica y supuestos de evaluación

### 5.1 Costes observables y costes por estimar

| Categoría | Tratamiento inicial | Estado de verificación |
|---|---|---|
| Infraestructura en la nube | Presupuesto objetivo del ADR-0001: **0 a 20 USD/mes** | Es una restricción de diseño, no una factura real |
| Hardware local | Reutilización de equipo existente | Coste incremental no calculado |
| Horas de desarrollo | Horas del equipo × valor de hora de oportunidad | A estimar; no tratar como coste cero en el ROI económico |
| Comisiones y deslizamiento | Incorporadas a backtests; sensibilidad con comisiones del exchange | Tarifas reales de la cuenta pendientes de confirmación en PQ-17 |
| Servicios externos | Datos históricos públicos y software abierto cuando sea posible | Verificar licencias y condiciones vigentes |
| Riesgo de contraparte | Escenarios de pérdida ante quiebra o indisponibilidad del exchange | Es una hipótesis de simulación, no una tasa histórica verificada |

### 5.2 Fórmulas de evaluación

Para una comparación anual simplificada con la misma base de capital:

\[
V_{neto}=C(r_P-r_B)-12M-H
\]

Donde: \(C\) = capital; \(r_P\) = retorno anual esperado de la estrategia según un escenario; \(r_B\) = retorno del benchmark bajo su propia hipótesis; \(M\) = gasto incremental mensual de infraestructura; \(H\) = valor anual del tiempo y otros costes no incorporados.

Una medida de rendimiento incremental sobre el capital es:

\[
ROI_{incremental}=\frac{V_{neto}}{C}
\]

No debe interpretarse como rentabilidad futura garantizada. El resultado depende de supuestos de mercado, financiación, riesgo y costes.

## 6. Escenarios económicos ilustrativos basados en el research del carry

El informe del ticket **PQ-33** documenta 10.000 años simulados con una estrategia H2, manteniendo cerrado el holdout final. El benchmark de 4 % anual en stablecoin es **un supuesto del estudio**, no una tasa libre de riesgo ni una recomendación.

Para facilitar la lectura, calculamos valores ilustrativos con \(C=1.000\) USD y **sin incluir** trabajo, impuestos ni infraestructura:

| Escenario del estudio | Retorno medio anual simulado | Resultado anual sobre USD 1.000 | Diferencia frente al benchmark hipotético de 4 % |
|---|---:|---:|---:|
| Carry sin quiebra del exchange | 4,41 % | USD 44,10 | **+USD 4,10** |
| Carry con quiebra supuesta del 2 % anual | 2,15 % | USD 21,50 | **−USD 18,50** |
| Carry con quiebra supuesta del 5 % anual | −0,95 % | −USD 9,50 | **−USD 49,50** |
| Benchmark hipotético del estudio | 4,00 % | USD 40,00 | Referencia |

**Interpretación:** con capital pequeño, incluso una diferencia favorable de 0,41 puntos porcentuales equivale a solo 4,10 USD anuales por cada 1.000 USD. Un gasto operativo incremental de 10 USD/mes (120 USD/año) excedería ampliamente esa ventaja. Bajo el escenario supuesto de quiebra del 2 %, el research del equipo concluye que la asignación óptima al carry es 0 % cuando se exige CVaR 95 % ≤ 5 %.

**Limitaciones:** la comparación no modela el riesgo de *depeg* ni de contraparte de la stablecoin; el escenario de quiebra es una hipótesis de sensibilidad; los resultados históricos o simulados no pronostican retornos reales.

### 6.1 Capital de equilibrio, condicionado a supuestos

Si la ventaja anual neta fuera positiva y constante (\(r_P>r_B\)), el capital mínimo teórico para cubrir solo infraestructura sería:

\[
C^*=\frac{12M}{r_P-r_B}
\]

Con \(M=10\) USD/mes y una ventaja **hipotética** de 0,41 puntos porcentuales, se obtiene \(C^*\approx 29.268\) USD. Esta cifra es únicamente una sensibilidad aritmética, no un objetivo de inversión: omite tiempo de trabajo, impuestos, escalabilidad, costes y cambios de comportamiento del mercado.

## 7. Conclusión de viabilidad y ruta futura

1. **Viabilidad técnica/académica:** existe evidencia en GitHub de ingeniería de datos, backtesting, simulación, dashboard y reporte reproducible. El valor principal actual está en el proceso y la formación de capacidades.
2. **Viabilidad financiera para capital menor a 1.000 USD:** la evidencia disponible **no demuestra** una ventaja económica suficientemente amplia y robusta del carry que justifique operar con capital real bajo los supuestos de riesgo evaluados.
3. **Viabilidad comercial:** no está demostrada. Se requieren investigación de demanda, análisis regulatorio vigente, costes reales y validación de un modelo de ingresos antes de prometer licencias o servicios a terceros.
4. **Decisión preliminar:** continuar investigación y pruebas controladas; conservar el capital real fuera del alcance operativo mientras no se cumplan los gates del proyecto.

## 8. Indicadores para seguimiento

| Perspectiva | Indicador | Interpretación |
|---|---|---|
| Económica | Diferencial de retorno neto frente a benchmark | Determina si hay ventaja después de costes |
| Riesgo | CVaR 95 %, drawdown y exposición por exchange | Evalúa pérdidas extremas y concentración |
| Estadística | DSR, PBO y número de ensayos registrados | Identifica riesgo de sobreajuste |
| Técnica | Pruebas y cobertura, CI y reproducibilidad | Permite confiar en el software y repetir los resultados |
| Negocio | Coste mensual, horas de trabajo, coste por experimento | Permite evaluar eficiencia y sostenibilidad |

## 9. Fuentes internas y verificación pendiente

- [`README.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/README.md): alcance y aviso de investigación.
- [`docs/academico/README.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/academico/README.md): ítems del capítulo 8.
- [`docs/academico/marco-de-referencia.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/academico/marco-de-referencia.md): contexto económico, PESTEL y cautelas normativas.
- [`docs/adr/0001-monolito-modular-hexagonal.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/adr/0001-monolito-modular-hexagonal.md): presupuesto inicial y arquitectura.
- [`docs/adr/0005-orden-de-estrategias.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/adr/0005-orden-de-estrategias.md): prioridades y capital inicial.
- [`docs/investigacion/2026-11-05-simulacion-carry.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/investigacion/2026-11-05-simulacion-carry.md): escenarios, resultados y limitaciones.
- [`docs/compliance/README.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/main/docs/compliance/README.md): comprobaciones pendientes de acceso y tributación.

**Pendientes antes de uso operativo o comercial:** corroborar costes reales y productos habilitados en la cuenta (PQ-17), obtener criterio tributario profesional (PQ-27) y examinar requisitos normativos vigentes con fuentes primarias.

## 10. Criterios de aceptación propuestos para Jira

- [x] Problema, propuesta de valor y beneficiarios definidos.
- [x] Canvas de nueve bloques elaborado.
- [x] Competencia funcional y posicionamiento comparados.
- [x] Estructura de costes y fórmulas económicas expuestas.
- [x] Sensibilidad y limitaciones conectadas a evidencia de PQ-33.
- [x] Aprobación del plan de implementación por el compañero en Jira.
- [ ] Revisión y aprobación del PR.
- [ ] Integración en `develop` con CI satisfactoria.
