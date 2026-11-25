# Spike: motor de ejecución en Binance Demo (PQ-51)

- **Fecha:** 2026-11-24.
- **Time-box:** 1 día.
- **Decisión:** [ADR-0014](../adr/0014-ccxt-detras-de-los-puertos-para-ejecutar.md), CCXT detrás de
  los puertos propios.
- **Claves:** las de Binance Demo del titular (PQ-17). Se leen del `.env`, no se imprimen, y todo
  el dinero es ficticio.
- **Scripts:** no se versionan, porque eran pruebas desechables. Este documento recoge todo lo que
  midieron.

## Qué se probó

En cada mercado (spot `demo-api.binance.com` y USDⓈ-M `demo-fapi.binance.com`), con SOLUSDT:

1. leer el saldo;
2. leer los filtros del par;
3. colocar una orden **límite lejos del mercado**, que no se ejecuta;
4. cancelarla.

Se hizo con REST firmado a mano (httpx) y con CCXT 4.5.94.

| Comprobación | REST propio (httpx) | CCXT 4.5.94 |
|---|---|---|
| Soporte de Binance Demo | URLs a mano | `enable_demo_trading(True)`, que apunta a `demo-api` y `demo-fapi` |
| Saldo spot | ✅ 5.000 USDT y 5.000 USDC de prueba (333 ms) | ✅ 5.000 USDT libres |
| Orden y cancelación en spot | ✅ al tercer intento (ver riesgos), ~340 ms por petición | ✅ al primer intento: `open` (335 ms) y luego `canceled` |
| Redondeo de precio y cantidad | A mano (`tickSize` 0,01, `stepSize` 0,001, nocional mínimo 5) | `price_to_precision` y `amount_to_precision` |
| Reloj | Desfase medido a mano y corregido con margen | `adjustForTimeDifference` |
| Saldo, posición y funding en USDⓈ-M | ✅ responden (posición y funding vacíos) | ✅ |
| Orden en USDⓈ-M | ❌ al principio: «Margin is insufficient» (billetera de futuros demo sin activar) | ✅ tras activarla: `open` (462 ms), luego `canceled` |
| Carga inicial | — | `load_markets` tarda ~6,5 s |

**NautilusTrader:** la última versión estable en PyPI es la 1.231.0, la misma del ADR-0006. Su
adaptador de Binance tiene un entorno `DEMO`, pero adoptarlo obliga a cambiar el runner, el diario
y el riesgo propios por su motor. Para un MVP de dos semanas es el cambio más caro y no aporta lo
que falta, que es un adaptador detrás de `OrderGateway`.

## Riesgos anotados

1. **Sincronización del reloj.**
   - El reloj de WSL fue entre 0,6 y 1,4 s **por detrás** de Binance.
   - Si se suma el desfase completo, el timestamp queda adelantado y Binance lo rechaza: «Timestamp
     for this request was 1000ms ahead», porque tolera como mucho 1 s de adelanto.
   - **Mitigación:** CCXT con `adjustForTimeDifference`. Si se usa REST, desfase menos 1,5 s con
     `recvWindow` de 5 s.
2. **Filtros de precio.** `PERCENT_PRICE_BY_SIDE` rechaza las órdenes límite muy alejadas del
   precio de mercado: una a −50 % se rechazó y una a −10 % se aceptó. Para el carry no importa,
   porque ejecuta a mercado, pero sí para las pruebas.
3. **Redondeo de cantidades:**
   - `stepSize` 0,001 en spot y 0,01 en USDⓈ-M para SOL;
   - nocional mínimo de 5 USDT en los dos.

   **Las dos patas del carry tienen pasos distintos.** Al redondear, la cobertura no es exacta y el
   residuo hay que vigilarlo (el monitor de desbalance de patas ya existe).
4. **Límites de tasa.**
   - El spot informa el peso usado (`x-mbx-used-weight-1m`: 44–89 tras unas pocas peticiones, de
     6.000 por minuto). El demo de futuros devuelve `-1`.
   - **Mitigación:** `enableRateLimit` de CCXT. El runner cicla cada 60 s, muy lejos del límite.
5. **La billetera de futuros demo se activa al abrirla en la web.**
   - Hasta que el titular entró una vez en la pantalla *Futures* del demo, la API la veía en 0 y
     rechazaba las órdenes por margen.
   - Después mostró 5.000 USDT y 5.000 USDC de prueba, sin transferir nada.
   - La API demo no expone `/sapi`, así que las transferencias por API dan 404.

## Futuros: criterio cerrado (2026-11-24)

Después de que el titular abriera la pantalla *Futures* del demo, CCXT leyó 5.000 USDT libres en
USDⓈ-M, colocó una orden límite de venta de 0,16 SOL a 76,69 (estado `open`, 462 ms) y la canceló.
Con eso se cumple el criterio del ticket en los dos mercados.
