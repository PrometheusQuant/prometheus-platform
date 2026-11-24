# ADR-0014: CCXT detrás de los puertos propios para ejecutar en Binance Demo y Bybit testnet

- **Estado:** Aceptada
- **Fecha:** 2026-11-24
- **Ticket:** PQ-51 (reemplaza a [ADR-0006](0006-nautilustrader-para-ejecucion.md))

## Contexto y problema

El ADR-0006 proponía NautilusTrader para el backtest, el paper y el vivo. Desde entonces la
plataforma construyó su propio circuito:

- el runner de paper, con reconciliación por nivel y kill-switch;
- un diario append-only;
- el control de riesgo pre-trade (PQ-119);
- el contrato `Strategy` (ADR-0011);
- el puerto `OrderGateway`, que hoy implementa un bróker simulado.

Lo que falta es un adaptador que mande órdenes **reales** a Binance Demo (spot y USDⓈ-M, PQ-52) y
a Bybit testnet (PQ-100) detrás de ese puerto.

## Opciones consideradas

1. **NautilusTrader** (LGPL-3.0). La última versión estable en PyPI sigue siendo la 1.231.0. Su
   adaptador de Binance tiene un modo `DEMO`, pero usarlo implica sustituir el runner, el diario y
   el riesgo propios por su motor de eventos.
2. **Adaptador propio sobre la API REST** (httpx, ya en el proyecto). Sin dependencias nuevas, pero
   todo lo que el spike encontró se resuelve a mano: firma, sincronización del reloj, filtros de
   precio y cantidad, límites de tasa y diferencias entre exchanges.
3. **CCXT** (MIT) detrás del puerto `OrderGateway`. Tiene una API unificada para Binance y Bybit y
   soporta Demo Trading (`enable_demo_trading`). Resuelve el redondeo (`amount_to_precision`,
   `price_to_precision`), el reloj (`adjustForTimeDifference`) y el límite de tasa
   (`enableRateLimit`).

## Decisión

**CCXT detrás de los puertos propios.** NautilusTrader se descarta para el MVP.

La prueba del spike (2026-11-24, con las claves Demo de PQ-17) se resume en
[spike de ejecución](../investigacion/2026-11-24-spike-ejecucion-binance-demo.md):

- **Con CCXT 4.5.94 en spot demo:** se leyó el saldo (5.000 USDT de prueba), se colocó una orden
  límite (estado `open`, 335 ms) y se canceló. El precio y la cantidad salieron redondeados según
  los filtros del par.
- **Con REST a mano, el mismo flujo** funcionó solo después de corregir dos fallos que CCXT evita
  solo:
  - el filtro `PERCENT_PRICE_BY_SIDE`, que rechaza precios a más de cierta distancia del mercado;
  - un reloj de WSL que va entre 0,6 y 1,4 s **atrasado**, con lo que el timestamp corregido
    quedaba adelantado y Binance lo rechazaba (no acepta más de 1 s de adelanto).
- **En USDⓈ-M demo,** al principio las dos vías respondían «Margin is insufficient», porque la
  billetera de futuros demo **no se activa hasta abrirla una vez en la web**. Después, CCXT colocó
  y canceló una orden de venta (`open`, 462 ms) con 5.000 USDT de prueba.

**El runner, el diario, el riesgo y las estrategias no cambian.** CCXT vive solo en `adapters/`,
detrás de `OrderGateway`, y ninguna otra capa lo importa (lo verifica import-linter).

## Consecuencias

- **Positivas:**
  - Bybit testnet (PQ-100) reutiliza el mismo adaptador con otro `exchange_id`.
  - El redondeo, el reloj y los límites de tasa dejan de ser código propio.
  - La licencia MIT es compatible con Apache-2.0.
- **Negativas y riesgos:**
  - CCXT es una dependencia grande, con publicaciones muy frecuentes: se fija la versión en
    `uv.lock` y se revisa con `make audit`.
  - `load_markets` tarda unos 6,5 s, así que se carga una vez al arrancar, no en cada ciclo.
  - Los nombres de símbolo de CCXT (`SOL/USDT`, `SOL/USDT:USDT`) se traducen en el adaptador.
  - Las claves solo llegan desde `Settings` (`.env`).
- **Qué la revertiría:**
  - que CCXT dejara de soportar el Demo Trading de Binance o el testnet de Bybit;
  - que hiciera falta backtest event-driven con libro de órdenes. En ese caso se reevalúa
    NautilusTrader v2 cuando sea estable.
