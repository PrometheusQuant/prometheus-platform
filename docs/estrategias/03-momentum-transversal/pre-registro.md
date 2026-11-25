# Estrategia 3 · Momentum cross-sectional en los perpetuos líquidos: pre-registro

- **Ticket:** PQ-114 · **Carril:** Boris (ensayos en `boris.jsonl`) · **Fase CRISP-ML(Q):** 1
- **Fecha de registro:** 2026-11-21
- **Estado:** registrado, **antes de ingerir el universo y antes de cualquier backtest**

!!! info "Por qué se prueba aunque la evidencia sea floja"
    La investigación base advierte que el momentum cross-sectional en cripto es más frágil y más caro
    que el de series temporales: Han, Kang y Ryu lo encuentran débil con costes realistas, y Rohrbach
    et al. reportan drawdowns brutos de ~70 % frente a ~40 % del TSMOM
    ([investigación base](../../investigacion/2026-10-16-plataforma-multiestrategia.md)). Probarlo con
    el protocolo y documentar el resultado, sea cual sea, es justo lo que distingue a la plataforma.

## 1. Hipótesis

**X1 (principal).** En un universo fijo de perpetuos USDⓈ-M líquidos, una cartera **larga en el
tercio con mayor retorno pasado y corta en el tercio con menor retorno pasado**, neutral en dólares y
con 1x bruto, obtiene neta de costes reales (comisiones, slippage de altcoins y funding) un Sharpe
positivo y una rentabilidad mayor que el yield de una stablecoin.

**X2 (secundaria, evaluada aparte).** La misma señal, **solo larga** en el tercio superior, obtiene un
Sharpe mayor que el del universo a partes iguales (B1). X2 cuenta en N, pero no cambia la decisión
sobre X1.

**Hipótesis nula.** El ranking por retorno pasado no predice el retorno relativo de la semana
siguiente, neto de costes.

## 2. Mecanismo económico

- El momentum es uno de los tres factores de riesgo cripto (Liu, Tsyvinski y Wu, *Journal of
  Finance*, 2022), atribuido a la infrarreacción y a la demanda minorista que persigue rendimientos.
- **Por qué podría fallar:**
  - las reversiones bruscas («crashes» del momentum) en las altcoins;
  - el coste de rotar una cartera de 10 posiciones cada semana, con el slippage de las altcoins;
  - el funding que pagan los largos en mercados alcistas, que en las altcoins puede ser alto;
  - el sesgo de supervivencia, si el universo se eligiera mirando qué monedas siguen vivas (ver §3).

## 3. Universo y datos

**Regla del universo, fijada antes de verlo:**

1. Candidatos: los perpetuos USDⓈ-M de Binance listados antes del **2021-01-01**, sin stablecoins
   ni tokens apalancados.
2. Se eligen los **15 de mayor volumen negociado en USDT en diciembre de 2020** (klines diarios de
   Data Vision). Esa fecha es anterior a toda la evaluación, así que la lista no puede elegirse por lo
   que pasó después.
3. La lista queda **fija** para todo el estudio y se publica en la evaluación con su comprobación.
4. **Deslistados:** si un símbolo deja de cotizar, su posición se cierra al último precio disponible
   y su parte queda en efectivo. **Nunca se sustituye** por otro (eso sería sesgo de supervivencia).

**Datos:** velas USDⓈ-M de 1 h y funding de Data Vision, con las mismas correcciones del silver que
el carry (timestamps normalizados, funding con su intervalo por fila y huecos sin imputar). La
ingesta del universo no es un ensayo y no suma a N.

## 4. Reglas de la estrategia

- **Señal:** `ret_L(t) = cierre_t / cierre_{t−L días} − 1`, con el cierre del perpetuo a las 00:00 UTC.
- **Rebalanceo semanal:** cada lunes a las 00:00 UTC, con los símbolos que tienen precio ese día y
  `L` días de historia.
- **Cartera X1 (long/short):** el tercio superior del ranking va largo y el inferior corto, a partes
  iguales dentro de cada lado. El nocional bruto es 1x del capital: 0,5 largo y 0,5 corto.
- **Cartera X2 (solo larga):** el tercio superior, a partes iguales, con 1x de nocional. El resto
  queda en efectivo.
- **Empates** en el ranking: se ordenan por símbolo, alfabéticamente, para que sea determinista.
- **Ejecución sin anticipación:** al `open` de la vela que abre en *t* + 1 h, o la siguiente con
  precio, como en el carry y la tendencia.
- **Funding:** en cada liquidación con la posición abierta antes de ella, el largo paga y el corto
  cobra `tasa × nocional`, al `close` del perpetuo de la vela que cierra en la liquidación.

## 5. Ensayos pre-declarados

| Parámetro | Valores |
|---|---|
| `L` (ventana del momentum, días) | 7, 14 y 28 |
| Cartera | X1 (long/short) y X2 (solo larga) |

Son **6 configuraciones**. **Familia de N: `tendencia`**, la misma del TSMOM (PQ-68), porque es el
mismo factor. Así el Deflated Sharpe de cada estrategia de momentum descuenta todos los ensayos de
momentum. Toda ejecución adicional se registra y suma a N.

