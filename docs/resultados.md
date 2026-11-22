# Resultados

<!-- Generado con `uv run pq report public`: no lo edites a mano. -->

!!! warning "No es asesoramiento financiero"
    Proyecto universitario de investigación. Los resultados son del periodo de
    desarrollo y de **paper trading con dinero simulado**; rentabilidades pasadas no
    garantizan las futuras. Nada de esta página es una recomendación de inversión.

*Actualizado: 2026-11-22 01:00 UTC. Cada cifra sale de un artefacto del repositorio; nada se copia a mano.*

## ¿Funciona? El carry de funding en el periodo de desarrollo

Neto de comisiones VIP 0 y slippage, de enero de 2020 a junio de 2024. El holdout (julio de 2024 en adelante) sigue cerrado: se abre una sola vez.

| hipótesis | retorno anual | siempre invertido | caída máx. | PBO | DSR | veredicto |
|---|---|---|---|---|---|---|
| H1 (BTCUSDT, ETHUSDT) | 6,5 % | 8,3 % | -0,51 % | 14,9 % | 1,000 | no pasa G4 |
| H2 (SOLUSDT, BNBUSDT, XRPUSDT) | 5,0 % | 2,5 % | -0,39 % | 4,5 % | 1,000 | pasa los cuatro gates |

**Gates de H2**

| gate | criterio | valor | pasa |
|---|---|---|---|
| G1 | Deflated Sharpe > 0.95 (N = 20) | 1,00 | sí |
| G2 | PBO < 0.5 | 0,04 | sí |
| G3 | t > 3.0 | 11,82 | sí |
| G4 | Sharpe > B1 (0.66) y CAGR > 4% | 5,57 | sí |

## ¿Es significativo? Validación estadística

| prueba | resultado | H0 |
|---|---|---|
| HE1: H2 rinde más que estar siempre invertido | 2,36 % al año; p = 0,044 | se rechaza |
| HE2: H2 rinde más que una stablecoin al 4 % | 4,91 % al año; p = 0,146 | no se rechaza |
| HE3: las configuraciones difieren (Friedman) | p = 1.5e-35; W de Kendall = 0,013 | se rechaza |

## ¿Qué riesgo hay? Simulación

- Retorno medio simulado del carry H2: **4,41 %** (mediana 3,44 %).
- Años por debajo del 4 %: **55 %**; años con pérdida: **16 %**.
- Con un 2 % anual de probabilidad de quiebra del exchange, el retorno medio cae a **2,15 %**. Por encima de **0,40 %** anual conviene la stablecoin.

## ¿Cómo va en vivo? Paper trading del carry H2

Dinero simulado sobre precios reales de Binance, con kill-switch y alertas. Solo agregados: sin claves ni identificadores de cuenta.

| medida | valor |
|---|---|
| Desde | 2026-11-13 |
| Capital inicial (simulado) | 1.000,00 USD |
| Capital actual (simulado) | 1.000,00 USD |
| Variación | 0,000 % |
| Caída máxima | 0,000 % |
| Funding cobrado | 0,0000 USD |
| Comisiones y slippage | 0,0000 USD |
| Órdenes ejecutadas | 0 |
| Activaciones del kill-switch | 0 |

Todavía no hubo operaciones: la regla de entrada del carry H2 no dio señal en este periodo, así que el capital sigue en efectivo.

**Últimos 14 días con actividad**

| día (UTC) | equity (USD) | funding (USD) | costes (USD) | órdenes |
|---|---|---|---|---|
| 2026-11-13 | 1.000,00 | 0,00 | 0,00 | 0 |
| 2026-11-20 | 1.000,00 | 0,00 | 0,00 | 0 |
| 2026-11-21 | 1.000,00 | 0,00 | 0,00 | 0 |
| 2026-11-22 | 1.000,00 | 0,00 | 0,00 | 0 |

## Cuántas veces probamos

Ensayos registrados: **63** (carry 18, modelo del funding 45). Ninguna ejecución se descarta: cada una queda en el [registro de ensayos](estrategias/registro-de-ensayos.md). El Deflated Sharpe de cada estrategia descuenta los ensayos de su familia (el N del gate G1).

La Estrategia 2 (tendencia con volatility targeting) está pre-registrada; su evaluación está pendiente.
