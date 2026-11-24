# Estrategia 4 · Sesgo favorito-longshot en Polymarket: pre-registro

- **Ticket:** PQ-87 · **Carril:** Boris (ensayos en `boris.jsonl`) · **Agente:** Claude B ·
  **Fase CRISP-ML(Q):** 1
- **Fecha de registro:** 2026-11-24
- **Estado:** registrado **antes de ingerir los datos (PQ-92) y antes de cualquier backtest (PQ-93)**
- **Base:** el spike de datos [PQ-78](../../investigacion/2026-11-24-spike-datos-polymarket.md),
  que dio *go* con tres condiciones que este documento recoge (§3, §4 y §7).

!!! note "Numeración"
    La épica PQ-11 la llama «Estrategia 3». La carpeta es `04-` porque el `03-` ya lo ocupa el
    momentum transversal (PQ-114), que se registró antes.

## 1. Hipótesis

**P1 (principal).** En los mercados binarios de Polymarket **fuera de deportes**, comprar el
resultado favorito cuando su precio está entre **0,80 y 0,95** y mantenerlo hasta la resolución da
un retorno medio por apuesta **positivo, neto de la comisión taker y del diferencial**. Dicho de
otro modo: los favoritos están baratos y los longshots caros.

**P2 (secundaria, evaluada aparte).** Lo mismo en los mercados **de deportes**. La literatura no
encuentra el sesgo en deportes (§2), así que P2 funciona como control: si P2 sale tan bien como P1,
es una alarma que obliga a revisar el backtest antes de creer en P1. P2 cuenta en N, pero no cambia
la decisión sobre P1.

**Hipótesis nula.** Los precios están calibrados: un contrato que cuesta *p* paga, en promedio, *p*.
Neto de costes, el retorno medio es negativo.

## 2. Mecanismo económico

- **El sesgo favorito-longshot** está documentado en apuestas desde hace décadas y en mercados de
  predicción recientes. Se atribuye a la preferencia por loterías (pagar de más por la pequeña
  probabilidad de un gran premio) y a que los takers minoristas compran longshots.
