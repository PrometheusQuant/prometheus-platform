# Estrategias

Una carpeta por estrategia, numerada en el orden de [ADR-0005](../adr/0005-orden-de-estrategias.md):
`01-carry/`, `02-tendencia/`, `03-momentum-transversal/`, `04-polymarket/` y `05-sentimiento/`
(el spike de datos de Polymarket, PQ-78, eligió `04-` porque momentum ya ocupaba `03-`).

Cada carpeta sigue el ciclo PDCA y los gates de CRISP-ML(Q):

| Archivo | Cuándo se escribe | Qué contiene |
|---|---|---|
| `pre-registro.md` | **Antes** de cualquier backtest | Hipótesis económica, universo, métricas, benchmarks, costes y fechas del holdout |
| `evaluacion.md` | Tras el backtest con validación purgada | Resultados, número de ensayos N, Deflated Sharpe, PBO, sensibilidad |
| `holdout.md` | Al abrir el holdout (una sola vez) | Resultado fuera de muestra, fecha, commit y autor |
| `decision.md` | Al cerrar el ciclo | Pasa a paper trading, se itera o se descarta, y por qué |

El commit del `pre-registro.md` es la evidencia fechada de que la hipótesis no se ajustó a los resultados.

## Estado

| Estrategia | Pre-registro | Evaluación | Holdout | Decisión |
|---|---|---|---|---|
| 1 · Carry de funding con entrada por umbral | [2026-10-23](01-carry/pre-registro.md) (PQ-18), enmiendas 1 y 2 | [2026-10-30](01-carry/evaluacion.md), reejecución 2026-11-24 | [2026-11-24](01-carry/holdout.md): **H2 no pasa** (CAGR 0,22 %), PQ-50 | [H1 y H2 descartadas; el paper sigue como demostración](01-carry/decision.md) |
| 2 · Tendencia con volatility targeting (BTC/ETH) | [2026-11-06](02-tendencia/pre-registro.md) (PQ-64) | [2026-11-23](02-tendencia/evaluacion.md) (PQ-68): T1 pasa los gates, T2 descartada | [2026-11-23](02-tendencia/holdout.md): **no pasa** (Sharpe 0,29) | [Descartada](02-tendencia/decision.md) |
| 4 · Sesgo favorito-longshot en Polymarket | [2026-11-24](04-polymarket/pre-registro.md) (PQ-87) | Pendiente (PQ-92 ingesta, PQ-93) | Pendiente | — |
| 5 · Overlay de sentimiento (Fear & Greed) sobre el momentum | [2026-11-24](05-sentimiento/pre-registro.md) (PQ-103) | Pendiente: después del momentum (PQ-114) y de la ingesta del índice | Pendiente | — |
