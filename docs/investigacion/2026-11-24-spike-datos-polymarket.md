# Spike de datos de Polymarket: qué hay, cuánto y con qué condiciones

- **Ticket:** PQ-78 (spike, time-box de 1 día) · **Carril:** Boris · **Agente:** Claude B
- **Fecha de la consulta:** 2026-11-24, contra las API públicas en vivo y la documentación oficial
- **Reproducible con:** `uv run python scripts/spike_polymarket.py --out spike-polymarket.json`
- **Desbloquea:** PQ-87 (pre-registro), PQ-92 (ingesta) y PQ-93 (evaluación)

## Decisión: **GO**, con tres condiciones

Las API públicas dan lo que la Estrategia de Polymarket necesita: catálogo con resolución,
historial de precios hasta el minuto y operaciones una a una. Desde 2023 hay **al menos 59.759
mercados cerrados** con 1.000 USD o más de volumen, doce veces el mínimo de 5.000 registros del
ticket. En la muestra, **225 de 227 mercados desde 2023 tienen historial de precios**. El acceso
desde Bolivia sigue abierto.

Las condiciones, que PQ-87 y PQ-92 tienen que recoger:

1. **Solo desde 2023.** Los mercados de 2020 a 2022 casi no tienen historial en el CLOB (2 de 136
   en la muestra). Todo apunta a que eran de la época del AMM, anterior al libro de órdenes.
2. **Un corte de point-in-time anterior a `closedTime`.** El precio ya refleja el resultado antes
   de que el mercado se cierre (§4), y en eventos en vivo la serie puede quedar clavada en 0,5
   durante horas.
3. **Las operaciones solo cubren unos tres años móviles** (§3). Si la estrategia es maker y
   necesita simular fills, PQ-92 tiene que guardarlas ya, antes de que la ventana las borre.

## Qué se midió y qué no

El script consulta tres API públicas sin credenciales:

- **Gamma** (`gamma-api.polymarket.com/markets`): el catálogo de mercados, con su resolución.
- **CLOB** (`clob.polymarket.com/prices-history`): el historial de precios de cada resultado.
- **Data API v2** (`data-api.polymarket.com/v2/trades`): las operaciones una a una.

Para cada mes entre 2020-01 y 2026-11 cuenta los mercados cerrados con al menos 1.000 USD de
volumen. Después toma 5 al azar por mes (semilla 78) y comprueba qué historial de precios sirve el
CLOB.

!!! warning "Lo que el spike no miró a propósito"
    No se calcularon rentabilidades ni la calibración de los precios por tramo (por ejemplo, si
    los contratos de 5 ¢ ganan menos del 5 % de las veces). Esa es justo la hipótesis que
    PQ-87 tiene que registrar antes de ver datos. El único cruce entre precio y resultado que se
    hizo es un control de calidad: que el último precio antes del cierre apunte al resultado
    publicado.

## 1. Volumen de datos

Mercados cerrados con volumen ≥ 1.000 USD, por año de `endDate`. Gamma no acepta
`offset` > 2.000, así que en un mes con más mercados el conteo se detiene ahí: los años marcados
con «≥» son **cotas inferiores** y el número real es mayor.

| Año | Mercados cerrados | En la muestra | Con historial de precios |
|---|---:|---:|---:|
| 2020 | 36 | 16 | 0 |
| 2021 | 1.876 | 60 | 0 |
| 2022 | 2.418 | 60 | 2 |
| 2023 | 1.321 | 60 | 58 |
| 2024 | ≥ 12.415 | 58 | 58 |
| 2025 | ≥ 24.012 | 54 | 54 |
| 2026 (hasta noviembre) | ≥ 22.011 | 55 | 55 |
| **Desde 2023** | **≥ 59.759** | **227** | **225** |

La muestra no llega a 5 × 12 en algunos años porque algunas consultas a Gamma fallaron tras los
reintentos. No se repitieron para no cambiar la semilla. Un mercado de 2020 salió dos veces en la muestra
(en noviembre y en diciembre); no cambia ninguna conclusión. Los 2 mercados de 2023 sin historial
terminan en enero de 2023 y sus preguntas son de 2022 (la recesión «antes del Q4 2022» y el Merge
de Ethereum).

## 2. Historial de precios

En los 225 mercados de la muestra desde 2023 que tienen historial:

| Serie | Mercados con datos |
|---|---:|
| Diaria completa (`interval=max`, `fidelity=1440`) | 220 |
| Por hora, 15 días antes del cierre | 225 |
| Por minuto, 15 días antes del cierre | 225 |

Los 5 sin serie diaria son eventos de pocas horas (dos votaciones sobre McCarthy, una entrevista,
un discurso y una partida de ajedrez) que no cruzan ninguna medianoche UTC. Sí tienen datos por
minuto.

Cómo se comporta `GET /prices-history` (medido, no solo documentado):

