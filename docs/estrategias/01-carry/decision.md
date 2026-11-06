# Estrategia 1 · Carry de funding: decisión (ciclo PDCA 1)

- **Fecha:** 2026-10-30 · **Base:** [evaluación en desarrollo](evaluacion.md)

| | Decisión | Por qué |
|---|---|---|
| **H1** (BTC, ETH) | **Descartada** | Falla G4: la entrada por umbral (CAGR 6,5 %) rinde menos que estar siempre dentro (8,3 %). En 2022 se queda fuera y pierde el funding base. El pre-registro (§8) manda descartar si falla un gate. |
| **H2** (SOL, BNB, XRP) | **Pasa a holdout (pendiente)** | Pasa G1 a G4. En altcoins el funding negativo y la basis castigan al carry siempre activo, y el umbral evita esos tramos. El margen económico es fino: CAGR 5,0 % frente al 4 % de una stablecoin. |

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
