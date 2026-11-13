# Especificación: motor de backtest de tendencia con volatility targeting

- **Ticket:** PQ-67 (5 puntos) · **Rama:** `feature/PQ-67-motor-tendencia` · **Fecha:** 2026-11-13
- **Contrato:** [pre-registro de la Estrategia 2](../../docs/estrategias/02-tendencia/pre-registro.md)
  (PQ-64), §3–§8. Esta historia **no ejecuta la evaluación**: eso es PQ-68.

## Escenarios

1. **Dado** un historial de velas de 1 h de BTC y ETH, **cuando** se simula una configuración
   (L, σ*) de T1, **entonces**:
   - se decide cada día a las 00:00 UTC con el `close` de la última vela del día;
   - la señal es `signo(cierre_t / cierre_{t-L} - 1)`;
   - la volatilidad es la de los 30 retornos diarios hasta *t*, anualizada con √365, **solo con el
     pasado**;
   - el peso es `w = señal · min(1, σ*/σ̂)`, nunca negativo en T1 y con |w| ≤ 1;
   - la posición solo se ajusta si `|w - w_actual| > 0,10`;
   - la orden se ejecuta al `open` de la vela que abre en *t* + 1 h, o la siguiente disponible;
   - se cobran la comisión y el slippage del `CostModel` sobre el nocional negociado.
2. **Dado** T2, **entonces** opera en el perpetuo, admite cortos y paga o cobra el funding de las
   liquidaciones con la posición abierta antes de *s*, al `close` del perpetuo de la vela que cierra
   en *s*.
3. **Dado** el periodo de desarrollo, **entonces** no decide ni cobra eventos `≥ HOLDOUT_START`
   (corrección de KE-014). La última valoración es la de `HOLDOUT_START`, con precios del desarrollo.
4. **Dado** cualquier ejecución vía `run_and_register`, **entonces** queda su fila en el registro de
   ensayos, familia `tendencia`, y suma a N.
5. **Benchmarks:** B1 (comprar y mantener al 50/50 en spot) y B3 (la misma señal sin volatility
   targeting) con el mismo motor, los mismos costes y la misma valoración.

## Requisitos

- **FR-001** El motor vive en `research/trend.py` y reutiliza `SymbolResult`, `CostModel`,
  `portfolio_returns`, `performance` y `HOLDOUT_START`, con las convenciones del carry.
- **FR-002** Una prueba demuestra que el peso en *t* no cambia si se alteran precios posteriores a *t*.
- **FR-003** Una prueba demuestra que la ejecución usa el `open` de la vela de *t* + 1 h, y no el de
  la de *t*. Es la latencia que el backtest del carry no aplica (KE-016).
- **FR-004** **Ninguna ejecución sobre datos reales en este ticket.** Las pruebas usan datos
  sintéticos. La primera ejecución real es la evaluación de PQ-68, y se registra.
