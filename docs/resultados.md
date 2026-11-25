# Resultados

<!-- Generado con `uv run pq report public`: no lo edites a mano. -->

!!! warning "No es asesoramiento financiero"
    Proyecto universitario de investigación. Los resultados son del periodo de
    desarrollo y de **paper trading con dinero simulado**; rentabilidades pasadas no
    garantizan las futuras. Nada de esta página es una recomendación de inversión.

*Actualizado: 2026-11-25 17:14 UTC. Cada cifra sale de un artefacto del repositorio; nada se copia a mano.*

## ¿Funciona? El carry de funding en el periodo de desarrollo

Neto de comisiones VIP 0 y slippage, de enero de 2020 a junio de 2024. La prueba final, con datos nunca vistos (julio de 2024 a septiembre de 2026), va en la sección siguiente.

| hipótesis | retorno anual | siempre invertido | caída máx. | PBO | DSR | veredicto |
|---|---|---|---|---|---|---|
| H1 (BTCUSDT, ETHUSDT) | 6,5 % | 8,3 % | -0,43 % | 22,0 % | 1,000 | no pasa G4 |
| H2 (SOLUSDT, BNBUSDT, XRPUSDT) | 5,1 % | 2,3 % | -0,54 % | 2,0 % | 1,000 | pasa los cuatro gates |

**Gates de H2**

| condición | criterio | valor | resultado |
|---|---|---|---|
| G1 | Deflated Sharpe > 0,95 (N = 38) | 1,00 | ✓ pasa |
| G2 | PBO < 0,5 | 0,02 | ✓ pasa |
| G3 | t > 3,0 | 11,84 | ✓ pasa |
| G4 | Sharpe > B1 (0,61) y CAGR > 4 % | 5,58 | ✓ pasa |

## La prueba final: datos nunca vistos, una sola vez

Cada estrategia que pasa sus condiciones en el desarrollo se prueba una sola vez con julio de 2024 a septiembre de 2026, sin ajustar nada. Se exige más de un 4 % anual neto de costes.

| estrategia | configuración | retorno anual | Sharpe | caída máx. | veredicto |
|---|---|---|---|---|---|
| Carry H2 | k9-theta20 | 0,22 % | 1,73 | -0,1 % | descartada |
| Tendencia T1 | T1-L120-vol20 | 2,76 % | 0,29 | -14,5 % | descartada |

Las dos pasaron en el desarrollo y fallaron con datos nunca vistos, así que ninguna opera con dinero real. El paper trading del carry sigue como demostración del sistema completo.

## ¿Es significativo? Validación estadística

| prueba | resultado | H0 |
|---|---|---|
| HE1: H2 rinde más que estar siempre invertido | 2,61 % al año; p = 0,038 | se rechaza |
| HE2: H2 rinde más que una stablecoin al 4 % | 4,97 % al año; p = 0,130 | no se rechaza |
| HE3: las configuraciones difieren (Friedman) | p = 3.7e-26; W de Kendall = 0,010 | se rechaza |

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
| 2026-11-23 | 1.000,00 | 0,00 | 0,00 | 0 |
| 2026-11-24 | 1.000,00 | 0,00 | 0,00 | 0 |
| 2026-11-25 | 1.000,00 | 0,00 | 0,00 | 0 |

## Cuántas veces probamos

Ensayos registrados: **107** (carry 36, tendencia 20, modelo del funding 45 y otras 6). Ninguna ejecución se descarta: cada una queda en el [registro de ensayos](estrategias/registro-de-ensayos.md). El Deflated Sharpe de cada estrategia descuenta los ensayos de su familia (el N del gate G1).

## Las que se quedaron en el desarrollo

Se probaron con el mismo protocolo y no pasaron sus condiciones mínimas, así que su prueba final no se abrió. Cada ejecución cuenta en el N de su familia.

| estrategia | resultado | veredicto |
|---|---|---|
| Momentum transversal, largo/corto (X1-L28) | 2,9 % anual; t = 0,45 | descartada en el desarrollo |
| Momentum transversal, solo largo (X2-L28) | -14,0 % anual; t = 0,48 | descartada en el desarrollo |
| Filtro de miedo extremo sobre el momentum largo/corto (S1) | Sharpe 0,48 frente a 0,24 sin filtro; t = 0,89 | descartada en el desarrollo |
| Filtro de miedo extremo sobre el momentum solo largo (S2) | Sharpe 0,68 frente a 0,26 sin filtro; t = 1,25 | descartada en el desarrollo |
| Polymarket, comprar al favorito (fuera de deportes) | -0,59 % por apuesta; t = -2,07 | descartada en el desarrollo |
| Polymarket, comprar al favorito (deportes, control) | -0,20 % por apuesta; t = -0,43 | descartada en el desarrollo |
