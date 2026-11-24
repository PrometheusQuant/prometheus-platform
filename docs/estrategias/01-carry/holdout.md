# Estrategia 1 · Carry H2: holdout (PQ-50)

- **Apertura:** 2026-11-24, **una sola vez**, a pedido del titular (David Quintela), con el commit
  `bebb408`. Comando: `pq research carry-holdout --confirmo-un-solo-uso`, carril `david`.
- **Registro:** la apertura quedó en `docs/estrategias/ensayos/david.jsonl` (fila `holdout`) antes
  de calcular. No suma a N, porque la configuración ya estaba elegida.
- **Configuración:** H2 (SOLUSDT, BNBUSDT, XRPUSDT), **k9-theta20**, la elegida en desarrollo tras
  la reejecución de la enmienda 3 ([evaluación](evaluacion.md)), sin re-ajustes.
- **Costes:** escenario principal, que PQ-17 verificó igual a las comisiones reales.
- **Periodo:** 2024-07-01 → 2026-09-30, 822 días. La estrategia corre de forma continua y se
  evalúan sus días del holdout. Entró sin posición: la última salida fue en abril de 2024.
- **Artefactos:** `data/research/carry/holdout/summary.json` y `daily_returns.parquet`.
- **Figura:** [curva de capital](img/holdout-curva.png).

## Resultado frente al criterio de éxito (§8, fijado antes)

| Criterio | Umbral | H2 k9-theta20 | ¿Cumple? |
|---|---|---|---|
| H1 Sharpe neto | > 0,5 | 1,73 | ✅ |
| H2 CAGR neto | > 4 % | **0,22 %** | ❌ |
| H3 Drawdown máximo | < 15 % | −0,11 % | ✅ |
| | | **Veredicto** | **No pasa** |

| Métrica | H2 k9-theta20 | B1 siempre activo |
|---|---|---|
| CAGR neto | 0,22 % | 0,59 % |
| Sharpe neto | 1,73 (t = 2,60) | 2,11 |
| Drawdown máximo | −0,11 % | −0,80 % |
| Días con posición | 38 de 822 | todos |

Sensibilidad con costes de maker y BNB: Sharpe 2,80. El CAGR sigue muy por debajo del 4 %.

**Por año:**

| Año | H2: retorno | H2: días con posición | B1: retorno |
|---|---|---|---|
| 2024 (jul–dic) | +0,49 % | 38 | +1,51 % |
| 2025 | 0,00 % | 0 | −0,06 % |
| 2026 (ene–sep) | 0,00 % | 0 | −0,12 % |

## Lectura

- **La regla hizo lo que dice:** solo entra cuando el funding medio supera el umbral (θ = 20 %
  anual). Con el funding comprimido de 2025 y 2026, eso no pasó nunca. Evitó pérdidas (peor caída
  −0,11 %), pero **no hubo prima que cobrar**.
- **Aun estando siempre dentro (B1) se ganó 0,59 % anual.** No es la señal la que falla: en este
  periodo el carry de funding en estas altcoins no paga lo suficiente para superar una stablecoin
  (4 %). El Sharpe alto (1,73) es engañoso, porque mide la estabilidad de unos retornos ínfimos.
- **La revisión adversarial de la reejecución lo anticipaba:** el resultado de desarrollo dependía
  de 2021, y entre 2022 y 2024 la estrategia ganaba ≈ 1,2 % anual.
- **Las garantías del cálculo** (sin liquidaciones fuera del periodo, costes en ambas patas,
  ejecución en *t* + 1 h) son las verificadas por la revisión adversarial de la reejecución y por
  las pruebas del comando. Un resultado negativo no necesita revisarse para descartar un falso
  positivo.

## Decisión

Ver [decision.md](decision.md): **H2 se descarta** (§8, falla el CAGR).
