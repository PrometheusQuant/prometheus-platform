# Plan de implementación: runner de paper trading

- **Ticket:** PQ-54 · **Fecha:** 2026-11-06 · **Spec:** [spec.md](spec.md)

| Pieza | Capa | Archivo |
|---|---|---|
| Regla del carry (pura) | `domain` | `domain/carry_rules.py` (la usan el backtest y la estrategia) |
| Eventos nuevos | `domain` | `RunnerStarted`, `FundingSettled`, `PortfolioValued` en `domain/events.py` |
| Puertos | `domain` | `LiveMarket`, `Broker` en `domain/ports.py` |
| Estrategia | `strategies` | `strategies/carry.py` |
| Bróker simulado | `adapters` | `adapters/simulated_broker.py` (usa el `CostModel` de research) |
| Mercado en vivo | `adapters` | `adapters/binance_public_market.py` (REST público, sin claves) |
| Runner y CLI | `api` | `api/paper/runner.py` (raíz de composición) y `pq paper run` |

**Ciclo (`tick`):**
1. `observe()` del kill-switch y cierre si está activado;
2. precios y valoración;
3. `monitor` y `enforce`;
4. por símbolo: liquidaciones nuevas (`FundingSettled` con la decisión y el estado deseado) y
   reconciliación con el estado deseado desde *t* + 1 h (riesgo, bróker y diario);
5. `PortfolioValued` y heartbeat.

**Reconstrucción:** posiciones y efectivo, del estado del bróker simulado (JSON atómico con
`fsync`). Liquidaciones procesadas, estado deseado y rebalanceos ya enviados, del diario.
Cambio respecto al primer plan («el bróker se rehace con el diario»): un bróker real (PQ-52) es su
propia fuente de verdad, así que el simulado se comporta igual.

| Riesgo | Mitigación |
|---|---|
| Ejecutar a precio actual difiere del backtest (open de t+1 h) | La paridad se exige en **decisiones**. La diferencia de precio es el slippage real que mide PQ-95 |
| Liquidación duplicada tras un reinicio | Se cuenta una vez por `(símbolo, funding_time)`, con una prueba de reinicio |
| API caída | Ciclo sin decisión y alerta por heartbeat (PQ-55) |
