# Paper trading del carry H2

El runner opera la estrategia H2 (SOL, BNB y XRP, k = 9, θ = 20 %) con **datos en vivo** de la API
pública de Binance y un **bróker simulado**: no necesita claves ni mueve dinero. Las decisiones
salen de la misma función que el backtest (`domain/carry_rules.decide`). Cuando PQ-52 conecte
Binance Demo, se cambia el bróker y nada más.

## Arrancar

```bash
uv run pq paper run --once        # un ciclo y termina: para probar
uv run pq paper run               # bucle: un ciclo cada 60 s (Ctrl+C para detener)
uv run pq paper run --capital 1000 --interval 60 --symbols SOLUSDT,BNBUSDT,XRPUSDT --k 9 --theta 0.20
```

- No arranca con `PQ_ENVIRONMENT=live`.
- Solo puede haber **un runner por carpeta**: un segundo `pq paper run` se niega a arrancar
  (bloqueo en `data/paper/runner.lock`).
- `--once` termina con código 1 si el ciclo no fue sano: sirve para un cron o un smoke test.
- Si falla con `CERTIFICATE_VERIFY_FAILED`, la red está interceptando el TLS: ver
  [KE-015](errores-conocidos.md).
- El capital solo se usa la primera vez. Después manda el estado guardado del bróker.

## Vigilarlo

