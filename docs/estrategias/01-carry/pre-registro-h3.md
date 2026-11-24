# Estrategia 1 · H3: carry con la señal del clasificador de régimen (ML): pre-registro

- **Ticket:** PQ-69 · **Épica:** PQ-5 · **Fase CRISP-ML(Q):** 1 (negocio y datos)
- **Fecha de registro:** 2026-11-21
- **Estado:** registrado, **antes de cualquier backtest de H3**
- **Relación:** variante del [pre-registro del carry](pre-registro.md) (H1 y H2). Todo lo que este
  documento no cambia se rige por aquel, con sus enmiendas 1 y 2 y la corrección de KE-014 y KE-016
  (PQ-66).

!!! warning "Por qué H3 necesita su propio pre-registro"
    El clasificador del capítulo 5 tiene un AUC de **0,977** frente a **0,882** de la regla S₉ en el
    periodo de desarrollo (`data/research/funding_model/residual/summary.json`). Cambiar la regla de
    H2 por el modelo **después de ver eso** sería elegir con los datos. Por eso H3 es una hipótesis
    nueva, con su rejilla, su N y su propio uso del holdout.

## 1. Hipótesis

**H3.** En el universo de H2 (SOLUSDT, BNBUSDT y XRPUSDT), la misma posición delta-neutral de H2
(spot largo y perpetuo corto, 1x), **abierta cuando el clasificador estima una probabilidad alta de
que la próxima liquidación supere el 20 % anualizado**, obtiene neta de costes un Sharpe **mayor que
el de H2** (k = 9, θ = 20 %, la configuración elegida por CPCV) y que el carry siempre activo, y una
rentabilidad mayor que el yield de una stablecoin.

**Hipótesis nula.** La señal del clasificador no mejora a H2 neta de costes: la diferencia diaria
media entre H3 y H2 no es positiva.

## 2. Mecanismo económico

- El carry de H2 entra cuando la media reciente del funding ya es alta. El clasificador usa además
  el basis, la volatilidad, el retorno del precio y los rezagos del funding, que anticipan el cambio
  de régimen antes que la media (capítulo 5, importancia por permutación en validación, PQ-74).
- **Por qué podría fallar.**
  - Un AUC alto en clasificación no garantiza más retorno: el carry gana sobre todo en las rachas
    largas de funding alto, que la regla S₉ ya captura.
  - Los aciertos pueden concentrarse en liquidaciones que no cambian la decisión.
  - El reentrenamiento añade ruido a las entradas y salidas, y la rotación se paga en costes.

## 3. Datos

Los mismos del carry (§3), en el universo de H2 desde la fecha de inicio de cada símbolo. Las
features son las del capítulo 5 (`research/funding_model.FEATURES`), todas point-in-time, calculadas
con datos con `knowledge_time ≤ t`.

## 4. Reglas de la estrategia

**Etiqueta.** En la liquidación *t*, `alto(t) = 1` si la **siguiente** liquidación anualizada es
≥ 20 % (`THRESHOLD` del capítulo 5, el mismo θ de H2).

**Modelo.** Bosque aleatorio del capítulo 5 (`n_estimators = 100`, `random_state = 42`), entrenado
con el panel combinado de los cinco símbolos del carry (H1 y H2), como en el capítulo 5.

**Walk-forward sin fuga** (lo exige el ticket):

1. El modelo se **reentrena cada 90 días** con ventana creciente, desde el inicio de los datos.
2. En la fecha de reentrenamiento *r*, una fila solo entra al entrenamiento si **su etiqueta ya se
   conocía en *r***, es decir, si la liquidación siguiente ocurrió antes de *r*. Así ninguna fila de
   entrenamiento usa información posterior a *r*.
3. Los hiperparámetros se eligen **en cada reentrenamiento**, con `GridSearchCV` sobre el pasado
   de *r* (la misma rejilla del capítulo 5: `max_depth` ∈ {4, 8}, `min_samples_leaf` ∈ {20, 100}),
   validación `TimeSeriesSplit(3)` con hueco de 15 liquidaciones y AUC como criterio. **No se usan
   los hiperparámetros del capítulo 5**, que se eligieron mirando todo el desarrollo.
4. La winsorización (1 % y 99 %) se calcula solo con el entrenamiento de cada ventana.
5. **Primer modelo:** el primer reentrenamiento con al menos **365 días** de historia etiquetada.
   Antes no hay señal y H3 está en efectivo. **La evaluación empieza en esa fecha**, y H2, B1 y B2 se
   comparan en los mismos días.

**Señal.** En cada liquidación *t*, `p(t)` = probabilidad de `alto` del último modelo entrenado
antes de *t*.

**Entrada.** Sin posición, si `p(t) ≥ p*`.

**Salida.** Con posición, si `p(t) < p* / 2` (la misma histéresis relativa de H2) o la última tasa
liquidada es negativa.

