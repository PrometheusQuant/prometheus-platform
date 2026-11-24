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

Generados con `uv run pq research stats` (resultados en `data/research/stats/summary.json`). B1
recalculado coincide con la evaluación: el Sharpe es el mismo hasta 10⁻⁶; si no lo fuera, el
comando se detiene.

### 6.1 Supuestos (§3)

**Ninguna de las 10 series cumple normalidad ni independencia.**

- Jarque-Bera da p < 10⁻¹⁵ en todas.
- Ljung-Box(10) da p < 10⁻¹¹ en todas.
- Levene rechaza la igualdad de varianzas (p < 10⁻³⁸).
- `k9-theta20` tiene asimetría 2,91 y exceso de curtosis 21,3. B1 tiene −8,80 y 463.

Por eso, como estaba previsto, deciden las pruebas robustas: HAC, bootstrap de bloques, Wilcoxon y
Friedman.

### 6.2 HE1: ¿la política optimizada supera a B1?

| Medida | Valor |
|---|---|
| Diferencia media anualizada (`k9-theta20` − B1) | **+2,36 %** |
| t con HAC (rezago 7) | 1,706 → **p = 0,044** |
| IC 95 % bootstrap de la diferencia anualizada | **[+0,19 %, +5,65 %]** |
| Wilcoxon unilateral (robustez) | p = 0,005 |
| d de Cohen pareada | 0,03 |

**Decisión: se rechaza H0.** Se cumplen las dos condiciones de la regla: p < 0,05 y el IC excluye
el cero. La política optimizada rinde más que el carry siempre activo, pero **por poco**:

- el valor p está cerca del umbral;
- el límite inferior del IC es de apenas +0,19 % anual;
- el efecto por día es muy pequeño (d = 0,03).

La mejora viene más de **evitar las pérdidas** de B1 (su máximo drawdown fue −11,2 % y el de la
política, −0,4 %) que de ganar más cada día.

### 6.3 HE2: ¿supera al hurdle de la stablecoin (4 %)?

| Medida | Valor |
|---|---|
| Retorno medio anualizado | 4,91 % (hurdle 4,00 %) |
| t con HAC frente al hurdle | 1,055 → **p = 0,146** |
| IC 95 % bootstrap del exceso anual | **[−1,17 %, +3,42 %]** |
| Wilcoxon unilateral | p = 1,0 |

**Decisión: no se rechaza H0.** La política rinde en promedio más que el 4 %, pero la diferencia
**no es distinguible del ruido**: el IC incluye el cero.

El Wilcoxon de p = 1,0 tiene una explicación concreta. La política está fuera de posición la mayor
parte del tiempo (73 %; invierte el 27,2 % del tiempo según la evaluación), y esos días rinde 0, menos que el 0,011 % diario de la stablecoin. Su
ventaja está en pocos días buenos, no en el día típico.

**Lectura honesta:** el gate G4 («CAGR > 4 %») se cumplió en el desarrollo, pero esta prueba muestra
que **ese margen no es estadísticamente sólido**. Es una razón más para que la decisión final la
tome el holdout (PQ-50).

### 6.4 HE3: ¿importan los parámetros de la política?

| Prueba | Resultado |
|---|---|
| ANOVA de una vía (referencia; supuestos no cumplidos) | F = 1,34, p = 0,208, η² = 0,0007 |
| **Friedman** (decide) | χ² = 187,3, **p < 10⁻³⁴**, W de Kendall = 0,013 |

**Decisión: se rechaza H0.** Las 10 políticas no tienen la misma distribución de retornos diarios,
aunque el tamaño del efecto es muy pequeño (W = 0,013).

El ANOVA no lo detecta, por la misma razón que no sirve aquí: compara medias con varianzas enormes y
desiguales, y supone independencia. Friedman compara las políticas **dentro de cada día**.

**Post-hoc: cada configuración contra B1, Wilcoxon bilateral con corrección de Holm**

| Configuración | Diferencia anual | p | p (Holm) |
|---|---|---|---|
| k9-theta20 (elegida) | +2,36 % | 0,010 | 0,072 |
| k3-theta20 | +2,16 % | 0,059 | 0,228 |
| k21-theta20 | +2,06 % | 0,057 | 0,228 |
| k9-theta10 | +1,82 % | 0,009 | 0,071 |
| k21-theta30 | +1,55 % | 0,417 | 0,723 |
| k21-theta10 | +1,55 % | 0,013 | 0,076 |
| k9-theta30 | +1,46 % | 0,361 | 0,723 |
| k3-theta30 | +0,70 % | 0,025 | 0,124 |
| **k3-theta10** | **−0,24 %** | 0,002 | **0,017** |

Corregido por las 9 comparaciones, solo `k3-theta10` difiere de B1, y lo hace **para peor**. El
umbral más bajo (θ = 10 %) con la señal más corta (k = 3) entra y sale demasiado.

**Por qué HE1 sí rechaza y la fila de `k9-theta20` aquí no:**
- **HE1** es la comparación principal y fijada de antemano: una sola prueba, unilateral.
- **El post-hoc** es exploratorio: bilateral y corregido por 9 comparaciones.

Las dos lecturas son coherentes: la mejora existe, pero es pequeña, y no sobrevive a una corrección
por comparaciones múltiples.

### 6.5 Sensibilidad: sin el día frontera (KE-014)

El último retorno del desarrollo incluye la liquidación del 2024-07-01 00:00, que es del holdout
([KE-014](../runbooks/errores-conocidos.md)). Sin ese día, ninguna decisión cambia:

| | Con el día | Sin el día |
|---|---|---|
| HE1 (p HAC) | 0,0441 → rechaza | 0,0442 → rechaza |
| HE2 (p HAC) | 0,1458 → no rechaza | 0,1452 → no rechaza |
| HE3 (Friedman) | p < 10⁻³⁴ → rechaza | p < 10⁻³⁴ → rechaza |

## 7. Conclusión para el capítulo 7.4

1. **La optimización tiene un impacto estadísticamente significativo frente a la línea base (HE1),
   aunque pequeño.** Su valor principal es el control del riesgo: menos drawdown y menos cola
   izquierda.
2. **El exceso sobre la stablecoin no es significativo (HE2).** Con estos datos no se puede afirmar
   que el carry rinda más que el 4 % sin riesgo de contraparte. Esto coincide con el capítulo 6:
   con un 2 % anual de probabilidad de quiebra del exchange, la media cae al 2,15 %.
3. **Los parámetros importan (HE3), pero ninguna configuración supera a B1 tras corregir por
   comparaciones múltiples.** Solo una es claramente peor.
4. Todo esto es **dentro de la muestra y con sesgo de selección**. La prueba confirmatoria es el
   holdout (PQ-50), que se abre una sola vez.