- **Dashboard:** pestaña «¿Cómo va en vivo?» (`make dashboard`).
- **Telegram:** kill-switch, pata sin cubrir, drawdown y resumen diario. Ver
  [alertas del paper trading](alertas.md#alertas-del-paper-trading-pq-55).
- **Vigilante:** un proceso caído no puede avisar de su propia caída. Junto al runner, corre:

    ```bash
    uv run pq paper watchdog            # bucle: revisa el heartbeat cada 60 s
    uv run pq paper watchdog --once     # una revisión, para cron (código 1 si no está sano)
    ```

    Alerta en cada **cambio** de estado (caído, con fallos, de vuelta) y repite cada hora mientras
    siga mal. El estado se guarda en `data/paper/watchdog.json`.

## Qué hace cada ciclo

El runner trabaja **por niveles**. Cada decisión deja en el diario el **estado deseado** del símbolo
(dentro o fuera, y si toca rebalancear), y cada ciclo lleva las posiciones a ese estado.

1. Comprueba el kill-switch. Si está activado, cierra todas las posiciones y no abre nada.
2. Pide precios (spot y mark price del perpetuo). Si falta alguno, el ciclo no decide nada y el
   heartbeat queda en `ok: false`.
3. Valora la cartera y aplica los límites de riesgo. Las violaciones graves activan el kill-switch.
4. Por cada liquidación de funding nueva: cobra o paga el funding **sobre la posición que había
   antes de esa liquidación** (aunque la tasa se publique y se procese minutos después) y decide
   con la misma regla que el backtest. Registra la decisión y el estado deseado en un
   `FundingSettled`. Si la API de funding falla, la reconciliación sigue con el estado deseado
   que ya hay en el diario: una salida decidida se ejecuta igual.
5. Reconcilia cada símbolo con su estado deseado, **una hora después de la decisión**
   (enmienda 1.1 del pre-registro: vela que abre en t + 1 h).
   - Fuera y con posición: cierra las dos patas (`salida`).
   - Dentro y sin posición: abre las dos patas (`entrada`).
   - Dentro con una pata sola o con el signo cambiado: la completa (`reparacion`).
   - Dentro, cubierto, y una decisión pidió rebalancear: lleva las dos patas al objetivo, una sola
     vez (`rebalanceo`). Una decisión posterior no aplaza un rebalanceo pendiente (importa con
     funding de 1 h, cuando la liquidación siguiente llega antes de que pase la latencia).
   - «Cubierto» es spot largo, perpetuo corto y desbalance por debajo de la mitad de
     `PQ_RISK_MAX_HEDGE_IMBALANCE`. Por encima se repara antes de que cuente como violación.
   - Las dos patas se aprueban antes de enviar ninguna. Si el riesgo rechaza una, no se envía
     ninguna y se vuelve a intentar en el ciclo siguiente. El rechazo queda en el diario una vez.
6. Registra la valoración (cada 15 min o cuando hubo movimiento) y escribe el heartbeat.

Gracias a la reconciliación, un fallo entre las dos patas o una caída entre la decisión y las
órdenes se corrigen en el ciclo siguiente. Mientras tanto, la pata sola cuenta como desbalance, y
si dura más que la gracia (`PQ_RISK_IMBALANCE_GRACE_SECONDS`), activa el kill-switch.

## Archivos (en `data/paper/`)

| Archivo | Qué es |
|---|---|
| `diario.jsonl` | Diario append-only: `RunnerStarted`, `FundingSettled` (con la decisión y `S_k`), `SignalGenerated`, `OrderSubmitted`, `OrderFilled`, `PortfolioValued`, `RiskLimitBreached` |
| `broker-simulado.json` | Efectivo, posiciones y última liquidación aplicada del bróker simulado |
| `heartbeat.json` | Último ciclo: hora, `ok`, detalle de lo que falló (precios, un símbolo, un hueco), bróker y kill-switch |
| `runner.lock` | Bloqueo de instancia única (lo libera el sistema si el proceso muere) |
| `KILL_SWITCH` | Existe solo si el kill-switch está activado ([runbook](kill-switch.md)) |

Ver el estado:

```bash
cat data/paper/heartbeat.json      # estado del runner
tail -n 5 data/paper/diario.jsonl  # últimos eventos
uv run pq paper status             # solo el kill-switch
```

## Reiniciar

Detener (Ctrl+C) y volver a arrancar es seguro.

- **Fuentes de verdad:** posiciones y efectivo viven en `broker-simulado.json`; el historial, las
  liquidaciones procesadas y el estado deseado, en el diario. Si hay diario pero falta el estado
  del bróker, el runner no arranca: restaura el archivo o aparta la carpeta.
- El bróker aplica cada liquidación una sola vez. Si el diario no llegó a registrarla, el
  reintento la anota con su importe sin cobrarla otra vez.
- Tras una caída, el runner se pone al día: cobra las liquidaciones perdidas y decide con todas
  ellas, en orden. Después reconcilia hacia el estado final, sin las órdenes intermedias.
- Si la caída fue más larga que la ventana de 90 liquidaciones (30 días con intervalos de 8 h),
  el heartbeat avisa de un **hueco**: esas liquidaciones no se cobraron ni se decidieron.
- **Arranque en frío** (sin diario): el estado de la histéresis se reconstruye recorriendo las
  últimas 90 liquidaciones desde «fuera». Coincide con el backtest salvo que este llevara dentro
  más tiempo que la ventana con `S_k` entre θ/2 y θ.
- Al rearmar el kill-switch, el runner vuelve al estado deseado: si la estrategia está dentro,
  **entra en el ciclo siguiente**.
- Cambiar `--symbols` con posiciones abiertas en un símbolo que sale de la lista no se permite:
  ciérralas antes (kill-switch) o mantén el símbolo.

Para empezar de cero, mueve la carpeta y no la borres: es el historial del paper trading.

```bash
mv data/paper data/paper-$(date +%Y%m%d)
```

## Diferencias con el backtest

| Aspecto | Backtest | Paper (bróker simulado) |
|---|---|---|
| Decisión | `carry_rules.decide` | La misma función. Paridad de entradas y salidas verificada en un test, con precios que se mueven y arranque a mitad del historial |
| Momento de ejecución | Open de la vela que abre en *t* (ver KE-016) | Primer ciclo desde *t* + 1 h, como dice la enmienda 1.1 |
| Precio de ejecución | Open de esa vela; slippage como coste | Último precio de valoración ± slippage |
| Tamaño por pata | Parte del símbolo / 2, con un libro por símbolo | Equity total / n / 2, acotado por los límites de riesgo y menos un margen del 2 % |
| Funding perdido en una caída | No aplica | Se cobra al mark price del momento en que vuelve |
| Entradas fuera de *t* + 1 h | Nunca | Arranque en frío «dentro» y rearme del kill-switch: se entra en el ciclo siguiente |
| Precio del perpetuo | Velas de la kline (precio de operaciones) | Mark price de `premiumIndex` |

El tamaño conjunto, y no por símbolo, cambia cuándo salta el umbral de rebalanceo del 10 %: el
funding o las pérdidas de un símbolo mueven el objetivo de los demás. Por eso la paridad se exige en
entradas y salidas, no en rebalanceos ni en tamaño. El paper trading no es una evaluación del
pre-registro y no cuenta en N.

## Limitaciones conocidas

- Ejecutar al precio actual no es el precio real de Binance Demo: esa diferencia la mide PQ-95.
- Tras un reinicio, la antigüedad de un desbalance de patas empieza de cero, así que la gracia
  se cuenta de nuevo.
- Si el diario falla justo después de una orden, el fill queda en el bróker y no en el diario.
  Si el envío falla después de escribir `OrderSubmitted`, queda una orden sin fill; la
  reconciliación del ciclo siguiente la repite con otro `client_order_id`.
- Si falta el precio de un símbolo, el ciclo entero se salta, incluido el cierre del
  kill-switch, hasta que vuelva el precio.
- Tras un reinicio, la equity de inicio del día es la primera valoración registrada ese día, que
  se escribe al final del ciclo; en un proceso continuo es la del inicio del primer ciclo.
- El intervalo de cada liquidación se deduce de la distancia a la anterior. No está contrastado
  con la columna `funding_interval_hours` de Data Vision que usa el silver.
- `RiskManager.pre_trade` usa las órdenes pendientes para decidir si una orden reduce, pero no
  las suma a la exposición. Con el bróker simulado no hay pendientes, porque se ejecuta al
  instante. Hay que cubrirlo antes de Binance Demo (PQ-52).
- Con el kill-switch activado, el diario sigue registrando las decisiones de la estrategia
  (`FundingSettled`) sin órdenes. Para saber si se ejecutaron, crúzalas con `KillSwitchTripped`
  y `KillSwitchReset`.
