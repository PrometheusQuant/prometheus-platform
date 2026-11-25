# Pre-registro: overlay de sentimiento sobre el momentum transversal

- **Ticket:** PQ-103 · **Carril:** Boris · **Agente que lo redacta:** Claude B
- **Fecha:** 2026-11-24, **antes de cualquier backtest del momentum transversal**. El registro de
  ensayos solo tiene filas descriptivas de su universo.
- **Base:** [`03-momentum-transversal/pre-registro.md`](../03-momentum-transversal/pre-registro.md)
  (PQ-114). Todo lo que no se diga aquí es igual que en ese documento.
- **Evidencia de los datos:** [spike de sentimiento](../../investigacion/2026-11-24-spike-sentimiento.md)

## 1. Hipótesis

**S1 (sobre X1, largo/corto).** Con la ventana `L` que el momentum elija en desarrollo para X1,
quedarse en efectivo las semanas que empiezan con **miedo extremo** en el Crypto Fear & Greed Index
da un Sharpe neto de costes **mayor que el de X1 sin filtro**.

**S2 (sobre X2, solo larga).** Lo mismo, sobre X2 y con la `L` que elija X2.

**Hipótesis nula.** Quedarse fuera en las semanas de miedo extremo no mejora el Sharpe neto del
momentum: las semanas que se evitan no son peores que las demás, o lo que se evita no compensa lo
que se deja de ganar y los costes de salir y volver a entrar.

## 2. Mecanismo económico

- Las ganancias del momentum se concentran en los periodos optimistas y desaparecen en los
  pesimistas (Antoniou, Doukas y Subrahmanyam, 2013, *JFQA*).
- Los «crashes» del momentum llegan en los estados de pánico que siguen a una caída del mercado:
  los perdedores rebotan más que los ganadores, y la pata corta pierde mucho de golpe (Daniel y
  Moskowitz, 2016, *JFE*).
- En cripto, el miedo extremo marca esos estados.
- **Por qué podría fallar:**
  - parte del índice es precio (volatilidad y momentum del mercado), así que el filtro puede ser
    solo una regla de «salir tras una caída» con otro nombre;
  - los rebotes violentos también pueden llegar con el índice en miedo, no solo en miedo extremo;
  - cada salida y cada vuelta pagan costes;
  - hay pocas semanas de miedo extremo, así que la diferencia puede no ser significativa.

## 3. Datos

- **Fuente:** Crypto Fear & Greed Index de alternative.me (`api.alternative.me/fng/`), diario desde
  el 2018-02-01. Se atribuye junto al dato, como pide su licencia.
- **`knowledge_time`:** el valor del día D se publica a las 00:00 UTC de D. El spike lo midió con 67
  copias de la Wayback Machine: aparece desde las 00:14 UTC y ninguna copia mostró el día anterior.
  Como margen, se considera conocido a la **01:00 UTC** de D.
- **Valor que usa cada rebalanceo:** el del **domingo** (D − 1) para el rebalanceo del lunes D a las
  00:00 UTC. El del lunes todavía no se conoce a esa hora.
- **Huecos:** se usa el último valor con `knowledge_time` anterior a la decisión, siempre que tenga
  como mucho 7 días. Si no hay ninguno así, la semana se trata como **sin filtro** (igual que la
  base). Nunca se rellena hacia atrás. El único hueco que afecta es el de 2 días tras el 2024-10-25,
  que cae en el holdout.
- **Miedo extremo:** valor **≤ 25**, el límite de la propia clasificación de la fuente (en la
  historia completa, «Extreme Fear» va de 5 a 25 y «Fear» empieza en 26). No se elige ni se ajusta.

## 4. Reglas

Son las del momentum (§4 de su pre-registro): señal, ranking, carteras X1 y X2, empates, ejecución
al `open` de la vela que abre en *t* + 1 h y funding. Se añade una sola regla:

- **Filtro.** En el rebalanceo del lunes D, si el índice del domingo es ≤ 25, la cartera objetivo
  de esa semana es **todo en efectivo**: se cierran todas las posiciones en la ejecución normal del
  rebalanceo. El lunes siguiente se vuelve a mirar el índice.
- El efectivo no rinde nada dentro de la estrategia. El hurdle del 4 % se aplica en G4, igual que
  en la base.

## 5. Ensayos pre-declarados

