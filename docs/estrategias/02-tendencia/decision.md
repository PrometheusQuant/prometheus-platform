# Estrategia 2 · Tendencia: decisión (PQ-68)

**Fecha:** 2026-11-23. **Decisión: se descarta la Estrategia 2 tal como fue pre-registrada.**

| Hipótesis | Desarrollo ([evaluación](evaluacion.md)) | Holdout ([holdout](holdout.md)) | Decisión |
|---|---|---|---|
| T1, larga con vol targeting | Pasa G1–G4 (DSR 0,987 con N = 12; Sharpe 1,73) | **No pasa:** Sharpe 0,29 y CAGR 2,8 % | **Descartada** |
| T2, larga y corta en perpetuo | No pasa G1–G3 | No se evaluó | **Descartada** |

## Consecuencias

- **No va a paper trading en Demo:** PQ-82 queda sin objeto para esta estrategia.
- **El holdout de tendencia (2024-07-01 → 2026-09-30) ya está usado** y no se puede volver a usar
  para esta familia. Una variante (otra señal, otro universo, otro objetivo de volatilidad)
  necesita un **pre-registro nuevo** y un periodo de validación nuevo. Por ejemplo, datos
  posteriores al 2026-09-30, cuando haya suficientes.
- **Lo que deja:**
  - el código de backtest y la evaluación, reutilizables;
  - la evidencia de que en este periodo la tendencia sobre BTC y ETH redujo el riesgo pero no
    ganó retorno.
- **Para la próxima:** las correcciones de método de PQ-122 (selección fuera de muestra de verdad,
  N global, Newey-West) se aplican a los pre-registros futuros.
