# Estrategia 1 · H4: carry repartido entre exchanges con límite por exchange: pre-registro

- **Ticket:** PQ-94 · **Épica:** PQ-5 · **Fase CRISP-ML(Q):** 1
- **Fecha de registro:** 2026-11-22
- **Estado:** registrado, **antes de cualquier backtest de H4**
- **Relación:** variante del [pre-registro del carry](pre-registro.md), que manda en todo lo que este
  documento no cambia (con sus enmiendas 1 y 2 y la corrección de KE-014 y KE-016).

!!! info "Por qué H4"
    El capítulo 6 y el presupuesto de PQ-83 muestran que la **quiebra del exchange** domina el carry:
    con un 2 % anual, el carry de H2 rinde en esperanza menos que una stablecoin, y el presupuesto
    recomendado le da un 0 %. H4 prueba si **repartir entre exchanges** cambia esa conclusión.

## 1. Hipótesis

**H4.** La regla de H2 (k = 9, θ = 20 %, histéresis θ/2, salida con tasa negativa) aplicada **por
separado en Binance y en Bybit**, cada uno con su propio funding y una parte fija del capital, tiene
un **retorno anual esperado con quiebras simuladas** mayor que el de H2 con todo en Binance, y mayor
que el de una stablecoin al 4 %.

**Hipótesis nula.** Repartir no mejora el retorno esperado con quiebras: el funding de Bybit o sus
costes se comen la ventaja de diversificar el riesgo de contraparte.

## 2. Universo y datos

- **Símbolos:** los de H2 (SOLUSDT, BNBUSDT y XRPUSDT), la hipótesis aprobada en el desarrollo.
- **Exchanges:** Binance y **Bybit**. **OKX no entra:** su API pública solo guarda unos 3 meses de
  funding y no cubre el desarrollo ([PQ-79](../../investigacion/funding-entre-exchanges.md)). Si
  aparece una fuente histórica de OKX, añadirlo es una hipótesis nueva.
- **Funding:** silver de Binance (`silver/funding/`) y de Bybit (`silver/funding/exchange=bybit/`).
- **Precios:** las velas spot y perpetuo **de Binance** valoran también las patas de Bybit. **Es una
  simplificación declarada:** en una posición delta-neutral, el PnL lo dan sobre todo el funding y
  la base, y la diferencia de precio entre exchanges en estos símbolos es de décimas de punto básico.
  Medirla con velas de Bybit queda como sensibilidad, si se ingieren.
- **Periodo común:** desde la primera liquidación de Bybit en los tres símbolos (2021-06-29, PQ-79)
  hasta el **2024-06-30**. H2 se compara en esos mismos días.

## 3. Reglas

- En cada exchange, la regla de H2 con **su** funding: entrada si S₉ ≥ 20 %; salida si S₉ < 10 % o
  la última tasa es negativa.
- Cada exchange recibe una parte fija del capital, `w` en Binance y `1 − w` en Bybit, repartida a
  partes iguales entre los tres símbolos. Las dos partes **no se rebalancean entre sí**: el dinero de
  cada exchange se queda en él, que es lo que pasa en la realidad.
- La ejecución, el tamaño (1x), el rebalanceo del 10 % y la latencia de 1 h son los de H2.

## 4. Ensayos pre-declarados

| Reparto (`w` en Binance) | |
|---|---|
| 0,5 | Mitad y mitad |
| 0,7 | Sesgo al exchange principal |

Son **2 configuraciones**. H2 (`w` = 1) es la referencia y **no** es un ensayo nuevo. Se suman al N
acumulado del carry (H1, H2, los 2 de humo, la reejecución de PQ-66 y H3). Toda ejecución adicional
se registra y suma a N.

## 5. Costes

| Exchange | Spot (por lado) | Perp (por lado) | Slippage |
|---|---|---|---|
| Binance | Los del carry (§6) | | 5 pb |
| Bybit | 0,100 % | **0,055 %** (taker, sin VIP) | 5 pb |

Las comisiones de Bybit son las de su tabla pública para cuentas sin VIP y quedan **por verificar**
antes del primer backtest. Si PQ-17 o la verificación de Bybit dan comisiones más altas, este
documento se enmienda **antes** de evaluar.

## 6. Evaluación

**Criterio principal (lo pide el ticket): retorno anual esperado con quiebras simuladas.**

