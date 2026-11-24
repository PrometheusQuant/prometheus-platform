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
- **Telegram:** kill-switch, pata sin cubrir, drawdown, resumen diario y resumen semanal. Ver
  [alertas del paper trading](alertas.md#alertas-del-paper-trading-pq-55).
- **Informe semanal en PDF:** ver [abajo](#informe-semanal-pq-85).
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
| `KILL_SWITCH-<id>` | Existe solo si el kill-switch **de esa estrategia** está activado (PQ-83) |

**Compatibilidad del diario.** Cada línea debe traer exactamente los campos de su evento. Solo puede
faltar un campo que se añadió después **con un valor por defecto fijo**, como `marks` en
`PortfolioValued` (PQ-84): así los diarios antiguos se siguen leyendo. Un campo desconocido o un
campo obligatorio que falta detienen la lectura (`JournalCorruptError`), porque no se adivina.

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

## Precios por websocket (PQ-80, opcional)

```bash
uv run pq paper run --market-data stream     # por defecto: --market-data rest
```

- Un hilo lee los streams públicos de Binance: `markPrice@1s` y `kline_1h` de futuros (por la ruta
  `/market`, ver KE-018) y `miniTicker` de spot. Reconecta con espera creciente, y un stream que
  calla 30 s cuenta como corte.
- **El runner usa el precio del stream solo si tiene menos de 15 s.** Si no, lo pide a REST y lo
  registra una vez (`market_stream_fallback`); al volver, `market_stream_recovered`. Una vela de
  1 h que no sigue a la anterior deja `market_stream_gap`.
- Las liquidaciones ya ocurridas, el historial y las velas de las estrategias siguen saliendo de
  REST. El estado vive en el diario y el bróker: un corte de red solo cambia de dónde salen los
  precios (prueba de caos con 5 minutos sin stream).

## Presupuesto de capital (PQ-83)

`uv run pq research budget` calcula el presupuesto recomendado entre las estrategias aprobadas, con
el tope de CVaR y el tope por exchange ([ADR-0012](../adr/0012-presupuesto-de-capital-con-cvar.md)).
Escribe `data/research/budget/summary.json`. **El runner no lo aplica solo** (decisión del titular del
21-nov-2026): el paper es una demostración. Para hacerlo cumplir, se le pasa a mano:

```bash
uv run pq paper run --carry-share 0.10 --exchange-cap BINANCE=0.125
```

- `--carry-share`: parte del capital del carry. El resto queda en efectivo en el bróker.
- `--exchange-cap`: el runner no arranca si las partes de ese exchange suman más que el tope.
- Sin las opciones, el runner opera como siempre: el carry usa lo que dejan las demás estrategias.

## Otras estrategias en el mismo runner (PQ-116)

Además del carry, el runner opera cualquier estrategia que cumpla el puerto `Strategy`
([ADR-0011](../adr/0011-contrato-de-estrategia.md)) y pase la prueba de contrato. Se le pasa en
`build(..., strategies=[StrategyAllocation(estrategia, capital_share)])`. La CLI aún no tiene opción
para elegirlas: la añade la primera estrategia real (PQ-82, tendencia).

| Regla | Detalle |
|---|---|
| Capital | Cada estrategia usa su `capital_share` de la equity; el carry usa el resto. Las asignaciones suman menos de 1 |
| Decisión | Una vez por cierre de vela de 1 h, dos minutos después, con la `MarketSnapshot` de su ventana `lookback`: velas de sus instrumentos y funding de sus perpetuos |
| Datos incompletos | Si falta la vela de un instrumento, no decide y lo reintenta en el ciclo siguiente. A los 10 minutos el heartbeat lo muestra |
| Señales | Se validan como en la prueba de contrato. Una señal inválida no se registra ni se opera, y queda en el heartbeat |
| Latencia | La señal de *t* rige desde *t* + `execution_delay`, 1 h por defecto, como el backtest de la tendencia. Una señal nueva sustituye a la pendiente |
| Órdenes | Por niveles: cada ciclo lleva la posición al peso vigente si se aleja más que `rebalance_band` (10 % del capital asignado por defecto). Pasan por `pre_trade`, el kill-switch y el diario, igual que las del carry |
| Cobertura | Cada instrumento tiene un solo dueño, y un símbolo del carry no puede ser de otra estrategia. La alerta de pata sin cubrir solo vigila los símbolos del carry |
| Reinicio | Las señales salen del diario (`SignalGenerated`): el objetivo sigue aunque la API de velas no responda, y la misma vela no se decide dos veces |

El estado interno de una estrategia con memoria se reconstruye con su ventana `lookback` en la
primera decisión tras un reinicio. La prueba de contrato garantiza que con esa ventana decide igual.

## Página pública de resultados (PQ-89)

[Resultados](../resultados.md) es la página estática que ve el jurado. El QR del póster apunta a
<https://prometheusquant.github.io/prometheus-platform/resultados/>. Muestra los gates, la
validación estadística, la simulación y el paper trading **agregado por día**: sin ids de órdenes,
claves ni cuentas. No expone el dashboard ni el servidor.

Se regenera desde los artefactos y se publica con el workflow de Docs al fusionar el PR:

```bash
uv run pq report public          # escribe docs/resultados.md; no lo edites a mano
```

Mientras no haya servidor se regenera a mano antes de cada demo. Con el servidor (PQ-57), un cron
allí la regenerará y la subirá sola.

## Informe semanal (PQ-85)

Cada semana ISO (lunes a domingo, UTC) tiene dos salidas, y las dos salen de la misma función
(`weekly_summary`), así que nunca dan cifras distintas:

| Salida | Cuándo | Qué trae |
|---|---|---|
| Resumen semanal por Telegram | Solo: el runner lo envía al terminar el domingo UTC, después del resumen diario | Órdenes, funding, comisiones, slippage, equity al cierre, variación, caída máxima dentro de la semana, violaciones de riesgo, kill-switch y PnL por estrategia |
| PDF (Quarto + Typst) | `pq paper weekly-report --pdf` | Lo mismo, con la curva de equity, la tabla por estrategia, los costes reales frente al modelo, la paridad con el backtest y la lista de incidentes |

```bash
uv run pq paper weekly-report                       # entradas de la última semana terminada
uv run pq paper weekly-report --pdf                 # y el PDF (necesita Quarto)
uv run pq paper weekly-report --week 2026-W47 --pdf --send   # una semana concreta, y al grupo
make informe-semanal                                # lo mismo que --pdf, para la última semana
```

Todo queda en `data/informes/paper/<AAAA-Www>/` (el PDF es `informe-paper-<AAAA-Www>.pdf`), fuera
de `data/paper/` para no inflar los respaldos cifrados. Se puede regenerar cuando se quiera: el
diario no cambia.

- **Equity al inicio:** la del cierre de la semana anterior; si el runner arrancó durante la
  semana, la primera valoración.
- **PnL por estrategia:** el acumulado al cierre del domingo menos el acumulado al inicio del
  lunes, con la misma fórmula que la pestaña de cartera del dashboard (PQ-84).
- **Costes reales frente al modelo:** comisión y slippage de cada pata frente a lo que cobraría el
  `CostModel` del backtest para ese símbolo. Con el bróker simulado salen iguales (1,00x) por
  construcción; la cifra dice algo con fills de Binance Demo (PQ-52, PQ-95).
- **Paridad con el backtest:** el retorno de la semana frente a las bandas p5–p95 del carry H2 a
  7 días (remuestreo por bloques del desarrollo, como la pestaña de cartera). Si falta la
  evaluación de H2 queda como n/d. Una semana fuera de la banda es una señal, no una prueba.
- **Incidentes:** violaciones de límites de riesgo y cambios del kill-switch de la semana, con su hora.
- **`--send`:** con `--pdf` manda el PDF al grupo de alertas (`sendDocument`) con el resumen como
  pie; sin `--pdf`, solo el resumen. Sin canal configurado sale con código 1.

En el servidor (PQ-57), un cron lo envía cada lunes, cuando ya están las liquidaciones del domingo:

```bash
# los lunes a las 06:30 UTC; necesita Quarto instalado en el servidor
30 6 * * 1 cd /ruta/prometheus-platform && uv run pq paper weekly-report --pdf --send >> ~/informe-semanal.log 2>&1
```

Mientras no haya servidor, el resumen por Telegram ya llega solo desde la laptop. El PDF se genera a
mano con `make informe-semanal`.

## Binance Demo: órdenes reales con dinero ficticio (PQ-52)

El mismo runner, pero cada pata se ejecuta de verdad en Binance Demo (spot y USDⓈ-M) con las
claves del `.env` (PQ-17). La decisión técnica es el
[ADR-0014](../adr/0014-ccxt-detras-de-los-puertos-para-ejecutar.md).

```bash
cd ~/code/pq-runtime
PQ_ENVIRONMENT=paper setsid nohup uv run --no-sync pq paper run --broker binance-demo \
  --metrics-port 9109 > ~/pq-logs/paper-demo.log 2>&1 &
uv run pq paper status --broker binance-demo
uv run pq paper kill --broker binance-demo --reason "..."   # su propio kill-switch
```

- **Carpeta propia:** `data/paper-binance-demo/`, con su diario, su estado, su bloqueo y su
  kill-switch. El paper simulado de `data/paper/` sigue igual, y los dos pueden correr a la vez si
  usan puertos de métricas distintos.
- **El libro es una subcuenta:** `--capital` (1000 por defecto) dentro de la cuenta demo, que
  tiene más saldo de prueba.
- **Reconciliación al arrancar:** compara el libro con el exchange en los instrumentos del carry.
  Si no cuadran, deja `paper_reconcile_gaps` en el log y no corrige nada solo.
- **Qué se registra:** cada fill lleva el precio medio, la cantidad neta y la comisión reales. En
  una compra spot, Binance cobra el 0,1 % en SOL, así que llega algo menos de lo pedido. El
  slippage es la diferencia con la valoración del ciclo.
- **Comisiones del demo:** no son las de la cuenta real. El 2026-11-24, el USDⓈ-M del demo cobró
  un 0,04 % taker, frente al 0,05 % VIP0 de la cuenta del titular. Para calibrar costes (PQ-95)
  se usan las tarifas reales de PQ-17; los fills del demo sirven para medir el slippage y la
  latencia (≈1,1 s por orden, contando la consulta de comisiones).
- **Prueba de integración** (ida y vuelta de 0,1 SOL en cada mercado, dinero ficticio):
  `PQ_DEMO_INTEGRATION=1 uv run pytest -m demo --no-cov`.
- **Si una orden queda por debajo del mínimo** al redondear (`stepSize`; nocional mínimo de 5
  USDT), se rechaza antes de enviarla con `OrderTooSmallError`.

## Limitaciones conocidas

- Con el bróker simulado, ejecutar al precio actual no es el precio real. Con `--broker
  binance-demo` los fills son reales (PQ-52), y la diferencia la mide PQ-95.
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
- `RiskManager.pre_trade` suma las órdenes pendientes a la exposición desde PQ-119. Las órdenes de
  mercado de Binance Demo se ejecutan dentro de `submit`, así que el runner tampoco deja
  pendientes entre ciclos.
- Con el kill-switch activado, el diario sigue registrando las decisiones de la estrategia
  (`FundingSettled`) sin órdenes. Para saber si se ejecutaron, crúzalas con `KillSwitchTripped`
  y `KillSwitchReset`.
- Si el runner estuvo parado varias horas, las otras estrategias deciden solo con la última vela:
  las intermedias no se recuperan. Para una estrategia sin memoria da igual; para una con memoria,
  vale lo dicho sobre la ventana `lookback`.
