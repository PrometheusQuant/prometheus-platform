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
- Si falla con `CERTIFICATE_VERIFY_FAILED`, la red está interceptando el TLS: ver
  [KE-015](errores-conocidos.md).
- El capital solo se usa la primera vez. Después manda el estado guardado del bróker.

## Qué hace cada ciclo

1. Comprueba el kill-switch. Si está activado, cierra todas las posiciones y no abre nada.
2. Pide precios (spot y mark price del perpetuo). Si falta alguno, el ciclo no decide nada y el
   heartbeat queda en `ok: false`.
3. Valora la cartera y aplica los límites de riesgo. Las violaciones graves activan el kill-switch.
4. Por cada liquidación de funding nueva: cobra o paga el funding y decide.
   - Entra, sale o rebalancea con las dos patas.
   - Las dos patas se aprueban antes de enviar ninguna: si el riesgo rechaza una, no se envía
     ninguna. Así nunca queda media cobertura.
5. Registra la valoración (cada 15 min o cuando hubo movimiento) y escribe el heartbeat.

## Archivos (en `data/paper/`)

| Archivo | Qué es |
|---|---|
| `diario.jsonl` | Diario append-only: `RunnerStarted`, `FundingSettled` (con la decisión y `S_k`), `SignalGenerated`, `OrderSubmitted`, `OrderFilled`, `PortfolioValued`, `RiskLimitBreached` |
| `broker-simulado.json` | Efectivo, posiciones y última liquidación aplicada del bróker simulado |
| `heartbeat.json` | Último ciclo: hora, `ok`, detalle del error, bróker y kill-switch |
| `KILL_SWITCH` | Existe solo si el kill-switch está activado ([runbook](kill-switch.md)) |

Ver el estado:

```bash
cat data/paper/heartbeat.json
tail -n 5 data/paper/diario.jsonl
uv run pq paper status
```

## Reiniciar

Detener (Ctrl+C) y volver a arrancar es seguro.

- Las liquidaciones ya procesadas salen del diario. El bróker aplica cada una una sola vez.
- Tras una caída, el runner se pone al día: cobra las liquidaciones perdidas y decide con todas
  ellas, en orden. Envía solo las órdenes del estado final, no las intermedias.
- **Arranque en frío** (sin diario): el estado de la histéresis se reconstruye con las últimas 90
  liquidaciones (30 días), y el runner se coloca donde estaría el backtest.

Para empezar de cero, mueve la carpeta y no la borres: es el historial del paper trading.

```bash
mv data/paper data/paper-$(date +%Y%m%d)
```

## Diferencias con el backtest

| Aspecto | Backtest | Paper (bróker simulado) |
|---|---|---|
| Decisión | `carry_rules.decide` | La misma función: paridad verificada en un test |
| Precio de ejecución | Open de la vela siguiente | Precio actual ± slippage del `CostModel` |
| Tamaño por pata | Capital / 2 (1x) | Equity / n símbolos / 2, menos un margen del 2 % para no superar el límite de 1x |
| Funding perdido en una caída | No aplica | Se cobra al mark price del momento en que vuelve |

## Limitaciones conocidas

- Ejecutar al precio actual no es el precio real de Binance Demo: esa diferencia la mide PQ-95.
- Tras un reinicio, la antigüedad de un desbalance de patas empieza de cero, así que la gracia
  (`PQ_RISK_IMBALANCE_GRACE_SECONDS`) se cuenta de nuevo.
- `RiskManager.pre_trade` usa las órdenes pendientes para decidir si una orden reduce, pero no
  las suma a la exposición. Con el bróker simulado no hay pendientes, porque se ejecuta al
  instante. Hay que cubrirlo antes de Binance Demo (PQ-52).