1. Escenarios anuales por **bootstrap conjunto** de bloques de 21 días de los retornos diarios del
   desarrollo de cada parte (Binance y Bybit), los mismos bloques para las dos
   (`portfolio_risk.budget`, ADR-0012).
2. Cada exchange quiebra con una probabilidad anual del **2 %** (el escenario moderado del capítulo 6)
   y su parte pierde el 100 %. Se evalúan dos supuestos:
    - **independientes** (supuesto principal);
    - **contagio:** si uno quiebra, el otro también con probabilidad del 50 %, como sensibilidad
      (FTX en 2022 arrastró a otros).
3. Se comparan el retorno esperado y el CVaR95 de H4 (cada `w`) con los de H2 (`w` = 1) en los mismos
   escenarios.

**Gates para abrir el holdout** (todos, en el escenario principal):

| Gate | Criterio |
|---|---|
| G1 | Retorno anual esperado con quiebras independientes **> el de H2 y > 4 %** |
| G2 | El mismo criterio con contagio no se invierte: H4 no queda por debajo de H2 |
| G3 | Deflated Sharpe > 0,95 con el N acumulado del carry |
| G4 | PBO < 0,5 sobre los 2 repartos más H2 |

Se elige el `w` con mayor retorno esperado con quiebras independientes. **Se informan siempre** el
Sharpe, el CAGR, el drawdown, la correlación diaria entre las partes y el funding cobrado en cada
exchange.

**Decisión.** Si pasa, H4 abre el holdout del carry (cerrado hasta PQ-17) con el mismo criterio de
éxito, y **el tope por exchange de PQ-83 se recalibra con su reparto**. Si falla, se descarta y se
documenta en `decision-h4.md`.

## 7. Riesgos no modelados

- **Correlación de quiebras** mayor que el supuesto de contagio.
- Diferencias de precio entre exchanges en un episodio extremo (la simplificación de §2).
- Operar en Bybit exige otra cuenta, otro KYC y otra API: es coste operativo, no solo de comisiones.

## 8. Enmiendas

Las reglas del carry (§10). Antes del primer backtest de H4, una enmienda no suma a N. Después, todo
cambio es un ensayo nuevo. Una prueba de humo se registra y suma a N.

## 9. Declaración de exposición previa

Antes de este registro el equipo **ya vio** en el desarrollo:

- el desempeño de H2 (pasa los cuatro gates);
- el presupuesto de PQ-83 (0 % al carry con quiebra al 2 %);
- **la comparación descriptiva del funding de Binance y Bybit** (PQ-79): medianas iguales, correlación
  de 0,66 a 0,90 y Bybit pagando más en torno al 40 % de las liquidaciones.

**No se calculó ningún retorno de una estrategia en Bybit** ni de un reparto entre exchanges. Como la
comparación de PQ-79 ya sugiere que el funding se parece, **la prueba que decide es el holdout**.

## Archivada (2026-11-24, decisión del titular)

**Esta hipótesis no se evaluó y queda archivada, con la puerta abierta.** No se calculó ningún
retorno ni ningún gate suyo, así que N no cambia.

**Por qué:**

- **Su holdout ya está usado.** El holdout del carry (2024-07-01 → 2026-09-30) lo abrió H2 una sola
  vez en PQ-50, y no se puede reutilizar.
- **El régimen no paga el carry.** En ese periodo H2 ganó un 0,22 % anual y estuvo con posición
  solo 38 de 822 días. Aun estando siempre dentro (B1), el carry en SOL, BNB y XRP ganó un 0,59 %
  anual, muy por debajo del 4 % de una stablecoin. Con funding comprimido desde 2025, refinar la
  entrada o repartir entre exchanges no puede crear una prima que no existe
  ([holdout de H2](holdout.md)).

**Cuándo retomarla.** Hacen falta las dos condiciones:

1. **Vuelve un régimen de funding alto.** La media de 90 días del funding anualizado de SOL, BNB y
   XRP supera el 20 % (el umbral θ de H2) durante al menos 30 días seguidos. Se comprueba con el
   silver de funding, que se actualiza a diario.
2. **Hay un periodo de validación nuevo:** al menos 6 meses de datos posteriores al 2026-09-30, sin
   mirar, que harán de holdout.

Al retomarla, este pre-registro se enmienda con fecha (nuevo periodo de validación y N
acumulado) **antes** de cualquier ejecución. Además se aplican las correcciones de método de
PQ-122.
