# Overlay de sentimiento sobre el momentum: evaluación en desarrollo (PQ-128)

- **Fecha:** 2026-11-25.
- **Ejecución:** una sola, después de la evaluación del momentum (PQ-114), como pide el §8 del
  [pre-registro](pre-registro.md). David decidió evaluarlo el 25-nov aunque la base no pasó sus
  gates; el pre-registro lo preveía («se evalúa aunque la base no pase»).
- **Comando:** `pq research sentimiento`, carril `boris`.
- **Registro de ensayos:** S1-X1-L28 y S2-X2-L28 se registraron antes de evaluar
  (`docs/estrategias/ensayos/boris.jsonl`). La familia `tendencia` pasa a N = 20.
- **Datos:** Crypto Fear & Greed Index de alternative.me, ingerido con `pq sentimiento descargar`
  (3216 días, del 2018-02-01 al 2026-11-25). Fuente: Crypto Fear & Greed Index de alternative.me.
  El universo y el motor son los del momentum, sin cambiar sus reglas.
- **Periodo:** desarrollo, del 2021-02-01 al 2024-06-30 (1246 días, 178 lunes). **El holdout no se
  leyó.**
- **Artefactos:** `data/research/sentimiento/S1|S2/summary.json` y `daily_returns.parquet`.
- **Figuras:** [S1](img/s1-curvas.png) y [S2](img/s2-curvas.png), cada una frente a su base sin
  filtro.

## Resultado de los gates (escenario de costes principal)

| Gate | Criterio | S1 (sobre X1-L28) | S2 (sobre X2-L28) |
|---|---|---|---|
| G1 | Deflated Sharpe > 0,95 con N de la familia = 20 | 0,081 ❌ | 0,144 ❌ |
| G2 | PBO < 0,5 (base frente a overlay) | **0,233** ✅ | **0,170** ✅ |
| G3 | t de la media diaria > 3 | 0,89 ❌ | 1,25 ❌ |
| G4 | S1: CAGR > 4 %. S2: Sharpe > B1 (0,30) y CAGR > 4 % | **8,8 %** ✅ | **0,68 y 25,8 %** ✅ |
| G5 | Sharpe > base, en el periodo completo y en la mediana de la CPCV | **0,48 frente a 0,24; 0,43 frente a 0,24** ✅ | **0,68 frente a 0,26; 0,56 frente a 0,20** ✅ |
| | **Veredicto** | **No pasa (G1 y G3)** | **No pasa (G1 y G3)** |

| Métrica | S1 | X1-L28 (base) | S2 | X2-L28 (base) |
|---|---|---|---|---|
| Sharpe neto | 0,48 | 0,24 | 0,68 | 0,26 |
| CAGR neto | 8,8 % | 2,9 % | 25,8 % | −14,0 % |
| Drawdown máximo | −32,3 % | −46,4 % | −71,0 % | −92,9 % |
| Peor mes | −8,6 % | −8,8 % | −25,9 % | −35,0 % |

**Lo que el §8 pide informar:**

| | S1 | S2 |
|---|---|---|
| Semanas en efectivo | 37 de 178 lunes (21 %) | 37 de 178 (21 %) |
| Retorno de la base en esas semanas (lo que el filtro evitó) | −17,9 % | −74,3 % |
| Costes extra de salir y volver a entrar | 0,4 % del capital | 12,7 % del capital |
| Correlación diaria con el carry H2 | 0,02 | 0,10 |
| Correlación con la tendencia T1 / T2 | 0,05 / 0,04 | 0,62 / 0,33 |

## Lectura

- **El filtro hizo lo que el mecanismo predecía.** Las semanas de miedo extremo fueron malas para
  el momentum: la base perdió un 18 % (X1) y un 74 % (X2) en ellas. Quedarse fuera dobló el Sharpe
  de X1 y convirtió a X2 de −14 % a +26 % anual. La mejora se sostiene fuera de muestra: en la
  mediana de los caminos de prueba de la CPCV, el overlay también gana a su base, y el PBO es bajo.
- **Pero no es significativo.** El t de S1 es 0,89 y el de S2, 1,25; se exige más de 3. Con N = 20
  ensayos en la familia, el Deflated Sharpe queda en 0,08 y 0,14. Un Sharpe de 0,5-0,7 en 3,4
  años de datos diarios con colas pesadas (curtosis 16 y 7) no se distingue del azar con la
  exigencia del protocolo.
- **Parte de la mejora es precio con otro nombre.** El índice incluye la volatilidad y el momentum
  del mercado (riesgo declarado en el §2). S2 es casi una apuesta larga a las altcoins
  (correlación 0,62 con la tendencia): salir en el miedo extremo se parece a un stop por caída del
  mercado.
- **S2 sigue siendo inaceptable en riesgo:** cae un 71 % en su peor momento, aunque menos que la
  base (−93 %).

## Decisión

**S1 y S2 se descartan en el desarrollo: no pasan G1 ni G3.** El holdout no se abre. Ver
[decision.md](decision.md).