## 6. Modelo de costes

| Escenario | Perp (por lado) | Slippage (por lado) | Uso |
|---|---|---|---|
| **Principal** | 0,050 % (taker VIP0) | **5 pb** en todo el universo; **10 pb** en los 5 de menor volumen de diciembre de 2020 | Gates y decisión |
| Sensibilidad | 0,020 % (maker) | 0 | Solo se informa |

**Si PQ-17 verifica comisiones más altas, este documento se enmienda antes del primer backtest.**

## 7. Periodos

- **Evaluación:** desde el **2021-02-01** (28 días de calentamiento más un margen) hasta el
  **2024-06-30 23:59 UTC**.
- **Holdout:** del **2024-07-01** al **2026-09-30**, cerrado. Se abre una sola vez y solo si pasa los
  gates.

## 8. Evaluación

**Métrica principal:** Sharpe anualizado de los retornos diarios netos sobre el capital (√365).

**Benchmarks:**

| | Benchmark | Rol |
|---|---|---|
| B1 | El universo a partes iguales, solo largo, rebalanceado cada semana con los mismos costes | Lo que X2 debe batir |
| B2 | Stablecoin al 4 % anual | Hurdle de las dos |

**Validación en desarrollo:** CPCV con 6 grupos y 2 de prueba, purge de **35 días** (la ventana máxima
de 28 más la semana de tenencia) y embargo del 1 %. Se elige la `L` con mejor Sharpe medio de prueba,
por hipótesis. PBO con CSCV de 16 bloques. Deflated Sharpe con el N de la familia `tendencia`.

**Gates para abrir el holdout** (todos, escenario principal):

| Gate | X1 | X2 |
|---|---|---|
| G1 | Deflated Sharpe > 0,95 | ídem |
| G2 | PBO < 0,5 | ídem |
| G3 | t de la media diaria > 3 | ídem |
| G4 | CAGR neto > 4 % (B2) | Sharpe neto > el de B1, y CAGR neto > 4 % |

**Siempre se informan:** el drawdown máximo, el peor mes, la rotación anual, la descomposición en
precio, funding y costes, y la **correlación diaria con el carry H2 y con la tendencia (PQ-68)**, que
pide el ticket.

**Decisión.** Si falla un gate, la hipótesis se descarta y se documenta en `decision.md`, con los
números aunque sean malos.

## 9. Riesgos no modelados

- Liquidación de un corto en una subida brusca de una altcoin (limitada con 1x bruto, pero un solo
  símbolo puede moverse más del 100 %).
- Límites de posición y de liquidez de Binance en las altcoins pequeñas.
- ADL en los perpetuos de menor liquidez.

## 10. Enmiendas

Las reglas del carry (§10). Antes del primer backtest, una enmienda no suma a N. Después, todo cambio
es un ensayo nuevo o una hipótesis nueva. Una prueba de humo se registra y suma a N.

### Aclaración 1 (2026-11-25, antes del primer backtest; no suma a N)

Precisa cómo se implementan reglas que el texto no fijaba. No cambia ninguna regla. Se escribió
después de revisar la **cobertura** de los datos del universo (primera y última vela y huecos por
símbolo) y **sin ningún retorno** de la estrategia (PQ-114).

1. **Tamaño de los tercios:** con *n* símbolos elegibles, cada tercio tiene `floor(n / 3)`. Con 15
   elegibles son 5 largos y 5 cortos (las 10 posiciones de §2). Con menos de 3, la cartera queda en
   efectivo esa semana.
2. **«Tienen precio ese día» (§4) se lee literal:** entra al ranking del lunes el símbolo con al
   menos una vela de 1 h el día anterior. Seis símbolos (XRP, LTC, YFI, SUSHI, XLM y GRT) no tienen
   velas en Data Vision del 2022-02-26 al 2022-02-28. Por eso quedan fuera del rebalanceo del
   2022-02-28 y sus posiciones se cierran al volver las velas. No se rellena el hueco: el silver
   no imputa (KE-007). La evaluación informa cuántos lunes tuvieron menos de 15 elegibles.
3. **Deslistado (§3.4):** solo cuando la serie **termina** (no vuelve a tener velas). El símbolo se
   cierra a su último precio un día después de la última vela. Un hueco temporal no es un
   deslistado: la posición se mantiene y se valora cuando vuelven las velas. En el desarrollo
   ningún símbolo termina; EOSUSDT termina el 2025-05-21, dentro del holdout.
4. **Señal tras un hueco:** un día sin velas repite el cierre anterior, con la misma convención que
   la tendencia. Tras un hueco, `ret_L` puede cubrir unos días más que *L*.
5. **Rotación anual:** el nocional negociado sobre el capital inicial (C = 1), con la misma
   convención que la tendencia.

## 11. Declaración de exposición previa

El equipo conoce, como todo el mundo, la trayectoria pública de las criptomonedas grandes entre 2021 y
2024. **No se calculó ningún retorno de momentum cross-sectional** ni de B1, y **no se ha mirado el
volumen de diciembre de 2020** que define el universo.
