# Alertas a Telegram

Todo evento de log con nivel **ERROR** o **CRITICAL** (incluido `log.exception(...)`) se reenvía
como alerta. El código está en `ops/alerting.py` y `adapters/notifiers.py` (patrón Observer).

## Configurar el bot (una vez)

1. En Telegram, hablar con **@BotFather** → `/newbot` → copiar el token.
2. Escribir cualquier mensaje al bot nuevo y abrir
   `https://api.telegram.org/bot<TOKEN>/getUpdates`; el `chat.id` de la respuesta es el chat. Para
   un grupo, agregar el bot al grupo y repetir (el id es negativo).
3. Completar en `.env` (que git ignora):

    ```
    PQ_TELEGRAM_BOT_TOKEN=123456:ABC...
    PQ_TELEGRAM_CHAT_ID=987654321
    PQ_ALERT_TIMEZONE=America/La_Paz   # opcional; es el valor por defecto
    ```

4. Probar: `uv run pq alert test`. Debe responder `canal=TelegramNotifier entregada=sí` y llegar
   un mensaje `[WARNING] alerta de prueba`.

### Un grupo en vez de un chat privado

Para que las alertas lleguen a un grupo (por ejemplo, el de David y Boris), sin que el token pase
por el navegador:

1. Agrega el bot al grupo y escribe en él `/start@<usuario_del_bot>`. Con el modo de privacidad
   activado, el bot solo ve los comandos que lo nombran; este registra el grupo.
2. Busca el id del grupo. El comando imprime id, tipo y título de cada chat, nunca el token:

    ```bash
    set -a && . ./.env && set +a && curl -s "https://api.telegram.org/bot${PQ_TELEGRAM_BOT_TOKEN}/getUpdates" \
      | python3 -c "import json,sys; r=json.load(sys.stdin).get('result',[]); [print(c['id'], c.get('type'), c.get('title') or c.get('first_name')) for c in {(u.get('message') or u.get('my_chat_member') or {}).get('chat',{}).get('id'): (u.get('message') or u.get('my_chat_member') or {}).get('chat') for u in r}.values() if c]"
    ```

3. Pon en `.env` `PQ_TELEGRAM_CHAT_ID=<id negativo del grupo>` y prueba con `uv run pq alert test`.
4. Si responde `chat not found`, el grupo pasó a supergrupo y cambió de id (empieza por `-100`):
   repite el paso 2.

## Qué canal se usa

| Configuración | Canal |
|---|---|
| Token y chat definidos | Telegram |
| Sin Telegram, entorno `paper` o `live` | Consola (bloque `ALERTA` en stderr) |
| Sin Telegram, entorno `dev` | Ninguno: el error ya se ve en la terminal |

## Garantías

- **Sin secretos:** la alerta se arma *después* de enmascarar secretos, igual que el log.
- **No rompe el proceso:** si Telegram no responde (timeout de 5 s), se escribe
  `telegram_alert_failed` en stderr, con el tipo de error o el código HTTP. Nunca se escribe el
  mensaje de la excepción, porque podría contener la URL con el token.
- **Sin inundar el canal:** el mismo evento solo se reenvía una vez cada 5 minutos.

## Alertas del paper trading (PQ-55)

| Alerta | Severidad | Quién la emite |
|---|---|---|
| Kill-switch activado | CRITICAL | `kill_switch_tripped`, `kill_switch_active` |
| Pata sin cubrir | CRITICAL | `paper_unhedged_leg`: una pata sola, un signo cambiado o un desbalance mayor que `PQ_RISK_MAX_HEDGE_IMBALANCE` |
| Runner caído o sin heartbeat | CRITICAL | `pq paper watchdog`: el heartbeat tiene más de `PQ_PAPER_HEARTBEAT_MAX_AGE_MINUTES` |
| Ciclo con fallos (API, un símbolo, un hueco) | ERROR | `pq paper watchdog` y `paper_symbol_failed` |
| Drawdown mayor que `PQ_PAPER_DRAWDOWN_ALERT` | ERROR | `paper_drawdown`, una vez por cruce; se rearma al recuperar la mitad |
| Resumen diario: órdenes, funding, comisiones, slippage, equity | INFO | El runner, al cambiar el día UTC |
| El runner volvió a reportar | INFO | `pq paper watchdog` |

Las alertas INFO no salen de los logs: el runner y el vigilante las envían directamente al canal.
Ninguna orden individual genera alerta: van en el resumen diario.

## Si no llegan

| Síntoma | Causa probable |
|---|---|
| `HTTP 401` | Token mal copiado o revocado |
| `HTTP 400` | `chat_id` incorrecto, o nunca se le escribió al bot |
| `error de red (ConnectTimeout)` | Sin salida a internet o api.telegram.org bloqueado |
| `sin canal de alertas` | Faltan las variables en `.env` |
| `getUpdates` responde `{"ok": true, "result": []}` | El token es válido, pero ese bot no tiene mensajes: el token es de otro bot, se le escribió a un bot de nombre parecido o el mensaje tiene más de 24 h. Abre `.../bot<TOKEN>/getMe`, entra a `t.me/<username>` que indica, envía un mensaje y repite |

La URL `api.telegram.org/bot<TOKEN>/...` queda en el historial del navegador: bórrala al terminar.
Si el token se filtra, `/revoke` en @BotFather y actualiza `.env`.

## Hora de las alertas

Las alertas muestran primero la hora local y entre paréntesis la UTC:
`hora=2026-11-06 13:27:37 -04 (17:27:37 UTC)`. Logs y datos siguen en UTC, que es la referencia
para cruzar una alerta con los logs. La zona se cambia con `PQ_ALERT_TIMEZONE` (nombre IANA, por
ejemplo `America/Bogota`); un nombre inválido hace fallar el arranque.
