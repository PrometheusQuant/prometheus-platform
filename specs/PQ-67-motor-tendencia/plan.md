# Plan: motor de tendencia (PQ-67)

| Pieza | Archivo |
|---|---|
| Configuración (L, σ*, T1 o T2, B1, B3) y nombre del ensayo | `research/trend.py` (`TrendConfig`) |
| Peso objetivo, función pura | `target_weight(closes, config)`, solo con cierres hasta *t* |
| Simulación por símbolo, hora a hora | `simulate_trend(...)`, que devuelve `TrendResult(SymbolResult)` |
| Cartera de BTC y ETH al 50/50 | `run_config(...)`, con `portfolio_returns` del carry |
| Registro del ensayo | `run_and_register(...)`, en la familia `tendencia` del registro compartido |

**Bucle horario** (mismo esqueleto que `simulate_symbol` del carry):

1. ejecutar la orden pendiente si la vela abre en *t* + 1 h o después;
2. marcar la posición: el spot por valor y el perpetuo con el P&L al efectivo;
3. T2: funding de la liquidación que cierra en esta vela;
4. a las 00:00: cierre diario, valoración y decisión, solo si *t* < `HOLDOUT_START`.

| Riesgo | Mitigación |
|---|---|
| Look-ahead en σ̂ o en la señal | `target_weight` recibe solo los cierres hasta *t*; prueba que altera el futuro |
| Repetir KE-016 (ejecutar en *t*) | La orden espera la vela que abre en *t* + 1 h; prueba con un salto de precio |
| Contar ensayos de más o de menos | El motor no registra; solo lo hace `run_and_register`, que PQ-68 usará |
