# Estrategia 2 · Tendencia con volatility targeting: pre-registro

- **Ticket:** PQ-64 · **Épica:** PQ-6 · **Fase CRISP-ML(Q):** 1 (negocio y datos)
- **Fecha de registro:** 2026-11-06
- **Estado:** registrado, **antes de cualquier backtest de tendencia**

!!! info "Para qué sirve este documento"
    Igual que el [pre-registro del carry](../01-carry/pre-registro.md): fija la hipótesis, los
    parámetros, las métricas, los benchmarks, los costes y las fechas **antes** de ver un solo
    resultado, siguiendo el protocolo de Arnott, Harvey y Markowitz (2019). El commit que lo
    fusiona en `develop` es la evidencia fechada. También fija los detalles de ejecución que en el
    carry hubo que enmendar después (enmiendas 1 y 2), para no repetir esa situación.

## 1. Hipótesis

**T1 (principal).** En BTCUSDT y ETHUSDT **spot**, una posición **solo larga o en efectivo** cuyo
signo lo da el momentum de series temporales y cuyo tamaño lo da un objetivo de volatilidad obtiene,
neta de costes reales de una cuenta VIP 0, un Sharpe mayor que comprar y mantener y una
rentabilidad mayor que el yield de una stablecoin.

**T2 (secundaria, evaluada aparte).** La misma señal **larga o corta** en los perpetuos USDⓈ-M, con
el funding pagado o cobrado contabilizado. T2 cuenta en el número de ensayos N, pero su resultado no
cambia la decisión sobre T1.

**Hipótesis nula.** Ni el momentum ni el escalado por volatilidad mejoran el Sharpe de comprar y
mantener neto de costes, o la estrategia no supera el yield de una stablecoin.

## 2. Mecanismo económico

