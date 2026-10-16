# ADR-0006: NautilusTrader para backtest event-driven, paper y vivo

- **Estado:** Propuesta (se decide al iniciar el sprint de ejecución)
- **Fecha:** 2026-10-16

## Contexto y problema

Se necesita paridad entre backtest y ejecución real sin escribir un motor desde cero.

## Opciones consideradas

1. **NautilusTrader** (LGPL-3.0; adaptadores de Binance Spot/USDT-M y Polymarket).
2. Núcleo propio sobre CCXT (MIT).
3. Freqtrade (GPL-3.0), Hummingbot (Apache-2.0), LEAN (Apache-2.0).

## Decisión propuesta

NautilusTrader como dependencia sin modificar, con las estrategias escritas contra los puertos
propios para poder portarlas. A 2026-10-16 la última versión estable en PyPI es **1.231.0**; la v2
(núcleo en Rust) está en release candidate. Si la v2 no es estable al iniciar el sprint, se fija la
1.231 y se planifica la migración. vectorbt (Apache-2.0 + Commons Clause) solo para research interno.