| Hipótesis | Base | `L` | Umbral |
|---|---|---|---|
| S1 | X1 | la que elija la CPCV del momentum para X1 | ≤ 25 |
| S2 | X2 | la que elija la CPCV del momentum para X2 | ≤ 25 |

Son **2 ensayos**. La `L` no se vuelve a elegir: se toma tal cual de la evaluación del momentum. El
umbral tampoco se varía, ni como sensibilidad. **Familia de N: `tendencia`**, la misma del momentum
y del TSMOM, porque el overlay es una variante del mismo factor. El Deflated Sharpe usa el N de esa
familia en el momento de evaluar, que ya incluye los 6 ensayos del momentum.

## 6. Costes

Los del momentum (§6): taker VIP0 al 0,050 % por lado y slippage de 5 pb, o de 10 pb en los cinco
símbolos de menor volumen. **Las salidas a efectivo y las vueltas pagan lo mismo que cualquier otro
rebalanceo.** Si PQ-17 enmienda las comisiones del momentum, este documento las hereda.

## 7. Periodos

- **Evaluación:** del **2021-02-01** al **2024-06-30 23:59 UTC**, igual que el momentum.
- **Holdout:** del **2024-07-01** al **2026-09-30**, cerrado. Se abre una sola vez, solo si S1 o S2
  pasan todos los gates y **después** de que el momentum haya tomado su propia decisión.

## 8. Evaluación

**Orden.** El overlay se evalúa **después** de la evaluación del momentum (PQ-114), con su motor de
backtest y sin cambiar sus reglas. Se evalúa aunque la base no pase sus gates, pero entonces S1 o S2
tienen que pasar los suyos por sí solos. No hay rescate: un overlay que mejora una base mala sigue
siendo malo si no pasa G1 a G4.

**Métrica principal:** Sharpe anualizado de los retornos diarios netos (√365).

**Benchmarks:** la base sin filtro con la misma `L` (lo que el overlay debe batir), más B1 y B2 del
momentum.

**Validación:** la misma CPCV del momentum (6 grupos, 2 de prueba, purge de 35 días y embargo del
1 %). PBO con CSCV de 16 bloques sobre las dos configuraciones de cada hipótesis: la base y el
overlay.

**Gates** (todos, en el escenario principal):

| Gate | Criterio |
|---|---|
| G1 | Deflated Sharpe > 0,95, con el N de la familia `tendencia` |
| G2 | PBO < 0,5 |
| G3 | t de la media diaria > 3 |
| G4 | El G4 de su base: CAGR neto > 4 % para S1; Sharpe neto > B1 y CAGR neto > 4 % para S2 |
| G5 | Sharpe neto del overlay > Sharpe neto de su base, en el periodo completo **y** en la mediana de los caminos de la CPCV |

**Siempre se informan:**

- cuántas semanas quedó fuera y qué parte del periodo es;
- el retorno que la base tuvo en esas semanas, es decir, lo que el filtro evitó o se perdió;
- el drawdown máximo y el peor mes, frente a la base;
- los costes extra de salir y volver a entrar;
- la correlación diaria con el carry H2 y con la tendencia.

**Decisión.** Si falla un gate, la hipótesis se descarta y se documenta en `decision.md`, con los
números aunque sean malos.

## 9. Riesgos no modelados

- **La metodología del índice cambió con el tiempo** (por ejemplo, las encuestas están en pausa). Lo
  publicado no se revisa, pero el índice de 2021 y el de 2024 no se calculan igual.
- **Las 67 copias son una muestra.** Que ninguna difiera no garantiza que nunca haya habido una
  revisión. Desde la ingesta se guarda una copia propia cada día.
- **Pocas semanas de miedo extremo.** El 23 % de los días de toda la historia lo son, pero agrupados
  en rachas: el número de episodios independientes es mucho menor.
- **Dependencia de un tercero.** Si alternative.me deja de publicar, el overlay no se puede operar.

## 10. Enmiendas

Ninguna.

## 11. Declaración de exposición previa

Quien redacta esto ha visto:

- los resultados del carry (desarrollo y prueba final) y de la tendencia (desarrollo y holdout);
- la distribución del índice: cuántos días hay en cada clasificación y los rangos de valores.

**No** ha visto:

- ningún retorno del momentum transversal;
- ninguna relación entre el índice y los retornos de ninguna estrategia o activo.

Ningún número de este documento sale de un backtest.