**Ejecución, tamaño, rebalanceo y costes:** los de H2 sin cambios (§4 a §6 y enmiendas 1 y 2 del
carry): latencia de 1 h (KE-016 corregido), 1x, rebalanceo del 10 % y slippage de 5 pb en SOL, BNB y
XRP.

## 5. Ensayos pre-declarados

| Parámetro | Valores |
|---|---|
| `p*` (umbral de probabilidad) | 0,5, 0,6 y 0,7 |

Son **3 configuraciones**. N acumulado del carry para el Deflated Sharpe de H3:

- H1 y H2: 18 ensayos, más los 2 de la prueba de humo (enmienda 2), más los que sume la reejecución
  de PQ-66;
- más los 3 de H3.

El informe da también el **N global** de la plataforma (`pq research registro resumen`), que hoy
incluye los 45 ensayos del modelo del capítulo 5. Toda ejecución adicional (otro umbral, otra
frecuencia de reentrenamiento, una corrección que cambie resultados) se registra y suma a N.

## 6. Modelo de costes

El escenario principal de H2 (§6 del carry). **Si PQ-17 verifica comisiones más altas, este
documento se enmienda antes del primer backtest de H3.**

## 7. Periodos

Los del carry: desarrollo hasta el **2024-06-30 23:59 UTC**; holdout desde el **2024-07-01** hasta el
**2026-09-30**. El holdout sigue cerrado hasta PQ-17 (enmienda 1.11). H3 lo abre **una sola vez**, y
solo si pasa los gates de la sección 8. Para H3, el modelo puede seguir reentrenándose dentro del
holdout con la misma regla de la sección 4, pero ninguna decisión del desarrollo usa datos del
holdout.

## 8. Evaluación

**Métrica principal:** la del carry (Sharpe anualizado de los retornos diarios netos sobre C).

**Validación en desarrollo:**

- **CPCV** con 6 grupos y 2 de prueba, purge de 8 días y embargo del 1 %. Se elige el `p*` con mejor
  Sharpe medio de prueba.
- **PBO** con CSCV de 16 bloques sobre la matriz días × 3 configuraciones.
- **Deflated Sharpe** con el N acumulado de la sección 5 y el V[SR] del registro de la familia carry.
- **t-estadístico** de la media diaria.

**Gates para abrir el holdout** (todos, en el escenario principal):

| Gate | Criterio |
|---|---|
| G1 | Deflated Sharpe > 0,95 con el N acumulado del carry |
| G2 | PBO < 0,5 |
| G3 | t de la media de los retornos diarios netos > 3 |
| G4 | Sharpe neto > Sharpe neto de B1, y CAGR neto > 4 % (B2) |
| **G5** | **Supera a H2 de forma significativa:** t de la media de la diferencia diaria (H3 − H2, mismos días) > 2 |

**Decisión.** Si pasa G1 a G5, H3 abre el holdout con el mismo criterio de éxito del carry (Sharpe
> 0,5, CAGR > 4 %, drawdown < 15 %) y, si lo supera, va a paper (PQ-101). **Si falla G5, H3 se
descarta aunque pase los demás:** no añade nada a H2. Se documenta en `decision-h3.md`.

## 9. Riesgos no modelados

Los del carry (§9), más dos propios de un modelo:

- **Deriva:** el régimen del funding cambió en 2025 (anclaje cerca del 11 %). El reentrenamiento
  cada 90 días lo mitiga, pero no lo evita.
- **Reproducibilidad:** el bosque se fija con `random_state = 42`, y el resultado puede depender de
  la versión de scikit-learn. La versión queda en el `uv.lock` del commit de la evaluación.

## 10. Enmiendas

Las mismas reglas del carry (§10). Antes del primer backtest de H3, una enmienda es un commit
`docs(estrategias): enmienda <n> del pre-registro de H3 PQ-<ticket>` y no suma a N. Después, todo
cambio es un ensayo nuevo o una hipótesis nueva.

**Prueba de humo:** si hace falta ejecutar el código para depurarlo, la ejecución se registra y suma
a N, y solo se miran conteos y capital final, no métricas de desempeño.

## 11. Declaración de exposición previa

Antes de este registro, el equipo **ya vio**, en el periodo de desarrollo:

- el desempeño de H1 y H2: H2 pasa los cuatro gates con k = 9, θ = 20 %, y H1 no los pasa;
- el AUC del clasificador frente a la regla (0,977 frente a 0,882) y su importancia por permutación;
- la frontera de CVaR del capítulo 6 y el presupuesto de PQ-83.

**No se calculó ningún retorno de una estrategia que use el clasificador** en ningún periodo. Como
la idea de H3 nace de haber visto el AUC en el desarrollo, **la prueba limpia de H3 es el holdout**;
el desarrollo solo sirve para descartarla.
