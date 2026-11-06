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

### 6.2 Costes cotizados y evaluación financiera (PQ-49)

> **Agregado por PQ-49.** Completa las secciones 5 y 6 con precios cotizados en sus fuentes y con
> el VAN, la TIR y el capital de equilibrio calculados por código. Las tablas siguientes las genera
> `uv run pq research finance --update-doc docs/academico/modelo-de-negocio.md` a partir de los
> escenarios del capítulo 6. No se editan a mano.

**Cómo se plantea la decisión.**
- **La comparación es incremental:** poner un capital C en el carry en lugar de dejarlo en la stablecoin
  al 4 %, que es el benchmark del pre-registro y también la tasa de descuento (costo de
  oportunidad del capital).
- **La fórmula es la de la sección 5.2:** flujo anual = C·(r_P − r_B) − costes de operación. La
  inversión inicial es la puesta en marcha del despliegue.
- **El desarrollo ya realizado es un costo hundido**, así que no entra en la decisión de operar.

<!-- PQ-49:inicio (generado por `uv run pq research finance --update-doc`) -->

**Fecha de cotización:** 2026-11-06. **Tasa de descuento y benchmark:** 4,0 % anual (stablecoin).

#### Costes cotizados (8.3)

| Concepto | USD/mes | Fuente | Verificado |
|---|---:|---|---|
| Laptop propia (solo durante la demo) | 0,00 | equipo existente (2026-11-06) | sí |
| Oracle Cloud Always Free (Ampere A1, 2 OCPU y 12 GB) | 0,00 | <https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm> (2026-11-06) | sí |
| Hetzner Cloud Cost-Optimized (plan más barato) | 6,69 | <https://www.hetzner.com/cloud/> (2026-11-06) | sí |
| Dominio .com en Cloudflare Registrar (opcional) | 0,93 | <https://costgoat.com/compare/domains/com> (2026-10-20) | **por verificar** |

- **Horas del equipo:** 1,16 USD/h (salario mínimo nacional 2026 (DS 5516) / 240 h / TCO del BCB). Es un piso: el costo de
  oportunidad real de un analista es mayor. Las horas de operación (8 h/mes) y de puesta en marcha (16 h) son **supuestos declarados**.
- **Comisiones y slippage de Binance:** ya están dentro de los retornos simulados (VIP 0, [compliance](../compliance/binance.md)); las reales se confirman en PQ-17.
- **Desarrollo ya realizado:** costo hundido; no entra en la decisión de operar.

#### Evaluación con Oracle Cloud Always Free (Ampere A1, 2 OCPU y 12 GB) (8.4)

Flujo anual = C·(r_P - 4 %) - costes de operación. VAN a 1 y 3 años; TIR sobre la puesta en marcha; capital de equilibrio = capital mínimo con VAN = 0.

| Escenario (cap. 6) | r_P medio | Capital | VAN 1 año | VAN 3 años | TIR 3 años |
|---|---:|---:|---:|---:|---:|
| sin quiebra del exchange | 4,4 % | 500 USD | -123 USD | -321 USD | no existe |
| sin quiebra del exchange | 4,4 % | 1.000 USD | -121 USD | -315 USD | no existe |
| sin quiebra del exchange | 4,4 % | 5.000 USD | -105 USD | -269 USD | no existe |
| sin quiebra del exchange | 4,4 % | 10.000 USD | -85 USD | -211 USD | no existe |
| quiebra con p = 2% anual | 2,2 % | 500 USD | -134 USD | -352 USD | no existe |
| quiebra con p = 2% anual | 2,2 % | 1.000 USD | -143 USD | -378 USD | no existe |
| quiebra con p = 2% anual | 2,2 % | 5.000 USD | -214 USD | -583 USD | no existe |
| quiebra con p = 2% anual | 2,2 % | 10.000 USD | -303 USD | -840 USD | no existe |
| quiebra con p = 5% anual | -1,0 % | 500 USD | -149 USD | -395 USD | no existe |
| quiebra con p = 5% anual | -1,0 % | 1.000 USD | -173 USD | -464 USD | no existe |
| quiebra con p = 5% anual | -1,0 % | 5.000 USD | -363 USD | -1.014 USD | no existe |
| quiebra con p = 5% anual | -1,0 % | 10.000 USD | -601 USD | -1.701 USD | no existe |

**Capital de equilibrio (VAN = 0) por infraestructura, a 3 años**

| Escenario | Laptop propia (solo durante la demo) | Oracle Cloud Always Free (Ampere A1, 2 OCPU y 12 GB) | Hetzner Cloud Cost-Optimized (plan más barato) |
|---|---:|---:|---:|
| sin quiebra del exchange | 28.368 USD | 28.368 USD | 47.714 USD |
| quiebra con p = 2% anual | no existe | no existe | no existe |
| quiebra con p = 5% anual | no existe | no existe | no existe |

**Sensibilidad a la tarifa horaria** (escenario sin quiebra del exchange, Oracle, 3 años). Las horas de operación son el costo dominante; sin valorarlas, cualquier capital tiene VAN positivo:

| Tarifa | USD/h | Capital de equilibrio |
|---|---:|---:|
| horas no valoradas | 0,00 | 0 USD |
| salario mínimo (fuente oficial) | 1,16 | 28.368 USD |
| supuesto ilustrativo | 5,00 | 122.654 USD |

**Rango de un año (p5 a p95 del Monte Carlo), por cada 1.000 USD frente a la stablecoin:**

| Escenario | Peor año (p5) | Año medio | Buen año (p95) |
|---|---:|---:|---:|
| sin quiebra del exchange | -47 USD | 4 USD | 91 USD |
| quiebra con p = 2% anual | -49 USD | -18 USD | 91 USD |
| quiebra con p = 5% anual | -1.040 USD | -50 USD | 90 USD |

<!-- PQ-49:fin -->

**Lectura.**
- **Con los costes cotizados, el carry no compensa en ninguno de los capitales evaluados
  (500 a 10.000 USD).** El VAN es negativo en los tres escenarios y no hay TIR, porque el flujo
  anual es negativo.
- **El costo dominante no es la infraestructura**, que es gratuita en Oracle, sino **las horas de
  operación**. Aun valoradas al salario mínimo, superan la ventaja esperada sobre la stablecoin
  para capitales pequeños.
- **El capital de equilibrio solo existe sin quiebra del exchange.** Con una probabilidad de quiebra
  del 2 % o del 5 % anual, el retorno esperado queda por debajo del 4 % y ningún capital compensa.
  Es la misma conclusión del capítulo 6, que da la asignación óptima de 0 % al carry con CVaR ≤ 5 %.

Dos resultados del capítulo 7.4
([validación estadística](../investigacion/2026-11-06-validacion-estadistica.md)) refuerzan esa
cautela:
- el exceso del carry sobre el 4 % **no es estadísticamente significativo**;
- el rango de un año (p5 a p95) va de perder a ganar en todos los escenarios.

**Conclusión del capítulo 8.4.** Con capital propio menor de 10.000 USD, el carry **no es viable
como fuente de ingreso**. Su valor está en el proceso: datos, validación, simulación y control de
riesgo, reutilizables para las estrategias siguientes. La decisión final sobre H2 la toma el
holdout (PQ-50) con las comisiones reales (PQ-17), que podrían empeorar estas cifras.

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
