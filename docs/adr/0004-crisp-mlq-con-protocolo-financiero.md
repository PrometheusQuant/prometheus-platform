# ADR-0004: CRISP-ML(Q) con protocolo financiero de control de calidad

- **Estado:** Aceptada
- **Fecha:** 2026-10-16

## Contexto y problema

El mayor riesgo de un sistema de trading no es técnico sino estadístico: con muchas pruebas sobre
pocos datos es fácil encontrar una estrategia que brilla en el backtest y fracasa en vivo.

## Opciones consideradas

1. CRISP-DM.
2. TDSP / modelos de madurez MLOps.
3. **CRISP-ML(Q) (Studer et al., 2021) + protocolo financiero.**

## Decisión

Opción 3. CRISP-ML(Q) es el único de los marcos comparados que define riesgos y métodos de QA por
tarea, e incluye monitoreo y mantenimiento. Como no trata la no-estacionariedad ni las pruebas
múltiples, se le añaden como métodos de QA:

- Protocolo de Arnott, Harvey y Markowitz (2019): hipótesis económica ex ante y registro de todo lo probado.
- Validación cruzada purgada con embargo y CPCV (López de Prado, 2018).
- Deflated Sharpe Ratio (Bailey y López de Prado, 2014) y PBO (Bailey et al.).
- Umbral t > 3 (Harvey, Liu y Zhu).
- Holdout final de **un solo uso** por estrategia, registrado con fecha, commit y autor.

Scrum (sprints de 2 semanas) marca el ritmo; cada hipótesis es un ciclo PDCA.
Los gates concretos están en [la Definición de Terminado](../metodologia/definicion-de-listo-y-terminado.md).

## Consecuencias

- Positivas: resultados defendibles ante un jurado y ante uno mismo antes de arriesgar capital.
- Negativas: más trabajo por estrategia; muchas hipótesis se descartarán.
