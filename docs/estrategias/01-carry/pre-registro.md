# Estrategia 1 · Carry de funding con entrada por umbral: pre-registro

- **Ticket:** PQ-18 · **Épica:** PQ-5 · **Fase CRISP-ML(Q):** 1 (negocio y datos)
- **Fecha de registro:** 2026-10-23
- **Estado:** registrado, **antes de cualquier backtest**

!!! info "Para qué sirve este documento"
    Siguiendo el protocolo de Arnott, Harvey y Markowitz (2019), fija la hipótesis, los
    parámetros que se probarán, las métricas, los benchmarks, los costes y las fechas del holdout
    **antes** de ver un solo resultado. El commit que lo fusiona en `develop` es la evidencia
    fechada. Cualquier cambio posterior sigue la sección 10.

## 1. Hipótesis

**H1 (principal).** En BTCUSDT y ETHUSDT, una posición delta-neutral *long spot / short perpetuo
USDⓈ-M* que **solo está abierta cuando el funding reciente anualizado supera un umbral** obtiene,
neta de costes reales de una cuenta VIP 0, un Sharpe mayor que el carry siempre activo y una
rentabilidad mayor que el yield de una stablecoin.

**H2 (secundaria, evaluada aparte).** Lo mismo en SOLUSDT, BNBUSDT y XRPUSDT. H2 cuenta en el
número de ensayos N, pero su resultado no cambia la decisión sobre H1.

**Hipótesis nula.** El timing por umbral no mejora el carry siempre activo neto de costes, o no
supera el yield de una stablecoin.

## 2. Mecanismo económico

