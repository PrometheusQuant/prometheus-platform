# Validación estadística del impacto de la optimización (cap. 7.4)

- **Ticket:** PQ-48 · **Fecha:** 2026-11-06 · **Épica:** PQ-9
- **Pregunta:** ¿la política de entrada optimizada del carry (H2, `k9-theta20`) mejora de forma
  estadísticamente significativa frente a la línea base, o la diferencia puede ser ruido?
- **Estado:** hipótesis y plan fijados **antes** de calcular (este commit). Los resultados se
  agregan en un commit posterior, sin cambiar nada de lo que sigue.

## 1. Datos

- **Periodo:** desarrollo de H2 (SOL, BNB y XRP), del 2020-01-03 al 2024-07-01: 1.642 retornos
  diarios netos de costes, los mismos de la [evaluación](../estrategias/01-carry/evaluacion.md).
  **El holdout no se toca.**
- **Política optimizada:** `k9-theta20`, la configuración que eligió la CPCV.
- **Línea base B1:** carry siempre activo, el benchmark del pre-registro (§6). Sus retornos diarios
  se recalculan con la misma función de la evaluación (`run_config` con `always_on`). No es un
  ensayo nuevo y N no cambia.
- **Hurdle:** stablecoin al 4 % anual, es decir 0,04 / 365 por día.
- **Grid:** las 9 configuraciones pre-registradas (k ∈ {3, 9, 21} × θ ∈ {10, 20, 30} %) más B1.

## 2. Hipótesis (fijadas antes de calcular)

| | Hipótesis nula (H0) | Alternativa (H1) | Pruebas |
|---|---|---|---|
| **HE1** | El retorno diario medio de `k9-theta20` es **menor o igual** que el de B1 | Es mayor | t pareada unilateral con error estándar HAC (Newey-West); Wilcoxon de rangos con signo unilateral; IC 95 % por bootstrap de bloques |
| **HE2** | El retorno diario medio de `k9-theta20` es **menor o igual** que el hurdle diario | Es mayor | t de una muestra unilateral con HAC; IC 95 % por bootstrap de bloques |
| **HE3** | Las 10 políticas (9 configuraciones y B1) tienen la **misma** distribución de retornos diarios | Al menos una difiere | ANOVA de una vía (la que pide el curso); Friedman (medidas repetidas: los días son bloques); post-hoc de Wilcoxon de cada configuración contra B1 con corrección de Holm |

**Regla de decisión, fijada de antemano:** α = 0,05.
- **HE1 y HE2:** se rechaza H0 solo si **las dos condiciones** se cumplen: el valor p de la prueba t con HAC es menor que 0,05, **y** el IC 95 % del bootstrap excluye el cero. Wilcoxon se informa como robustez.
- **HE3:** la conclusión se toma con **Friedman**. El ANOVA se informa, pero sus supuestos de independencia y normalidad no se cumplen en series diarias del mismo periodo (ver §3).

## 3. Supuestos que se verifican, y qué se hace si fallan

| Supuesto | Prueba | Si falla |
|---|---|---|
| Normalidad | Jarque-Bera | Se apoya la conclusión en Wilcoxon, Friedman y el bootstrap, que no la asumen |
| Homocedasticidad entre políticas | Levene (mediana) | Ídem: el ANOVA queda solo como referencia |
| Independencia en el tiempo | Ljung-Box con 10 rezagos | Errores HAC de Newey-West (rezago ⌊4 (T/100)^{2/9}⌋) y bootstrap circular de bloques de 21 días |
| Independencia entre políticas | — (no se cumple por diseño: mismos días) | Pruebas pareadas y de medidas repetidas (t pareada, Wilcoxon, Friedman) |

## 4. Tamaño del efecto

Además de los valores p se informan:
- la diferencia de retorno medio **anualizada** (× 365) con su IC 95 %;
- la d de Cohen pareada (d_z);
- η² para el ANOVA;
- la W de Kendall para Friedman.

**Bootstrap:** 10.000 réplicas, bloques circulares de 21 días (la duración de los regímenes del cap. 6) y semilla 2026.

## 5. Limitaciones declaradas de antemano

- **Sesgo de selección.** `k9-theta20` se eligió entre 9 configuraciones con estos mismos datos, así que los valores p de HE1 y HE2 son optimistas. El ajuste por número de ensayos ya lo hace el Deflated Sharpe (gate G1, N = 20). Estas pruebas no lo reemplazan: miden si la diferencia es distinguible del ruido dentro de la muestra.
- **La prueba confirmatoria es el holdout** (PQ-50), que se evalúa una sola vez. Este análisis no lo anticipa ni lo sustituye.
- Las colas pesadas (curtosis de 24 en `k9-theta20`, según la evaluación) hacen que el bootstrap y las pruebas no paramétricas sean más fiables que la t clásica.

## 6. Resultados

*Pendiente: se agregan en el commit siguiente, generados por `uv run pq research stats`.*
