# Estrategias

Una carpeta por estrategia, numerada en el orden de [ADR-0005](../adr/0005-orden-de-estrategias.md):
`01-carry/`, `02-tendencia/`, `03-polymarket/`.

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
| 1 · Carry de funding con entrada por umbral | [2026-10-23](01-carry/pre-registro.md) (PQ-18) | — | — | — |
