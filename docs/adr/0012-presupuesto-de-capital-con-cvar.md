# ADR-0012: presupuesto de capital entre estrategias con tope de CVaR y tope por exchange

- **Estado:** Aceptada
- **Fecha:** 2026-11-21
- **Ticket:** PQ-83

## Contexto y problema

El capítulo 6 optimiza **una** estrategia (el carry H2) contra una stablecoin al 4 %: la fracción en
el carry que maximiza el retorno esperado con un tope de CVaR. Con más de una estrategia (tendencia,
H3) hacen falta tres cosas:

- repartir el capital entre todas sin perder sus **correlaciones**;
- modelar que la quiebra de un exchange golpea a **todas** las estrategias que operan en él a la vez;
- un **tope de capital por exchange**, calibrado con la probabilidad de quiebra de equilibrio del
  capítulo 6.

## Opciones consideradas

1. **Bootstrap conjunto por bloques** de los retornos diarios del desarrollo de las estrategias
   aprobadas, con la quiebra del exchange aplicada en el mismo escenario a todas, y búsqueda en una
   rejilla del símplex.
2. **Extender el modelo de regímenes del capítulo 6** a cada estrategia. Es específico del funding:
   no sirve para la tendencia, y la correlación entre modelos habría que suponerla.
3. **Media-varianza (Markowitz).** Ignora la cola: justo el riesgo de quiebra que aquí manda.

## Decisión

Opción 1, en `portfolio_risk/budget.py` (puro, sin E/S) y `pq research budget` (lee los artefactos):

- **Escenarios:** años de 365 días formados con bloques de 21 días (el bloque del capítulo 6),
  **comunes a todas las estrategias**, sacados de sus retornos diarios del desarrollo (antes de
  `HOLDOUT_START`, KE-014). Así se conservan la correlación y las rachas.
- **Quiebra:** cada exchange quiebra con su probabilidad anual (2 %, el escenario moderado del
  capítulo 6) y todas sus estrategias pierden el 100 % ese año.
- **Optimización:** rejilla del 5 % sobre el símplex. El resto queda en efectivo al 4 %. Se maximiza
  el retorno esperado con `CVaR95 ≤ 5 %` (el tope del capítulo 6) y cada exchange bajo su tope; un
  empate se resuelve a favor de más efectivo. Es exacta en la rejilla y fácil de auditar. Con pocas
  estrategias es barata (21 puntos con una, 231 con dos).
- **Tope por exchange:** la mayor fracción `x` cuya quiebra, **por sí sola**, no supere el
  presupuesto de CVaR. Con una probabilidad `p < 5 %`, la quiebra ocupa `p / 5 %` de la cola y su
  CVaR95 es `x · p / 0,05`, así que `x ≤ 0,05 · 0,05 / p`. Se usa `p = max(p supuesta, p de
  equilibrio)`: con las cifras de hoy (2 % y 0,40 %) el tope es el 12,5 %.
- **Aprobada** significa que pasa los cuatro gates del desarrollo. No es lo mismo que pasar el
  holdout: el presupuesto se recalcula cuando cambien las evaluaciones.

## Consecuencias

- **Positivas:**
  - Una estrategia nueva entra al presupuesto con solo dejar su `summary.json` y sus retornos
    diarios.
  - La correlación y el riesgo de quiebra compartido se modelan, no se suponen.
- **Negativas y riesgos:**
  - **Con las cifras de hoy el presupuesto da 0 % al carry H2 y 100 % al efectivo** (`pq research
    budget`, 21-nov-2026). Con quiebra al 2 %, el carry rinde menos que la stablecoin en esperanza,
    como ya decía el capítulo 6. Sin quiebra, el máximo sería el 10 % (por el tope de 12,5 % en la
    rejilla del 5 %).
  - El bootstrap solo repite el pasado del desarrollo: no inventa regímenes que no ocurrieron.
  - La rejilla crece como `C(20 + k, k)`. Con más de 4 estrategias haría falta un optimizador
    continuo.
- **Pendiente de decisión del titular:** si el runner de **paper** debe aplicar este presupuesto (y
  dejar de operar el carry) o solo hacerlo cumplir como tope cuando se configure. Afecta a la demo en
  vivo de la feria. Mientras tanto el runner no cambia de comportamiento.
- **Qué la revertiría:** suficientes estrategias para que la rejilla no escale, o un modelo de cola
  del exchange mejor calibrado que una probabilidad anual fija.
