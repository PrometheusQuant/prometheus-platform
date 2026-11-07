# Especificación: runner de paper trading del carry H2

- **Ticket:** PQ-54 (8 puntos) · **Rama:** `feature/PQ-54-runner-paper` · **Fecha:** 2026-11-06 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** historia PQ-54; comentario del 2026-11-06, que pide un bróker simulado para el MVP
  sin esperar las claves de PQ-17; fase 5 de CRISP-ML(Q) (TRL 5: paper trading con datos en vivo)

## Escenarios

### Historia 1: H2 opera sola con datos en vivo (P1)

1. **Dado** el runner en marcha con el bróker simulado, **cuando** Binance publica una
   liquidación de funding nueva de SOL, BNB o XRP, **entonces** el runner:
   - cobra o paga el funding de la posición abierta;
   - calcula `S_k` con las últimas k tasas;
   - decide con **la misma función que el backtest** (`domain/carry_rules.decide`);
   - si hay que entrar, salir o rebalancear, envía las dos patas.
2. **Dada** cada orden, **entonces** pasa por `RiskManager.pre_trade` antes de llegar al bróker.
   Si se rechaza, queda un `RiskLimitBreached` y la orden no se envía.
3. **Dado** cualquier ciclo, **entonces**:
   - el runner llama a `KillSwitch.observe()`;
   - si el kill-switch está activado, cierra todo y no abre nada;
   - evalúa `monitor` y aplica `enforce`.

### Historia 2: el estado sobrevive a un reinicio (P1)

1. **Dado** un reinicio, **cuando** el runner arranca, **entonces** reconstruye desde el diario:
   - las posiciones;
   - el efectivo;
   - las liquidaciones ya procesadas.

   No cobra dos veces la misma liquidación ni repite órdenes.
2. **Dado** el diario, **entonces** contiene `RunnerStarted` (bróker y parámetros),
   `SignalGenerated`, `OrderSubmitted`, `OrderFilled`, `FundingSettled` y `PortfolioValued`.
   Con eso, el dashboard (PQ-55) y el informe (PQ-85) reconstruyen el historial.

### Historia 3: paridad con el backtest (P1)

1. **Dada** una secuencia histórica de liquidaciones, **cuando** se reproduce en el runner con el
   bróker simulado, **entonces** las decisiones (entradas, salidas y rebalanceos) coinciden con
   las del backtest en las mismas liquidaciones.

### Casos límite

- La API pública no responde: se registra, no se decide nada en ese ciclo y el heartbeat avisa.
- Una liquidación con datos parciales (falta un precio): no se decide con datos incompletos.
- El historial con el bróker simulado se rotula como tal, para no confundirlo con Binance Demo.

## Requisitos

- **FR-001** `domain/carry_rules.py` es la única definición de la regla. El backtest se refactoriza
  para usarla, con resultados idénticos (verificado: diferencia 0,0 en tres configuraciones y en B1).
- **FR-002** `strategies/carry.py` traduce las tasas recientes a una acción y a los pesos objetivo
  por pata.
- **FR-003** Puertos nuevos en `domain/ports.py`: `LiveMarket` (precios y funding recientes) y
  `Broker` (órdenes, posiciones y efectivo). Adaptadores: `BinancePublicMarket` (sin claves) y
  `SimulatedBroker` (fills al precio actual con comisiones y slippage del `CostModel`).
- **FR-004** `pq paper run [--once] [--interval S]`; heartbeat en `data/paper/heartbeat`.
- **FR-005** El runner no se ejecuta en `PQ_ENVIRONMENT=live` (eso es otra historia).
