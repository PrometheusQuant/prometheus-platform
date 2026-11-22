# Desconexión del exchange (SEV-2)

## Cuándo aplica

- **Alerta en Telegram** `paper_market_unavailable` (ERROR) o del vigilante: «con fallos» (ERROR),
  o «caído» o «sin heartbeat» (CRITICAL).
- `/estado` muestra el runner con fallos y un detalle como `SOLUSDT: MarketDataError`.
- En los logs aparece `market_stream_fallback`: el websocket dejó de dar precios frescos (más de
  15 s) y el runner pasó a la API REST. **Esto solo no es un incidente:** el runner sigue operando.

## Qué hace el sistema solo

- **Websocket caído:** usa REST para los precios y avisa una vez (`market_stream_fallback`). Al
  volver, registra `market_stream_recovered`.
- **REST también caído:** el ciclo se salta, el heartbeat queda con `ok: false` y el vigilante
  alerta al cambiar de estado. No se envían órdenes sin precios.
- **Al volver la conexión:** el runner trabaja por niveles. El estado deseado está en el diario y
  el ciclo siguiente reconcilia solo; no hay que reiniciar nada.
- **El carry es delta-neutral:** un corte no deja exposición al precio mientras las dos patas
  sigan abiertas. El riesgo es no poder rebalancear si el precio se mueve mucho.

## Pasos

1. **¿Somos nosotros o el exchange?** Desde el servidor (o la laptop):

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=SOLUSDT"
   curl -s -o /dev/null -w "%{http_code}\n" "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT"
   ```

   | Resultado | Qué significa | Qué hacer |
   |---|---|---|
   | `200` en los dos | El exchange responde; el problema es del proceso | Revisar los logs del runner y reiniciarlo ([paper trading](paper-trading.md)) |
   | `000` o un timeout | No hay red hacia el exchange | Revisar la red. En la universidad, el firewall bloquea Binance (KE-015): usar el hotspot del celular |
   | `451` o `403` | El exchange bloquea la IP o la región | El servidor está en una región restringida: no se arregla esperando ([Oracle](oracle-cloud.md), regla de región) |
   | `5xx` | Caída del exchange | Mirar la página de estado del exchange y esperar |

2. **Si hay posición abierta y el corte dura más de 1 h** (el RTO del [BIA](analisis-de-impacto.md)):
   entra a la web o la app del exchange, revisa que las dos patas sigan abiertas y con margen, y
   decide si cerrarlas a mano. El kill-switch no puede cerrar nada sin conexión: actúa cuando esta
   vuelve.
3. **Al volver la conexión:** confirma con `/estado` que el runner está sano y que las posiciones
   coinciden con las del exchange.

## A quién avisar

Al equipo por el grupo de Telegram si el corte supera los 15 minutos con posición abierta. Si se
cerraron posiciones a mano, abre un post-mortem.

## Simulacros

| Fecha | Tipo | Resultado |
|---|---|---|
| 2026-11-22 | Runner real con el bróker simulado, sobre una copia del estado, con la red cortada por un proxy inexistente | En el primer ciclo (5 s): `paper_market_unavailable`, heartbeat `ok: false` con `SOLUSDT: MarketDataError`, sin órdenes, y el vigilante respondió «con_fallos» (salida 1). Con la red de vuelta, el ciclo siguiente quedó sano y el vigilante respondió «ok». **Pendiente:** repetirlo con el runner en Demo (PQ-52) |
| — | Prueba automática de caos (PQ-80) | Corte del websocket: el runner cae a REST y el estado no cambia (en la CI) |
