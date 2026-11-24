# Estrategia 1 · Carry de funding: decisión (ciclo PDCA 1)

!!! danger "Decisión final (2026-11-24): H2 descartada en el holdout"
    El holdout de H2 se abrió una sola vez ([holdout.md](holdout.md)). CAGR 0,22 % frente al 4 %
    exigido: **no pasa**. Estuvo con posición solo 38 de 822 días. Desde 2025, el funding nunca
    superó el umbral de entrada.

    - **H1 y H2 quedan descartadas.** La Estrategia 1 no tiene ninguna hipótesis aprobada.
    - **El paper trading sigue operando el carry H2 como demostración del pipeline** (PQ-50): datos
      → señal → riesgo → ejecución → monitoreo. No es una estrategia aprobada.
    - **El holdout del carry (2024-07-01 → 2026-09-30) ya está usado.** H3 y H4, que lo iban a
      usar, necesitan otro periodo de validación. Hay que enmendar sus pre-registros antes de
      evaluarlas.

- **Fecha:** 2026-10-30 · **Base:** [evaluación en desarrollo](evaluacion.md)

| | Decisión | Por qué |
|---|---|---|
| **H1** (BTC, ETH) | **Descartada** | Falla G4: la entrada por umbral (CAGR 6,5 %) rinde menos que estar siempre dentro (8,3 %). En 2022 se queda fuera y pierde el funding base. El pre-registro (§8) manda descartar si falla un gate. |
| **H2** (SOL, BNB, XRP) | **Pasa a holdout → descartada en el holdout (2026-11-24)** | Pasa G1 a G4. En altcoins el funding negativo y la basis castigan al carry siempre activo, y el umbral evita esos tramos. El margen económico es fino: CAGR 5,0 % frente al 4 % de una stablecoin. |

## Condiciones antes de abrir el holdout de H2

1. **PQ-17:** verificar desde la cuenta que los futuros USDⓈ-M están habilitados y cuáles son las
   comisiones reales. Si son más altas que las del escenario principal, se repite la evaluación con
   ellas (+9 ensayos en N, enmienda 1.11).
2. Abrir el holdout **una vez**, con `holdout.md` firmado (fecha, commit y autor).

## Qué se aprendió (Act del PDCA)

- El valor del timing depende del activo: en BTC y ETH el funding base de ~11 % anual es casi
  "gratis" y conviene no salir. En altcoins, filtrar los tramos negativos sí suma.
- Esto sugiere una **hipótesis nueva** para el Sprint 3: carry siempre activo en BTC y ETH. Como
  nace de mirar estos resultados, necesita su propio pre-registro y cuenta en N (protocolo de
  Arnott, Harvey y Markowitz).
- El Sharpe diario sobrestima el atractivo de un carry: la gestión del riesgo de contraparte
  (límite por exchange, kill-switch) pesa más que afinar la señal (épica PQ-7).
