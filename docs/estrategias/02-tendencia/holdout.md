# Estrategia 2 · Tendencia: holdout (PQ-68)

- **Apertura:** 2026-11-23, **una sola vez**, a pedido del titular. Comando:
  `pq research trend-holdout --confirmo-un-solo-uso`, carril `boris`.
- **Registro:** la apertura quedó en `docs/estrategias/ensayos/boris.jsonl` (fila `holdout`) antes
  de calcular. No suma a N, porque la configuración ya estaba elegida.
- **Configuración:** **T1-L120-vol20**, la elegida en desarrollo ([evaluación](evaluacion.md)),
  sin re-ajustes.
- **Costes:** escenario principal, igual que en los gates.
- **Periodo:** 2024-07-01 → 2026-09-30, 822 días.
- **Artefactos:** `data/research/trend/holdout/summary.json` y `daily_returns.parquet`.
- **Figura:** [curva de capital](img/holdout-curva.png).

## Resultado frente al criterio de éxito (§8, fijado antes)

| Criterio | Umbral | T1-L120-vol20 | ¿Cumple? |
|---|---|---|---|
| H1 Sharpe neto | > 0,5 | **0,29** | ❌ |
| H2 CAGR neto | > 4 % | **2,8 %** | ❌ |
| H3 Drawdown máximo | < 30 % | −14,6 % | ✅ |
| | | **Veredicto** | **No pasa** |

| Métrica | T1-L120-vol20 | B1 comprar y mantener |
|---|---|---|
| Sharpe neto | 0,29 (t = 0,43) | 0,30 |
| CAGR neto | 2,8 % | 2,3 % |
| Drawdown máximo | −14,6 % | −58,5 % |
| Calmar | 0,19 | 0,04 |

Sensibilidad con costes de maker y BNB: Sharpe 0,31. **No cambia la conclusión.**

**Por año:**

| Año | T1: retorno | T1: Sharpe | B1: retorno |
|---|---|---|---|
| 2024 (jul–dic) | +6,9 % | 1,37 | +22,4 % |
| 2025 | −0,7 % | 0,04 | −7,4 % |
| 2026 (ene–sep) | +0,1 % | 0,07 | −7,1 % |

## Lectura

- **La estrategia conservó lo que prometía en riesgo.** El drawdown fue de −14,6 %, frente al
  −58,5 % del comprar y mantener. Pero no dio retorno: desde 2025 quedó plana. Su Sharpe
  (0,29) es indistinguible de cero (t = 0,43) y no supera el yield de una stablecoin (4 %).
- **Las fragilidades registradas en la evaluación anticipaban este resultado:**
  - selección dentro de la muestra;
  - Deflated Sharpe de 0,948 con el N global;
  - dependencia de 2020.

  El holdout cumplió su función: separar un resultado de desarrollo frágil de uno robusto.
- **Es un resultado negativo válido.** El protocolo (pre-registro, N, revisión adversarial,
  holdout de un solo uso) evitó llevar a paper trading una estrategia que en desarrollo parecía
  buena.

## Decisión

Ver [decision.md](decision.md): **T1 se descarta** (§8). T2 ya estaba descartada en desarrollo.
