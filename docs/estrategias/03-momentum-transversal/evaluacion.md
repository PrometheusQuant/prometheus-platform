# Estrategia 3 · Momentum transversal: evaluación en desarrollo (PQ-114)

- **Fecha:** 2026-11-25.
- **Ejecución:** una sola. PQ-17 verificó que las comisiones reales son iguales al escenario
  principal, así que no hizo falta enmienda de costes. Antes de ejecutar se añadió la
  [aclaración 1](pre-registro.md#aclaracion-1-2026-11-25-antes-del-primer-backtest-no-suma-a-n) del
  pre-registro (cómo se implementan reglas que el texto no fijaba). No suma a N.
- **Comando:** `pq research momentum`, carril `boris`.
- **Registro de ensayos:** las 6 configuraciones se registraron antes de evaluar
  (`docs/estrategias/ensayos/boris.jsonl`).
- **Universo:** los 15 perpetuos de [`universo.json`](universo.json), elegidos por volumen de
  diciembre de 2020 (PQ-114, parte 1). Ninguno deja de cotizar en el desarrollo.
- **Periodo:** desarrollo, del 2021-02-01 al 2024-06-30 (1246 días). **El holdout no se leyó:** las
  velas y el funding se recortan antes del 2024-07-01 al cargarlos.
- **Artefactos:** `data/research/momentum/X1|X2/summary.json` y `daily_returns.parquet`.
- **Figuras:** [X1](img/x1-curvas.png) y [X2](img/x2-curvas.png).
- **Agentes:** Claude A hizo el pre-registro y el universo; Claude B, el motor, la evaluación y
  la ejecución, porque Claude A estuvo fuera hasta el 30-nov. Hubo una revisión adversarial con
  contexto fresco antes de ejecutar (más abajo).

## Resultado de los gates (escenario de costes principal)

| Gate | Criterio | X1 (largo/corto, elegida L = 28) | X2 (solo largo, elegida L = 28) |
|---|---|---|---|
| G1 | Deflated Sharpe > 0,95 con N de la familia = 18 | 0,028 ❌ | 0,030 ❌ |
| G2 | PBO < 0,5 | **0,003** ✅ | 0,663 ❌ |
| G3 | t de la media diaria > 3 | 0,45 ❌ | 0,48 ❌ |
| G4 | X1: CAGR > 4 %. X2: Sharpe > B1 (0,30) y CAGR > 4 % | 2,9 % ❌ | 0,26 y −14,0 % ❌ |
| | **Veredicto** | **No pasa: descartada** | **No pasa: descartada** |

| Métrica de la elegida | X1-L28 | X2-L28 | B1, universo a partes iguales |
|---|---|---|---|
| Sharpe neto | 0,24 | 0,26 | 0,30 |
| CAGR neto | 2,9 % | −14,0 % | −8,4 % |
| Drawdown máximo | −46,4 % | −92,9 % | −85,8 % |
| Peor mes | −8,8 % | −35,0 % | |
| Volatilidad realizada | 24,5 % | 85,6 % | |
| Rotación anual (sobre el capital inicial) | 35,1 | 26,4 | |

**Sharpe medio de prueba en la CPCV**, de donde sale la elegida:

| | L = 7 | L = 14 | L = 28 |
|---|---|---|---|
| X1 | −0,67 | −0,34 | **0,27** |
| X2 | −0,01 | 0,16 | **0,24** |

**De dónde sale el resultado** (fracción del capital inicial, 3,4 años):

| | Precio | Funding | Costes | Total |
|---|---|---|---|---|
| X1-L28 | +22,6 % | +1,9 % | −14,1 % | +10,4 % |
| X2-L28 | +38,1 % | **−67,8 %** | −10,6 % | −40,3 % |

**Sensibilidad (solo se informa):** el Sharpe con costes de maker y sin slippage es 0,40 en X1 y
0,30 en X2. Ni siquiera sin slippage se acerca a los gates.

**Correlación diaria con las otras estrategias:**

| | Carry H2 | Tendencia T1 | Tendencia T2 |
|---|---|---|---|
| X1 | 0,02 | 0,03 | 0,05 |
| X2 | 0,12 | 0,62 | 0,21 |

**Datos:** un solo lunes con menos de 15 símbolos elegibles, el 2022-02-28, por el hueco de Data
Vision de la aclaración 1 (punto 2). No hubo deslistados en el desarrollo.

**N global de la plataforma:** 99 ensayos. Son 36 de carry, 45 del modelo de funding y 18 de
la familia `tendencia` (12 de la tendencia y 6 de este momentum), según
`pq research registro resumen` del 2026-11-25.

## Lectura

- **X1 no se distingue del azar.** Gana un 2,9 % anual con un t de 0,45. Su único punto a favor es
  que su retorno casi no se mueve con el carry ni con la tendencia (correlación ≤ 0,05), algo que
  vale solo si hay retorno.
  - El PBO bajo (0,003) dice que la elegida en muestra también fue la mejor fuera de muestra. Pero
    elegir bien entre tres configuraciones mediocres no salva el resultado.
- **Los costes se comen la mitad del precio.** X1 rota 35 veces el capital al año: los costes
  (−14,1 %) se llevan más de la mitad de lo que gana con el precio (+22,6 %).
- **X2 es casi una apuesta larga a las altcoins.** Correlación 0,62 con la tendencia, caída máxima
  del 93 %, y pagó en funding el 68 % del capital inicial, porque ir largo en altcoins en 2021 era
  muy caro. Pierde frente a B1 y frente al 4 %.
- **Lo que confirma el mecanismo del §2:** las ventanas cortas (L = 7 y 14) pierden en la CPCV. Es lo
  esperable si el momentum de corto plazo en altcoins se revierte, y el pre-registro lo anticipaba
  («crashes» del momentum y coste de rotar).

## Revisión adversarial antes de ejecutar (doubt-driven-development)

Un agente con contexto fresco revisó el motor contra el pre-registro sin tocar datos reales. Sus
comprobaciones:

- **Sin look-ahead:** un shock de precios desde el lunes 00:00 no cambia la decisión de ese lunes.
- **Ejecución y funding:** la ejecución es al `open` de la vela de las 01:00, y el funding solo se
  aplica a posiciones abiertas antes de cada liquidación.
- **Contabilidad:** cierra al 1e-14.

Lo que se corrigió antes de la ejecución:

1. Un hueco temporal de datos ya no se trata como deslistado.
2. El funding se liquida aunque falte la vela de esa hora.
3. El peor mes ya no se desplaza un día.
4. Se añadió una protección para equity ≤ 0.
5. Se informan los lunes con menos símbolos elegibles.
6. La aclaración 1 del pre-registro deja escritas las decisiones de implementación.
7. Los ensayos se registraron en el carril del ticket (`boris`) y no en el que viene por defecto.

Lo que quedó como decisión documentada, no como error:

- la señal tras un hueco cubre unos días más que *L*;
- la rotación se mide sobre el capital inicial, igual que en la tendencia;
- V[SR] del Deflated Sharpe mezcla las 18 configuraciones de la familia, igual que en la tendencia.

## Decisión

**Las dos hipótesis se descartan en el desarrollo.** El holdout (2024-07-01 → 2026-09-30) **no se
abre**: el §7 solo lo permite si pasan todos los gates. Ver [decision.md](decision.md).
