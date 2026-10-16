# ADR-0005: Orden de implementación de estrategias

- **Estado:** Aceptada
- **Fecha:** 2026-10-16

## Contexto y problema

Capital inicial < 1.000 USD, operando desde Bolivia con Binance como vía principal de depósito
y retiro. Se busca diversificar riesgo y fuentes de ingreso.

## Decisión

1. **Carry de funding en perpetuos**, entrando solo cuando el funding supera un umbral. Mecanismo:
   demanda minorista de apalancamiento (Schmeling, Schrimpf y Todorov, BIS WP 1087). La mayor parte
   del retorno documentado viene del *timing* de entrada, no del cupón.
2. **Tendencia en BTC/ETH con volatility targeting.**
3. **Mercados de predicción (Polymarket)** como proveedor de liquidez: única fuente de riesgo no
   correlacionada con el ciclo cripto.
4. **Capas de ML y sentimiento** (meta-labeling, CryptoBERT como feature de régimen).

Descartados: pairs trading por cointegración (evidencia neta negativa en cripto), provisión de
liquidez en Uniswap v3, martingala, copy trading. FinBERT se sustituye por CryptoBERT.

## Consecuencias

- Con el funding base actual, el carry sobre < 1.000 USD rinde del orden de decenas de USD al año:
  el valor inicial está en el proceso validado, que permite escalar capital después.
- Pendiente de verificar en el Sprint 0: habilitación de futuros USDⓈ-M de Binance para Bolivia,
  comisiones oficiales y elegibilidad en Polymarket.

Fuente: [`docs/investigacion/`](../investigacion/).