- **Por qué existe el carry.** La demanda minorista de exposición larga apalancada y la escasez de
  capital de arbitraje generan un carry medio superior al 10 % anual en BTC y ETH. Es una prima
  por riesgo de cola: un carry alto predice caídas
  ([Schmeling, Schrimpf y Todorov, BIS WP 1087](https://www.bis.org/publ/work1087.pdf)).
- **Por qué el timing.** En datos horarios de Binance 2020–2024, 8,64 de los 13,70 puntos de
  exceso de retorno de BTC vienen de la convergencia del precio y solo 5,06 del funding. Con la
  restricción realista de no vender spot en corto, el Sharpe es 1,62 en BTC y 2,23 en ETH
  ([He, Manela, Ross y von Wachter, arXiv 2212.06888](https://arxiv.org/html/2212.06888v5)).
- **Por qué podría fallar.** El mismo paper documenta que la desviación cae ≈11 % por año. Además,
  desde 2024 el funding "normal" se ancla cerca de 0,01 %/8 h (≈11 % anual), que es el tipo de
  interés por defecto de la fórmula del contrato. Y los costes "retail" del paper en futuros
  (1,44 pb) están muy por debajo del taker VIP 0 actual (5 pb). Las tres cosas juegan en contra.

## 3. Datos

| Dato | Fuente (bronze, PQ-20) | Uso |
|---|---|---|
| Velas spot 1h | `dataset=klines/market=spot/interval=1h` | Precio de la pata spot |
| Velas USDⓈ-M 1h | `dataset=klines/market=um/interval=1h` | Precio de la pata perpetua |
| Funding rate | `dataset=fundingRate/market=um` | Señal y pagos |

Se usan las correcciones de silver descritas en la
[auditoría de Data Vision](../../investigacion/2026-10-23-auditoria-binance-data-vision.md):
timestamps normalizados (µs en spot desde 2025), funding anualizado con el
`funding_interval_hours` **de cada fila** y huecos sin imputar.

**Universo y fecha de inicio por símbolo** (periodo común de spot, perp y funding): BTCUSDT y
ETHUSDT desde 2020-01-01; XRPUSDT desde 2020-01-06; BNBUSDT desde 2020-02-10; SOLUSDT desde
2020-09-14.

## 4. Reglas de la estrategia

**Señal.** En cada liquidación de funding *t* de un símbolo:

    S_k(t) = media de las últimas k tasas liquidadas, cada una anualizada como
             tasa × (8760 / funding_interval_hours)

**Entrada.** Si no hay posición y `S_k(t) ≥ θ`, se abre la posición.

**Salida.** Si hay posición y `S_k(t) < θ / 2` (histéresis) o la última tasa liquidada es
negativa, se cierra.

**Ejecución sin anticipación.** La decisión usa solo datos con `knowledge_time ≤ t`. Las órdenes
se ejecutan al precio de **apertura de la vela de 1h que empieza en t + 1 h**: una hora de
latencia, para no operar al mismo precio que generó la señal. El funding se cobra (o se paga) solo
en las liquidaciones en las que la posición ya estaba abierta.

**Tamaño.** El capital C se reparte a partes iguales entre los símbolos del universo; cada parte
queda en efectivo mientras su símbolo no tiene posición. Dentro de su parte *A*: A/2 compra spot y
A/2 queda como margen de un short perpetuo de **nocional A/2 (apalancamiento 1x)**.

**Rebalanceo.** Si en una decisión `|nocional spot − nocional perp| / nocional perp > 10 %`, se
reajusta la pata perpetua, con su coste.

**Sin venta en corto de spot.** Con funding negativo no se invierte la posición: se queda en
efectivo.

## 5. Ensayos pre-declarados

| Parámetro | Valores |
|---|---|
| `k` (liquidaciones en la media) | 3, 9, 21 (≈ 1, 3 y 7 días con liquidaciones de 8 h) |
| `θ` (umbral de entrada anualizado) | 10 %, 20 %, 30 % |

Son 9 configuraciones por hipótesis, así que **N = 18** como mínimo. Todo ensayo adicional
(otra señal, otro umbral, una corrección de errores que cambie resultados) se registra en el
registro de experimentos (PQ-24) y **suma a N** en el Deflated Sharpe.

## 6. Modelo de costes

| Escenario | Spot (por lado) | Perp (por lado) | Slippage (por lado y pata) | Uso |
|---|---|---|---|---|
| **Principal** (taker, sin BNB) | 0,100 % | 0,050 % | 2 pb en BTC/ETH; 5 pb en SOL/BNB/XRP | **Gates y decisión** |
| Sensibilidad (maker con BNB) | 0,075 % | 0,020 % | 0 | Solo se informa |

Ida y vuelta de las cuatro patas en el escenario principal, para BTC y ETH:
2 × (0,100 % + 0,02 %) + 2 × (0,050 % + 0,02 %) = **0,38 % del nocional**.

Fuentes: [comisiones de Binance](../../compliance/binance.md) (spot oficial; futuros de fuentes
secundarias, tomando el taker más conservador). Si la verificación desde la cuenta (PQ-17) da
comisiones **más altas**, este modelo se enmienda (sección 10) **antes** del primer backtest. Si
las da más bajas, el escenario principal no se toca.

El efectivo ocioso rinde 0 % en el escenario principal (conservador). Como sensibilidad se informa
también el resultado con un 4 % anual sobre el efectivo ocioso.

## 7. Periodos

| Periodo | Desde | Hasta (incluido) | Uso |
|---|---|---|---|
| **Desarrollo** | inicio del símbolo (sección 3) | **2024-06-30 23:59 UTC** | Selección de la configuración con CPCV |
| **Holdout** | **2024-07-01 00:00 UTC** | **2026-09-30 23:59 UTC** | Un solo uso; evaluación final |

- El holdout cubre 27 de los 81 meses disponibles (33 %) e incluye la compresión del funding de
  2025 y el desapalancamiento de octubre de 2025.
- La señal puede usar datos del periodo de desarrollo para su ventana inicial (*warm-up*), pero no
  se evalúa ninguna operación anterior al 2024-07-01.
- **El holdout se abre una sola vez**, después de pasar los gates de la sección 8. Se registra en
  `holdout.md` con fecha, commit y autor. Abrirlo antes o repetirlo invalida la evaluación.

## 8. Evaluación

**Métrica principal.** Sharpe anualizado de los retornos **diarios netos** sobre el capital total C
(√365, tasa libre de riesgo 0).

**Métricas secundarias.** Rentabilidad anual neta (CAGR), drawdown máximo, Calmar, % del tiempo
invertido, número de ciclos, peor día, y descomposición del retorno en funding cobrado y
convergencia del precio (como en He et al.).

**Benchmarks** (mismo capital y mismos costes):

| | Benchmark | Rol |
|---|---|---|
| B1 | Carry **siempre activo**: abre al inicio y no cierra nunca | Lo que hay que batir |
| B2 | Yield de stablecoin: **4 % anual** constante (rango 3–7 % de préstamo de USDC en Aave según la [investigación](../../investigacion/notas/edges_alternativos_y_contradicciones.md)) | Hurdle mínimo |
| B3 | Comprar y mantener BTC | Solo contexto: tiene otro perfil de riesgo |

**Validación en desarrollo.** CPCV ([López de Prado, 2018](https://doi.org/10.1002/9781119482086))
con 6 grupos y 2 de prueba (15 particiones, 5 caminos), *purge* de 8 días (ventana máxima de la
señal + latencia) y embargo del 1 %. Se elige la configuración con mejor Sharpe medio en CPCV.

**Gates para abrir el holdout** (todos, en el escenario de costes principal):

| Gate | Criterio |
|---|---|
| G1 | Deflated Sharpe Ratio > 0,95 con N = todos los ensayos registrados (≥ 18) |
| G2 | PBO < 0,5 (CSCV sobre las 9 configuraciones) |
| G3 | t de la media de los retornos diarios netos > 3 |
| G4 | Sharpe neto > Sharpe neto de B1, y CAGR neto > 4 % (B2) |

**Criterio de éxito en el holdout** (escenario principal, configuración elegida, sin re-ajustes):
Sharpe neto > 0,5, CAGR neto > 4 % y drawdown máximo < 15 %.

**Decisión.** Si pasa, la estrategia va a paper trading en Demo Trading (fase 5). Si falla un gate
o el holdout, **H1 se descarta** y se documenta en `decision.md`. Una variante nueva requiere un
pre-registro nuevo y un holdout nuevo.

## 9. Riesgos no modelados en el backtest

- **Contraparte del exchange** (tipo FTX): es el riesgo dominante con todo el capital en un CEX.
- **Autodesapalancamiento (ADL)** y liquidación del short perpetuo en una subida brusca, mitigados
  con margen 1x y el rebalanceo del 10 %.
- **Depeg** de la stablecoin de margen.
- **Cambios de reglas** del contrato: tope del funding o intervalo de liquidación.

## 10. Enmiendas

- **Antes del primer backtest:** una enmienda es un commit `docs(estrategias): enmienda <n> del
  pre-registro del carry PQ-<ticket>` con el motivo. Solo se permiten correcciones que no dependan
  de resultados (p. ej. comisiones verificadas o un error en una fórmula).
- **Después de ver resultados:** este documento no se modifica. Cualquier cambio es un ensayo
  nuevo (N + 1) o una hipótesis nueva con su propio pre-registro.

## 11. Declaración de exposición previa

Antes de este registro el equipo vio **estadísticos descriptivos** de la fuente: la proporción de
liquidaciones de funding negativas y los extremos por símbolo (auditoría PQ-19), y comentarios de
mercado sobre la compresión del funding en 2025 (informe de investigación del 2026-10-16). **No se
calculó ningún retorno de estrategia** ni de los benchmarks B1 y B3 en ningún periodo.

## 13. Enmienda 2 (2026-10-30, tras una prueba de humo y antes de la evaluación)

**Qué pasó.** Al probar el código del backtest con una configuración (k = 9, θ = 20 %) y con B1 sobre
BTCUSDT en el periodo de desarrollo, se vio que la regla literal de rebalanceo de la sección 4
(igualar la pata perp a la pata spot) **no mantiene el apalancamiento 1x** que la misma sección
declara. Si el precio sube, el nocional de las dos patas crece con él, mientras el capital (cubierto)
no lo hace. En BTC 2020–2024 el nocional llegaba a ~4 veces el capital y el margen de la pata corta
se volvía negativo, lo que en la realidad es una **liquidación**. El resultado (un funding cobrado
irreal) delató el error.

**Corrección.** Se aplica la restricción ya declarada de 1x: en cada decisión con la posición
abierta, si una pata se desvía más de un 10 % de capital/2, **ambas** se llevan a capital/2, con los
costes de las dos patas. No cambian la señal, los umbrales, la rejilla, los costes ni las fechas.

**Transparencia en el conteo de ensayos.** Las 2 ejecuciones de la prueba de humo (k9-θ20 y B1, con
el error) se registran como ensayos adicionales: **N = 18 + 2 = 20** en el Deflated Sharpe. No se
miraron métricas de Sharpe, drawdown ni CPCV de ninguna configuración: solo el capital final y el
funding cobrado de esas dos ejecuciones.