- **Por qué existe la tendencia.** Hay momentum de series temporales en 58 mercados
  (Moskowitz, Ooi y Pedersen, 2012), y el momentum es uno de los tres factores de riesgo cripto
  (Liu, Tsyvinski y Wu, *Journal of Finance*, 2022; [SSRN](https://papers.ssrn.com/abstract=3379131)).
  El mecanismo propuesto es la infrarreacción y la extrapolación de la demanda minorista, la misma
  que el BIS identifica detrás del carry ([investigación base](../../investigacion/2026-10-16-plataforma-multiestrategia.md)).
- **Por qué el volatility targeting.** La evidencia reciente, que es de preprints y practitioners,
  sugiere que la mayor parte del valor desde 2022 viene del escalado por volatilidad y no de la
  señal pura. Las cifras están autodeclaradas y no se verificaron
  ([notas de edges](../../investigacion/notas/edges_cripto_cuantitativos.md), §2).
- **Por qué podría fallar.**
  - Las ventanas cortas se las comen las comisiones ([Monash MCFS](https://www.monash.edu/business/mcfs/our-research/all-projects/investment-strategy/trend-following-strategies-for-crypto-investors)).
  - En BTC y ETH, comprar y mantener fue un benchmark muy exigente en 2020–2024.
  - La tendencia está correlacionada con el carry: comparten raíz, así que diversifica menos de lo
    que parece.
  - En T2, el funding medio anualizado que pagan los largos en el desarrollo fue de 15 % a 18 %
    (capa gold, PQ-46). Penaliza los tramos largos en el perpetuo.

## 3. Datos

| Dato | Fuente (silver) | Uso |
|---|---|---|
| Velas spot 1 h de BTCUSDT y ETHUSDT | `silver/klines/market=spot/interval=1h` | Señal, volatilidad y ejecución de T1 |
| Velas USDⓈ-M 1 h | `silver/klines/market=um/interval=1h` | Ejecución y valoración de T2 |
| Funding rate | `silver/funding` | Pagos y cobros de T2 |

- **Universo:** BTCUSDT y ETHUSDT, desde el 2020-01-01. Tienen los historiales más largos y
  líquidos, y su nocional mínimo es viable con < 1.000 USD.
- **Precio diario de la señal:** el `close` de la última vela de 1 h del día UTC, la que cierra a las
  00:00 del día siguiente. Es point-in-time: se conoce al cerrar esa vela.

## 4. Reglas de la estrategia

**Retornos diarios para la señal.** r_d = cierre_d / cierre_{d−1} − 1, con el precio de la
sección 3 (spot en T1 y T2).

**Señal (momentum de series temporales).** En cada decisión diaria *t* (00:00 UTC):

    señal_L(t) = signo( cierre_t / cierre_{t−L} − 1 )   (+1, 0 o −1)

**Volatilidad estimada.** σ̂(t) = desviación estándar muestral de los últimos **30** retornos diarios
hasta *t* inclusive, anualizada con √365. **No es un parámetro**: queda fija para no inflar N.

**Posición objetivo** por símbolo, como fracción de su parte del capital:

    w(t) = señal_L(t) × min( 1 ; σ* / σ̂(t) )

- **T1:** si `señal_L(t) ≤ 0`, entonces w = 0 (solo largo o efectivo).
- **T2:** se admite w < 0, que es un corto en el perpetuo.
- **Apalancamiento máximo 1x** en ambas: |w| ≤ 1.

**Banda de no-trade.** La posición solo se ajusta si `|w(t) − w_actual| > 0,10`. Es fija y no es un
parámetro. Reduce la rotación, como recomienda la investigación.

**Ejecución sin anticipación.** La decisión se toma con datos con `knowledge_time ≤ t`. La orden se
ejecuta al `open` de la vela de 1 h que **abre en t + 1 h** (01:00 UTC), con una hora de latencia como
en el carry. Si esa vela falta, se usa la siguiente disponible.

**Tamaño.** El capital C se reparte a partes iguales entre BTC y ETH. Lo no invertido queda en
efectivo, que rinde 0; con el 4 % solo se informa como sensibilidad.

**Funding (solo T2).** En cada liquidación *s* con la posición abierta antes de *s*, el largo paga y el
corto cobra `tasa(s) × nocional`, con el nocional valorado al `close` del perpetuo de la vela que
cierra en *s*. Es la misma aproximación del mark price que usa el carry.

**Valoración.** El capital se valora a las 00:00 UTC. El retorno diario se calcula sobre C. Se usan
la misma convención y la misma frontera del holdout que el carry, incluida la corrección de KE-014:
el desarrollo no cobra ni decide con eventos `≥ HOLDOUT_START`.

**Inicio común de la evaluación: 2020-05-01**, después del calentamiento de la ventana más larga
(120 días) y de la volatilidad (30). Todas las configuraciones se evalúan sobre los mismos días.

## 5. Ensayos pre-declarados

| Parámetro | Valores |
|---|---|
| `L` (ventana del momentum, días) | 20, 60, 120 |
| `σ*` (volatilidad objetivo anualizada) | 20 %, 40 % |

Son 6 configuraciones por hipótesis, así que **N = 12** para la familia de tendencia. Todo ensayo
adicional (otra ventana, otra volatilidad, la banda, el estimador, una corrección de errores que
cambie resultados) se registra en el registro de experimentos (PQ-24) y **suma a N**.

**N global.** El informe también da el número total de ensayos de la plataforma: carry, tendencia y
H3. Así se lee el Deflated Sharpe de la tendencia sabiendo cuánto se ha probado en total.

## 6. Modelo de costes

| Escenario | Spot (por lado) | Perp (por lado) | Slippage (por lado) | Uso |
|---|---|---|---|---|
| **Principal** (taker, sin BNB) | 0,100 % | 0,050 % | 2 pb | **Gates y decisión** |
| Sensibilidad (maker con BNB) | 0,075 % | 0,020 % | 0 | Solo se informa |

Son las mismas fuentes que en el carry ([comisiones de Binance](../../compliance/binance.md)).
**Si PQ-17 verifica comisiones más altas, este modelo se enmienda antes del primer backtest de
tendencia.** Si son más bajas, el escenario principal no se toca.

## 7. Periodos

Los mismos del carry, definidos en `domain/protocol.py`:

| Periodo | Desde | Hasta (incluido) | Uso |
|---|---|---|---|
| **Desarrollo** | 2020-05-01 (evaluación); datos desde el 2020-01-01 para el calentamiento | **2024-06-30 23:59 UTC** | Selección con CPCV |
| **Holdout** | **2024-07-01 00:00 UTC** | **2026-09-30 23:59 UTC** | Un solo uso; evaluación final |

**El holdout de la tendencia es independiente del del carry:** se abre una sola vez, después de pasar
los gates de la sección 8, y se registra en `holdout.md`.

## 8. Evaluación

**Métrica principal.** Sharpe anualizado de los retornos **diarios netos** sobre el capital total C
(√365, tasa libre de riesgo 0).

**Métricas secundarias:**
- CAGR, drawdown máximo y Calmar;
- volatilidad realizada frente a σ*;
- rotación anual (fracción del capital negociada);
- % del tiempo invertido y peor día;
- para T2, la descomposición del retorno en precio, funding y costes.

**Benchmarks** (mismo capital y mismos costes):

| | Benchmark | Rol |
|---|---|---|
| B1 | **Comprar y mantener** BTC y ETH al 50 % cada uno, en spot, desde el 2020-05-01 | Lo que hay que batir |
| B2 | Yield de stablecoin: **4 % anual** | Hurdle mínimo |
| B3 | La misma señal **sin** volatility targeting (w = señal, en T1 solo larga), con la L elegida | Solo informa si el vol targeting aporta; no es un gate |

**Validación en desarrollo:**
- **CPCV** con 6 grupos y 2 de prueba (15 particiones). **Purge de 150 días** (ventana máxima de 120 más
  volatilidad de 30) y embargo del 1 %.
- **Se elige la configuración con mejor Sharpe medio de prueba** en las 15 particiones.
- **PBO** con CSCV de 16 bloques sobre la matriz días × 6 configuraciones.
- **Deflated Sharpe y t-estadístico** como en el carry (enmienda 1, §9 y §10), con N de la familia de
  tendencia.

**Gates para abrir el holdout** (todos, en el escenario de costes principal):

| Gate | Criterio |
|---|---|
| G1 | Deflated Sharpe Ratio > 0,95 con N = todos los ensayos de tendencia registrados (≥ 12) |
| G2 | PBO < 0,5 |
| G3 | t de la media de los retornos diarios netos > 3 |
| G4 | Sharpe neto > Sharpe neto de B1 (comprar y mantener), y CAGR neto > 4 % (B2) |

**Criterio de éxito en el holdout** (escenario principal, configuración elegida, sin re-ajustes):
Sharpe neto > 0,5, CAGR neto > 4 % y drawdown máximo < 30 %.

**Decisión.** Si pasa, la estrategia va a paper trading en Demo Trading (PQ-82). Si falla un gate o el
holdout, **T1 se descarta** y se documenta en `decision.md`. Una variante requiere un pre-registro
nuevo y un holdout nuevo.

## 9. Riesgos no modelados en el backtest

- **Contraparte del exchange:** el mismo riesgo dominante que en el carry.
- **T2:** liquidación del corto en una subida brusca (limitada con 1x), ADL y cambios de reglas del
  contrato.
- **Gaps de precio** entre la señal y la ejecución mayores que una hora en eventos extremos.
- **Correlación con el carry:** se mide en la asignación de riesgo entre estrategias (PQ-83), no
  aquí.

## 10. Enmiendas

Mismas reglas que el carry:
- **Antes del primer backtest:** una enmienda es un commit `docs(estrategias): enmienda <n> del
  pre-registro de tendencia PQ-<ticket>` con el motivo. Solo se admiten correcciones que no dependan
  de resultados.
- **Después:** este documento no se modifica. Todo cambio es un ensayo nuevo (N + 1) o una hipótesis
  nueva.

**Prueba de humo.** Si el código del backtest necesita ejecutarse para depurarse, esa ejecución se
registra y **suma a N**, igual que en la enmienda 2 del carry. Solo se miran el capital final y los
conteos de órdenes, no métricas de desempeño.

## 11. Declaración de exposición previa

Antes de este registro, el equipo:
- conoce la trayectoria pública del precio de BTC y ETH entre 2020 y 2026 (es información pública e
  inevitable);
- vio cierres diarios y bases de spot y perpetuo en la capa gold (PQ-46), con fines de validación de
  datos;
- calculó el funding medio anualizado por símbolo del desarrollo (valores de control de PQ-47).

**No se calculó ningún retorno de una estrategia de tendencia ni de los benchmarks B1 y B3** en ningún
periodo. Tampoco se calculó la volatilidad realizada de BTC ni de ETH para elegir σ*.

Los valores de σ* (20 % y 40 %) y de L (20, 60 y 120 días) se eligieron por convención de la
literatura y de los practitioners citados, no por datos propios.