- **Evidencia en Polymarket** (Cardozo y Rivero-Wildemauwe, 2026, 588 M de operaciones,
  [arXiv 2609.12878](https://arxiv.org/pdf/2609.12878)):
    - con ponderación igual por contrato, los longshots pierden 6,3 ¢ por dólar;
    - agrupando los contratos por evento padre, **ganan** 4,1 ¢;
    - en deportes el sesgo no aparece.

  El signo depende de la agregación, y por eso §8 fija la métrica antes de ver datos.
- **En Kalshi** (Bürgi, Deng y Whelan, 2025) el sesgo es sistemático y mucho más fuerte para los
  takers. Resumen en [notas](../../investigacion/notas/edges_alternativos_y_contradicciones.md).
- **Por qué podría fallar:**
    - el resultado de Polymarket es frágil a la agregación (arriba);
    - una comisión o un diferencial algo mayores se comen un edge de pocos centavos;
    - la competencia de bots, que ya extrajeron unos 40 M USD de arbitraje (Saguillo et al., 2025);
    - el sesgo de selección por volumen (§3);
    - un favorito a 0,90 que pierde cuesta nueve veces lo que gana uno que acierta, así que pocas
      sorpresas grandes dominan el resultado.

## 3. Universo y datos

**Fuente:** el bronze y el silver de Polymarket de PQ-92 (Gamma para el catálogo y la resolución,
CLOB `prices-history` para los precios). La ingesta no es un ensayo y no suma a N.

**Reglas del universo, fijadas antes de verlo:**

1. Mercados con libro CLOB (`clobTokenIds` no vacío) y **exactamente dos resultados**. Esto
   incluye los mercados `negRisk`: cada uno es binario dentro de un evento de varios resultados.
2. Volumen total (`volumeNum`) de **al menos 1.000 USD**.
3. **Deportes** = el evento lleva la etiqueta `Sports` en Gamma, o el mercado tiene un `feeType`
   que empieza por `sports`. Todo lo demás es «fuera de deportes». La categoría es un dato fijo del
   mercado, conocido desde su creación.
4. Se excluyen los mercados resueltos con `outcomePrices = ["0", "0"]`, porque no tienen un pago
   definido. Se cuentan y se informan.

**Sesgo declarado.** La regla 2 usa el volumen de toda la vida del mercado, que en la fecha de
entrada todavía no se conocía. La API pública no da el volumen hasta una fecha dada para todo el
periodo (las operaciones solo cubren unos tres años, según el spike §3). Se acepta este sesgo. Para
acotarlo, la evaluación informa P1 con un umbral de 10.000 USD como sensibilidad; esa sensibilidad
no decide nada.

## 4. Reglas de la estrategia

- **Instantánea diaria a las 00:00 UTC.** Se usa el punto diario del CLOB (`interval=max`,
  `fidelity=1440`). Un mercado entra en la instantánea solo si estaba abierto en ese momento:
  instantánea anterior a `closedTime` y posterior a la creación. Saber si un mercado está abierto es
  información disponible en ese instante.
- **El punto diario es el precio de las 00:00, no el cierre del día.** Se comprobó el 2026-11-24
  en 14 puntos de 7 mercados de 2024: el punto diario coincide con el precio por minuto del mismo
  instante. En 4 de ellos el último precio de ese día era distinto, así que la prueba distingue
  los dos casos. PQ-92 repite la comprobación sobre todo el silver; si falla en algún mercado, se
  usa el precio por minuto inmediatamente anterior a las 00:00.
- **Favorito:** el resultado con precio *p* ≥ 0,5 en la instantánea, según el precio del primer token;
  el del segundo es 1 − *p*.
- **Entrada:** en la **primera** instantánea en que el precio del favorito cae dentro de la banda
  de la configuración (§5). **Una sola entrada por mercado.**
- **Datos de relleno:** un precio exactamente igual a 0,5 en una serie que no se ha movido en las
  24 h previas se trata como faltante, no como precio (spike §4). Con las bandas de §5 nunca
  provocaría una entrada, pero la regla queda escrita para las sensibilidades.
- **Precio de compra:** el precio de la instantánea más el diferencial de §6.
- **Salida:** ninguna. La apuesta se mantiene hasta la resolución y **cobra el precio final
  publicado** (`outcomePrices` del resultado comprado): 1 o 0 en el caso normal, y lo que se haya
  pagado en las resoluciones parciales, como 0,5. Así no hace falta excluir ninguna resolución
  mirando el resultado, salvo la regla 4 de §3.
- **Tamaño:** 1 USD por apuesta, siempre igual. La métrica no depende del capital (§8).
- **Fin de periodo:** una apuesta que no se ha resuelto al terminar su periodo (§7) se valora al
  último precio disponible antes de ese corte, menos el diferencial de salida. Así ningún resultado
  posterior al corte entra en el periodo.

## 5. Ensayos pre-declarados

| Parámetro | Valores |
|---|---|
| Banda del favorito | [0,70; 0,85), **[0,80; 0,95)** y [0,90; 0,98) |
| Categoría | fuera de deportes (P1) y deportes (P2) |

Son **6 configuraciones**. La banda [0,80; 0,95) de P1 es la que nombra la hipótesis; las otras dos
existen para el PBO y cuentan en N igual. **Familia de N: `polymarket`**, nueva. Toda ejecución
adicional, incluidas las pruebas de humo, se registra y suma a N.

## 6. Modelo de costes

Se paga como **taker**: el spike no encontró libro de órdenes histórico, así que no se puede saber
si una orden pasiva se habría llenado.

| Concepto | Escenario principal | Sensibilidad (solo se informa) |
|---|---|---|
| Diferencial al entrar | **+0,01** sobre el precio de la instantánea | 0 y +0,02 |
| Comisión taker | `feeRate × p × (1 − p)` por acción, con la tasa de la categoría de [compliance](../../compliance/polymarket.md) §2 (0,04 política, finanzas y tecnología; 0,05 deportes; 0,07 cripto; 0 geopolítica; **0,07 si la categoría es desconocida**) | sin comisión |
| Diferencial al salir (solo al valorar en el corte) | −0,01 | 0 |

La tabla de comisiones de 2026 se aplica a todo el periodo, aunque antes Polymarket no cobrara.
Esto hace al escenario principal **pesimista** a propósito. Si PQ-92 verifica las comisiones
históricas (`feesEnabled`, `takerBaseFee`), se puede pasar a ellas con una enmienda **antes del
primer backtest**, nunca después.

## 7. Periodos

Las fechas son de **entrada**:

- **Evaluación:** del **2023-01-01** al **2025-06-30**. Las apuestas sin resolver se valoran a
  2025-06-30 23:59 UTC.
- **Holdout:** del **2025-07-01** al **2026-06-30**. Las apuestas sin resolver se valoran a
  2026-10-31 23:59 UTC. Se abre una sola vez y solo si P1 pasa los gates.

Antes de 2023 casi no hay historial en el CLOB (spike §1), así que no se usa.

## 8. Evaluación

**Métrica principal:** retorno neto medio **por apuesta** (por dólar apostado), con ponderación
igual por mercado. Su error estándar se agrupa **por evento padre** de Gamma: los mercados `negRisk`
de un mismo evento no son independientes.

**Serie diaria (para Sharpe, DSR y PBO):** el PnL neto de las apuestas que se resuelven o se valoran
cada día, en USD con 1 USD por apuesta. El Sharpe se anualiza con √365 y no cambia con la escala.

**Siempre se informan:**

- el retorno por apuesta **ponderado por evento** (un voto por evento padre), porque en la
  literatura cambia de signo (§2);
- el retorno por dólar-año comprometido: PnL total dividido entre la suma de dólares × años que
  estuvo abierta cada apuesta;
- la tasa de acierto y la calibración por banda;
- la peor racha de pérdidas, el número de apuestas, eventos y mercados excluidos (§3.4), y la
  sensibilidad a costes y a 10.000 USD de volumen;
- la **correlación diaria con el carry H2 y con la tendencia**, que es el argumento de
  diversificación de PQ-93.

**Benchmarks:**

| | Benchmark | Rol |
|---|---|---|
| B1 | Comprar el favorito en la primera instantánea de cada mercado elegible, sin banda (*p* ≥ 0,5), con los mismos costes | Lo que la banda debe mejorar |
| B2 | Stablecoin al 4 % anual | Lo que el retorno por dólar-año debe batir |

**Validación en desarrollo:**

- PBO con CSCV sobre 16 bloques de la serie diaria, entre las 3 bandas de cada hipótesis.
- Deflated Sharpe con el N de la familia `polymarket`.
- No se elige la banda por resultado: la decisión es sobre la banda nombrada en P1.

**Gates para abrir el holdout** (todos, escenario principal, banda [0,80; 0,95) de P1):

| Gate | Condición |
|---|---|
| G1 | Deflated Sharpe > 0,95 |
| G2 | PBO < 0,5 |
| G3 | t del retorno medio por apuesta, agrupado por evento, > 3 |
| G4 | Retorno medio por apuesta > 0 **y** retorno por dólar-año > 4 % (B2) **y** por apuesta mejor que B1 |
| G5 | El retorno por apuesta **ponderado por evento** también es > 0 |

G5 no existe en las otras estrategias. Se añade porque la literatura muestra que el resultado de
Polymarket puede invertirse con la agregación: si el edge solo aparece con una de las dos
ponderaciones, no es robusto.

**Decisión.** Si falla un gate, P1 se descarta y se documenta en `decision.md`, con los números
aunque sean malos.

## 9. Riesgos no modelados

- **Resolución:** disputas en UMA, resoluciones tardías y el capital inmovilizado hasta el cierre.
- **Liquidez:** con 1 USD por apuesta el impacto es nulo, pero el retorno no escala sin un libro
  que lo respalde.
- **Regulación:** Argentina bloqueó Polymarket en 2026 y la región se endurece
  ([compliance](../../compliance/polymarket.md) §1). El acceso desde Bolivia debe volver a
  verificarse antes de operar.
- **Contraparte y contrato:** USDC en Polygon y el contrato del CTF Exchange.
- **Datos:**
    - No se sabe si el precio del CLOB es el último negociado o el punto medio (spike §2). El
      diferencial de §6 lo cubre a medias, igual que el retardo entre ver el precio y ejecutar.
    - Las etiquetas de Gamma (§3, regla 3) son las de hoy. Si un mercado se reetiquetó después de
      crearse, la categoría no es la que se conocía en la entrada.

## 10. Enmiendas

Las reglas del carry (§10 de su pre-registro). Antes del primer backtest, una enmienda solo puede
corregir algo que no dependa de resultados, como las comisiones verificadas o un error de una
regla, y no suma a N. Después, todo cambio es un ensayo nuevo o una hipótesis nueva. Una prueba de
humo se registra y suma a N.

## 11. Declaración de exposición previa

- **Literatura:** el equipo conoce la evidencia de §2, que motiva la hipótesis.
- **Spike PQ-78:** miró 227 mercados para controlar la calidad de los datos. Solo vio el **último**
  precio antes del cierre (casi siempre < 0,05 o > 0,95) y si apuntaba al resultado. **No vio
  ningún precio en las bandas de §5 frente a su resolución**, ni calculó retornos, calibración o
  tasas de acierto.
- **Comprobación de §4:** se miraron 14 precios diarios de 7 mercados para ver a qué instante
  corresponden. No se cruzaron con su resolución.
- **Fuera de eso:** no se ha descargado ninguna serie de precios del universo ni se ha calculado
  ninguna métrica de esta estrategia. El equipo conoce, como todo el mundo, el resultado de eventos
  públicos de 2023 a 2026 (por ejemplo, las elecciones de EE. UU. de 2024), que forman parte del
  universo.

## 12. Enmienda 1 (2026-11-24, PQ-93, antes del primer backtest)

Sale de una revisión adversarial del código de la evaluación, hecha por un agente de contexto
fresco **antes** de ejecutarla. Ningún punto depende de resultados: todavía no se ha calculado
ninguna métrica de la estrategia. Según §10, no suma a N.

**Universo (§3):**

1. **Catálogo usado:** los mercados cerrados con `endDate` entre 2022-01 y 2026-10, ingeridos el
   2026-11-24 con `pq polymarket mercados` (PQ-92). Se amplió a 2022 para no perder los mercados
   con `endDate` de 2022 que siguieron negociándose en 2023.
2. **Elegir «cerrado al ingerir» no deja fuera nada del periodo de evaluación.** Comprobado el
   2026-11-24:
    - el mercado abierto más antiguo con ≥ 1.000 USD empezó el 2025-07-03;
    - el mercado cerrado con `endDate` posterior a 2026-10 que empezó antes, el 2025-07-06.

   Ninguno es anterior al corte (2025-06-30). La evidencia se reproduce con
   `scripts/verificar_universo_polymarket.py`, que guarda las consultas y sus respuestas en JSON.
   **Para el holdout habrá que repetir la comprobación** y, si hace falta, ingerir también los
   mercados abiertos.
3. **Regla 4, corregida:** `["0", "0"]` se excluye solo si esa resolución ya se conocía en el
   corte. Si llegó después, en el corte el mercado seguía sin resolver y se valora al corte, como
   cualquier otro.
4. **Dato válido:** un mercado entra solo si su pago publicado tiene dos valores y ninguno es nulo.
   Los demás se cuentan y se informan, igual que los de la regla 4.
5. **Etiquetas:** son las que Gamma devuelve con `include_tag=true` en cada mercado. En el ejemplo
   comprobado coinciden con las de `/events/{id}`. §3.3 dice «del evento».

**Instantánea (§4):**

6. **La instantánea diaria** es el punto diario del CLOB dentro del primer minuto tras las 00:00
   UTC. Los puntos llegan a las 00:00:02 o 00:00:03. Un punto fuera de ese minuto no se usa y se
   cuenta. La instantánea también tiene que ser posterior a `createdAt`.
7. **Comprobación del punto diario:** se hace sobre una muestra en lugar de sobre todo el silver,
   con `scripts/verificar_punto_diario.py` (5 mercados por mes, de 2023-01 a 2025-06, semilla 93).
   - **Resultado del 2026-11-24:** 148 de 148 puntos diarios coinciden con el precio por minuto
     del mismo segundo. Ninguno es posterior.
   - Si la ingesta completa mostrara puntos fuera de medianoche, la evaluación los informa y no
     los usa.

**Costes (§6):**

8. **Tabla de tasas**, exactamente la de §6:
    - 0,04: `politics`, `finance` y `tech`;
    - 0,05: `sports`;
    - 0,07: `crypto`;
    - 0: `geopolitics`;
    - cualquier otra: 0,07.

   Se mira primero el prefijo de `feeType`; si no está, las etiquetas (sin distinguir mayúsculas).
   Si coinciden varias, se toma la tasa **más alta**.
9. **Precio de la comisión:** la comisión se calcula sobre el **precio de ejecución** (instantánea
   + diferencial), que es el que cobra Polymarket. El precio pagado tiene un tope de 0,999, para
   que el coste por acción nunca llegue a 1. El tope solo afecta a B1 y a la sensibilidad +0,02.

**Evaluación (§8):**

10. **Sensibilidades, por separado:** entrada 0, entrada +0,02, salida 0, sin comisión y volumen ≥
    10.000 USD.
11. **«Peor racha de pérdidas»** se informa de dos formas:
    - la racha más larga de días con PnL negativo; un día sin resoluciones (PnL 0) no la corta;
    - la caída máxima del PnL acumulado.
12. **Calibración:** se calcula sobre las apuestas resueltas, con los mismos denominadores para
    precio y pago. Cuenta como acierto un pago completo (≥ 0,999); los pagos parciales se informan
    aparte.
13. **Duración mínima:** el retorno por dólar-año cuenta al menos 1 día de tenencia por apuesta.
14. **Orden del registro.** Primero se calculan las 6 configuraciones, sin mirarlas. Después se
    registran juntas. Solo entonces se calculan los gates con el N resultante. Así, un fallo de
    datos a mitad de camino no deja filas a medias que obliguen a repetir y sumar a N. Lo que corre
    después del registro (B1, sensibilidades, escritura) puede fallar todavía, pero solo con datos
    que ya pasaron los mismos cálculos.
15. **Mercados del universo sin historial de precios:** no pueden apostarse. Se cuentan y se
    informan, para que una ingesta incompleta no pase inadvertida.
16. **Correlación con el carry H2 y la tendencia T1:** solo cubre su periodo de desarrollo, que se
    solapa de 2023-01 a 2024-06. Sus filas del holdout, desde 2024-07-01, no se usan (KE-014).
17. **Lectura de G2:** con 3 bandas, el PBO sin habilidad ronda los 2/3, porque el rango mediano
    cuenta como sobreajuste. G2 es exigente y no se relaja.

**Exposición previa adicional (§11):**

- La ingesta de PQ-92 descargó las series de precios del universo.
- La comprobación del punto 7 miró 148 precios diarios, sin cruzarlos con ninguna resolución.
- El código de la evaluación solo se ha ejecutado con datos sintéticos.
- No se ha calculado ninguna métrica de la estrategia sobre datos reales.
