# ADR-0011: las estrategias se conectan por un puerto `Strategy` con instantáneas point-in-time

- **Estado:** Aceptada
- **Fecha:** 2026-11-08
- **Ticket:** PQ-113

## Contexto y problema

Desde el Sprint 3 hay dos carriles. David mantiene el runner, el riesgo y la ejecución. Boris va a
conectar estrategias nuevas: la tendencia (PQ-82) y Polymarket. Sin un contrato pasan tres cosas:

- **Cambios en el núcleo ajeno:** cada estrategia nueva toca el runner, y los dos carriles chocan.
- **Look-ahead:** cada estrategia tiene que acordarse de no usar datos futuros.
- **Paridad:** nada garantiza que la estrategia decida en paper igual que en el backtest. En paper
  solo hay una ventana de historia; en el backtest, todo el pasado. La revisión de PQ-54 encontró
  justo ese tipo de divergencia en el carry: el arranque en frío y la histéresis.

## Opciones consideradas

1. **Puerto propio**: un `Protocol` en `domain/ports.py`. Recibe una instantánea point-in-time y
   devuelve `Signal`. Una prueba de contrato reutilizable lo hace cumplir.
2. **La API de estrategias de NautilusTrader** ([ADR-0006](0006-nautilustrader-para-ejecucion.md)).
   Ata cada estrategia al motor de ejecución y a sus eventos. Hoy el runner usa un bróker
   simulado propio y no Nautilus, y la investigación corre sobre Polars.
3. **Sin contrato**: cada estrategia con su propio runner. Duplica riesgo, kill-switch y diario, y
   es lo que más choques entre carriles produce.

## Decisión

Opción 1.

- **`MarketSnapshot`** (`domain/market.py`):
  - lleva `as_of` y las series de velas y de funding por instrumento, ordenadas;
  - **rechaza al construirse** cualquier dato con `knowledge_time > as_of`, así que el look-ahead
    se detiene en un solo sitio;
  - `snapshot_at` la corta del historial en `as_of` y, opcionalmente, en una ventana.
- **`Strategy`** (`domain/ports.py`), con `strategy_id`, `instruments`, `lookback` y
  `on_snapshot(snapshot) -> list[Signal]`:
  - devuelve pesos objetivo en [-1, 1]; no ve la ejecución, el riesgo, el reloj ni la red;
  - puede tener estado (la histéresis del carry), pero debe ser determinista;
  - `lookback` declara cuánta historia necesita cada instantánea.
- **Prueba de contrato** (`tests/contract/strategy_contract.py`). Toda estrategia que vaya al
  runner se añade a `STRATEGIES` en `tests/unit/strategies/test_strategy_contract.py` y debe
  pasar tres comprobaciones:
  1. señales válidas: su id, `generated_at = as_of`, solo instrumentos declarados y una por
     instrumento;
  2. determinismo: dos instancias nuevas con las mismas instantáneas dan las mismas señales;
  3. **paridad backtest ↔ paper:** con todo el pasado y con solo la ventana `lookback`, recibida
     de forma incremental como en vivo, da las mismas señales.

  La prueba incluye tres estrategias defectuosas que debe rechazar: una que usa más historia de la
  que declara, una con azar y una con la hora equivocada.
- **Ejemplo:** `CarryStrategy` cumple el puerto y pasa el contrato. Se probó con H2 y con
  k = 3, θ = 10 %, con un tramo de intervalo de 4 h.

## Consecuencias

- **Positivas:**
  - Boris escribe su estrategia contra el puerto y la prueba sin tocar el runner.
  - El look-ahead y las divergencias por ventana se detectan en la CI, no en paper trading.
- **Negativas y riesgos:**
  - **El runner todavía no ejecuta cualquier `Strategy`.** Sabe operar el carry: dos patas,
    funding y su reconciliación (PQ-54). Para conectar otra estrategia falta un ejecutor genérico
    que convierta los pesos objetivo de `Signal` en órdenes, pasando por `pre_trade`, el
    kill-switch y el diario. Es PQ-116, del carril de David, previo a PQ-82.
  - Las señales son pesos de la cartera de la estrategia. El tamaño final lo decide el runner con
    los límites de riesgo.
- **Qué la revertiría:** adoptar NautilusTrader como motor también de paper. Entonces el puerto se
  adaptaría a su API de estrategias, y la prueba de contrato seguiría valiendo.
