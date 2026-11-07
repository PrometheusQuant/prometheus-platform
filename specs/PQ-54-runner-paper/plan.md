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
1. heartbeat;
2. `observe()` del kill-switch y cierre si está activado;
3. precios y valoración (`PortfolioValued`);
4. `monitor` y `enforce`;
5. por cada símbolo con una liquidación nueva: `FundingSettled`, decisión, órdenes (riesgo, bróker y
   diario).

**Reconstrucción:** el bróker simulado se rehace con `replay` del diario. Las liquidaciones
procesadas salen de los `FundingSettled`.

| Riesgo | Mitigación |
|---|---|
| Ejecutar a precio actual difiere del backtest (open de t+1 h) | La paridad se exige en **decisiones**. La diferencia de precio es el slippage real que mide PQ-95 |
| Liquidación duplicada tras un reinicio | Se cuenta una vez por `(símbolo, funding_time)`, con una prueba de reinicio |
| API caída | Ciclo sin decisión y alerta por heartbeat (PQ-55) |