| Consulta | Resultado |
|---|---|
| `interval=max&fidelity=1440` | Serie diaria de toda la vida del mercado, con un punto a medianoche UTC. Un mercado que no cruza una medianoche UTC no tiene ningún punto. |
| `interval=max` con `fidelity` 60 o 1 | **0 puntos.** El detalle fino no sale con `interval`. |
| `startTs`/`endTs` de hasta 15 días, `fidelity=1` | Un punto por minuto (≈ 21.600 en 15 días), también en mercados de 2024. |
| Ventana de más de 15 días | Error `interval is too long`. |

Para tener datos por minuto de un mercado largo hay que encadenar ventanas de 15 días. El límite
documentado de este endpoint es de 1.000 peticiones cada 10 s por IP
([rate limits](https://docs.polymarket.com/quickstart/introduction/rate-limits)), de sobra para
una ingesta nocturna.

**Por verificar en PQ-92:** la documentación no dice si `p` es el último precio negociado o el
punto medio del libro. Esto importa para modelar el coste de entrar.

## 3. Volumen negociado y operaciones

- Gamma da el volumen total de cada mercado (`volumeNum`) y ventanas móviles actuales
  (`volume1wk`, `volume1mo`…), no una serie histórica de volumen.
- La serie de volumen sale de las operaciones: `GET /v2/trades?condition=<conditionId>`,
  paginada con cursor (`pagination.next_cursor`). Según la documentación, por mercado se ve una
  ventana fija de tres años. Medido el 2026-11-24: un mercado que cerró en junio de 2024
  devolvió operaciones desde el 2023-11-25, y dos mercados de 2023 (volumen > 50.000 USD) no
  devolvieron ninguna. La ventana es **móvil**: cada día se pierde un día de historia.
- La **Data API v1 se retiró el 2-nov-2026** y responde `410` con un enlace a la v2. Cualquier
  código o tutorial que use `/trades?market=` está roto.
- Un mercado muy líquido tiene decenas de miles de operaciones al día: en las elecciones de EE. UU.
  de 2024, 20.000 operaciones cubrían menos de un día y bajar 40 páginas llevó 47 s. Para un
  backtest diario o por hora basta el historial de precios; las operaciones solo hacen falta para
  simular fills de órdenes maker (§5).

## 4. Resolución

- Gamma publica `umaResolutionStatus` (`resolved`) y `outcomePrices`, que tras la resolución queda
  en `["1", "0"]` o `["0", "1"]`.
- De los 225 mercados de la muestra con historial, 217 tienen la resolución en `["1", "0"]` o
  `["0", "1"]`. En 212 el último precio por minuto está del lado del resultado publicado: en 208
  ese punto cae a 0 o 1 minutos de `closedTime` y en los otros 4, a entre 2 y 8 minutos. En 201 de
  los 212 el precio ya está por debajo de 0,05 o por encima de 0,95.
- **Los otros 5 terminan con el precio exactamente en 0,5**; en los 4 medidos, durante 2,5 a
  7,6 horas antes del cierre. Antes de ese tramo la serie se mueve con normalidad. Son eventos en
  vivo: NBA, MLB, UFC, fútbol y un reality. La explicación probable, **por verificar**, es que al
  empezar el evento se vacía el libro (Gamma tiene el campo `clearBookOnStart`) y la serie muestra
  0,5 porque `p` es el punto medio del libro o un valor por defecto con el libro vacío. En
  cualquier caso, ese 0,5 no es un precio: el silver debe marcarlo como faltante.
- **Los 8 no binarios son de enero a abril de 2023**, probablemente restos del AMM: 5 se resolvieron
  con decimales casi 0/1 (por ejemplo, `0.99999739…`), 2 con `["0", "0"]` y 1 con
  `["0.58…", "0.41…"]`, que parece una resolución a 50/50. La regla de calidad tiene que
  redondear los casi 0/1 y excluir o tratar aparte los otros dos casos.
- `umaResolutionStatus` puede venir vacío aunque el mercado esté resuelto (1 caso en la muestra):
  conviene usar `outcomePrices` como fuente de la resolución.

!!! danger "Trampa de point-in-time para PQ-92 y PQ-93"
    `closedTime` llega **después** de que el resultado ya se sabe: en 201 de los 212 mercados
    coherentes de la muestra, el último precio antes del cierre ya está por debajo de 0,05 o por
    encima de 0,95. Si el backtest opera hasta `closedTime`, compra con el
    resultado conocido. El silver de PQ-92 tiene que fijar un corte anterior (por ejemplo,
    `endDate` del mercado o el inicio del evento) y PQ-93 debe aplicar a esa regla la guía
    `doubt-driven-development`. Además, `endDate` no siempre es la fecha real: hay mercados que
    se cierran meses antes porque el evento ocurrió antes (en la prueba piloto, uno con `endDate`
    en noviembre de 2024 cerró en marzo).

## 5. Lo que falta: libro de órdenes histórico

El CLOB solo da el libro **actual** (`/book`). No hay libro histórico por API. La épica PQ-11
plantea una estrategia **maker**, y un backtest maker necesita saber si una orden pasiva se habría
llenado. Con las fuentes públicas solo cabe aproximarlo con las operaciones. Dar por llenada una
orden de compra a precio `q` si hubo después una operación a `q` es optimista, porque no se sabe
su lugar en la cola. Exigir una operación estrictamente por debajo de `q` es la variante
conservadora. PQ-87 debe elegir entre:

1. una hipótesis **taker** sobre el historial de precios, que paga la comisión taker, o
2. una hipótesis **maker** con fills simulados desde las operaciones, fijando antes cuál de las
   dos reglas se usa. Las operaciones solo cubren unos tres años (§3).

## 6. Costes por mercado

Gamma trae en cada mercado `feeType` (por ejemplo, `politics_fees`), `feesEnabled`,
`takerBaseFee`, `makerBaseFee`, el tick mínimo (`orderPriceMinTickSize`, 0,001 en los mercados
consultados) y el tamaño mínimo (`orderMinSize`, 5). La fórmula de la comisión taker y las tasas por
categoría están en [compliance/polymarket.md](../compliance/polymarket.md) §2.

**Por verificar en PQ-92:** las unidades de `takerBaseFee` y `makerBaseFee` (en los mercados
consultados valen 1000) y desde cuándo `feesEnabled` es verdadero. Un backtest de 2023 con las
comisiones de 2026 sería pesimista; uno de 2026 sin ellas, optimista.

## 7. Acceso y licencia

- **Bolivia sigue sin bloqueo:** `GET https://polymarket.com/api/geoblock` respondió
  `{"blocked": false, "country": "BO"}` el 2026-11-24, igual que el 2026-10-30
  ([compliance/polymarket.md](../compliance/polymarket.md)).
- **Términos de uso** (vigentes desde el 11-ago-2026, [polymarket.com/tos](https://polymarket.com/tos)):
    - la licencia es «personal, limited, revocable, non-exclusive»;
    - se prohíbe el scraping con robots o crawlers;
    - se prohíbe redistribuir o explotar comercialmente los datos ante «Capital Market Clients»
      sin acuerdo escrito.
- **Consecuencias para el proyecto:**
    - Usar la API pública para investigación propia encaja en esos términos.
    - Los datos crudos se quedan en el lakehouse local (`data/`, fuera de git) y no se publican.
      Los documentos muestran solo cifras agregadas.
    - El script respeta los límites de peticiones y no extrae nada de la web.
- No hay una licencia abierta de los datos. Si en el futuro la plataforma se ofreciera a terceros,
  habría que volver a revisar esto.

## 8. Recomendaciones para los tickets siguientes

**PQ-87 (pre-registro).**

- La carpeta es `docs/estrategias/04-polymarket/`: el `03-` ya es de momentum (PQ-114). Las
  descripciones de PQ-87 y PQ-93 dicen `03-polymarket/`.
- El universo empieza en 2023-01. Las reglas de inclusión se fijan antes de mirar precios:
    - volumen mínimo;
    - categorías (las comisiones y el sesgo favorito-longshot cambian por categoría,
      [notas](notas/edges_alternativos_y_contradicciones.md));
    - qué hacer con los mercados `negRisk` de varios resultados.
- Elegir entre hipótesis taker y maker sabiendo que no hay libro histórico (§5).
- Fijar el corte point-in-time: cuántas horas antes del evento se deja de operar.
- Reservar el holdout por fecha de `endDate`, por ejemplo los últimos 6 meses, y no tocarlo.

**PQ-92 (ingesta).**

- Bronze: catálogo de Gamma, series del CLOB por resultado (diaria completa más ventanas de 15
  días por minuto u hora cerca del cierre) y operaciones v2.
- Las operaciones primero, porque la ventana de tres años avanza cada día.
- Silver point-in-time:
    - `knowledge_time` de la resolución = `closedTime`;
    - corte de operación anterior al evento;
    - el tramo final en 0,5 con el libro vacío como faltante;
    - resoluciones casi 0/1 redondeadas;
    - `["0", "0"]` y 50/50 excluidas.
- Verificar qué es `p` y las unidades de `takerBaseFee`/`makerBaseFee`.
- Paginar Gamma por ventanas de fecha (como el script) o con `/markets/keyset`, que avanza con
  `after_cursor`, no con `next_cursor`.

**PQ-93 (evaluación).**

- Aplicar `doubt-driven-development` al corte point-in-time y a la simulación de fills.

## Fuentes

- Documentación oficial consultada el 2026-11-24:
  [rate limits](https://docs.polymarket.com/quickstart/introduction/rate-limits),
  [Data API v2](https://docs.polymarket.com/api-reference/data-api/overview),
  [migración v1 → v2](https://docs.polymarket.com/migrate/data-api-v1-to-v2.md),
  [prices-history](https://docs.polymarket.com/api-reference/markets/get-prices-history.md),
  [términos de uso](https://polymarket.com/tos).
- Mediciones: `scripts/spike_polymarket.py`. El JSON de salida no se versiona: trae los
  identificadores de la muestra, no las series.
