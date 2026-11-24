# Estrategia 1 · Carry de funding: evaluación en el periodo de desarrollo

- **Tickets:** PQ-23 (backtest), PQ-24 (registro de experimentos), PQ-25 (validación)
- **Fecha de ejecución:** 2026-10-30, **una sola ejecución por hipótesis**, con el código del commit `e4cd835`
- **Periodo:** desarrollo, del 2020-01-03 al 2024-07-01 (1.642 días). **El holdout no se abrió.**
- **Protocolo:** [pre-registro](pre-registro.md), con la enmienda 1 (fijada antes del primer
  backtest) y la enmienda 2 (corrección del apalancamiento 1x, declarada antes de esta evaluación)
- **Reproducir:** `pq silver build --symbol <S>` para los 5 símbolos y luego
  `pq research carry --hypothesis H1` y `--hypothesis H2`. Los ensayos quedan en MLflow
  (`data/mlflow/mlflow.db`; se ven con `uvx mlflow ui --backend-store-uri sqlite:///data/mlflow/mlflow.db`).

## Reejecución del 2026-11-24 (enmienda 3): resultados vigentes

Tras corregir KE-014 y KE-016 y verificar las comisiones (PQ-17, iguales al modelo), se repitió
**una sola vez** la evaluación. Orden: H1 y luego H2. La enmienda 3 se publicó antes de ejecutar.
**El veredicto no cambia.** El resto de este documento conserva la evaluación del 2026-10-30 como
historial.

| | H1 (k3-theta20) antes → ahora | H2 (k9-theta20) antes → ahora |
|---|---|---|
| N del Deflated Sharpe | 20 → **29** | 20 → **38** |
| G1 Deflated Sharpe > 0,95 | 1,000 → **1,000** ✅ | 1,000 → **1,000** ✅ |
| G2 PBO < 0,5 | 0,149 → **0,220** ✅ | 0,045 → **0,020** ✅ |
| G3 t > 3 | 16,32 → **16,39** ✅ | 11,82 → **11,84** ✅ |
| G4 Sharpe > B1 y CAGR > 4 % | 7,69 frente a 9,18 → **7,73 frente a 8,75** ❌ | 5,57 frente a 0,66 → **5,58 frente a 0,61** ✅ |
| CAGR neto | 6,52 % → **6,53 %** | 5,03 % → **5,10 %** |
| Drawdown máximo | −0,51 % → **−0,43 %** | −0,39 % → **−0,54 %** |
| **Decisión** | **Se descarta** (G4) | **Pasa al holdout** |

- **Configuraciones:** las elegidas por CPCV son las mismas que en octubre.
- **Registro:** los 18 ensayos nuevos están en `docs/estrategias/ensayos/david.jsonl`.
- **Holdout:** PQ-17 ya verificó las comisiones, así que H2 puede abrirlo (PQ-50). Se abre **una
  sola vez y con el titular presente**.

### Revisión adversarial de la reejecución (doubt-driven-development)

Un revisor con contexto fresco, que no recibió la conclusión, auditó el código y reprodujo bit a bit
dos configuraciones registradas de H2 sin crear ensayos nuevos. **No encontró nada que invalide el
resultado:**

- KE-016: todas las ejecuciones caen en la primera vela que abre en *t* + 1 h o después;
- KE-014: ninguna orden, vela ni liquidación del 2024-07-01 en adelante;
- funding solo con la posición abierta;
- costes en ambas patas en cada operación;
- N cuadra con el registro.

Sí dejó **dos matices importantes**, que quedan escritos antes del holdout:

1. **El Sharpe de 5,6 de H2 está inflado por la autocorrelación.** Los retornos diarios están
   correlacionados: 0,59, 0,54 y 0,41 en los retardos 1 a 3. El Sharpe da otra cosa al medirlo de
   otras formas:
   - 2,99 con retornos semanales;
   - 1,74 con mensuales;
   - 2,51 con el ajuste de Lo.

   **La cifra honesta es de 1,7 a 3.** La t con Newey-West baja a 3,7–5,2 y G3 sigue pasando. El
   Deflated Sharpe con retornos semanales sigue en 1,0. El gate pasa según el pre-registro; es una
   cuestión de cómo presentar la cifra.
2. **El resultado de H2 depende de 2021.**
   - De enero a mayo de 2021 sale más de la mitad de la ganancia total.
   - En 2022 la estrategia no estuvo invertida ningún día.
   - Del 2022-01-01 al 2024-07-01 ganó en total un +2,9 % (≈ 1,2 % anual), **por debajo del 4 % de
     una stablecoin**.

   El holdout (2024-07 → 2026-09) es un periodo de funding comprimido: hay un riesgo real de que no
   alcance el criterio de éxito.

Menores, sin efecto en el veredicto:

- un hueco de velas del perp de SOL y XRP en 2022 congela la marca del perp: afecta a B1, no a la
  elegida, que no estaba invertida;
- con la salida decidida y la pata perp pendiente, el funding de esa pata no se contabiliza (no
  ocurrió en las ejecuciones auditadas);
- una posición abierta el último día no paga el cierre: favorece a B1, no a las elegidas;
- los 2 ensayos de la prueba de humo están en el código y no tienen filas en el registro, que por
  eso muestra 36;
- la sensibilidad del efectivo al 4 % exagera el Sharpe.

Las mejoras de método van en [PQ-122](https://prometheusquant.atlassian.net/browse/PQ-122), para
pre-registros futuros.

## Resumen (evaluación del 2026-10-30, historial)

| Hipótesis | Configuración elegida (CPCV) | Sharpe neto | CAGR neto | Gates | Decisión |
|---|---|---|---|---|---|
| **H1** BTC + ETH | k = 3, θ = 20 % | 7,69 | 6,52 % | G1 ✅ G2 ✅ G3 ✅ **G4 ❌** | **Se descarta**: el timing no bate al carry siempre activo |
| **H2** SOL + BNB + XRP | k = 9, θ = 20 % | 5,57 | 5,03 % | G1 ✅ G2 ✅ G3 ✅ G4 ✅ | **Pasa a holdout**, que se abre solo cuando PQ-17 verifique las comisiones |

**Lectura honesta.** Un Sharpe de 5 a 9 **no** significa una máquina de dinero. Un carry
delta-neutral cobra funding casi todos los días y cubre el precio, así que sus retornos diarios
son muy estables. El riesgo real está en eventos que el backtest no contiene: quiebra del exchange,
autodesapalancamiento (ADL), liquidaciones y depeg de la stablecoin (pre-registro §9). Eso es lo
que advierte el BIS: el carry es una prima por riesgo de cola. La métrica que importa para decidir
es el **CAGR frente al 4 % de una stablecoin**: H2 lo supera por solo **1 punto**.

### H1 · BTCUSDT, ETHUSDT

| Métrica | Elegida (k3-theta20) | B1 siempre activo |
|---|---|---|
| Sharpe anualizado (neto) | **7,69** | 9,18 |
| CAGR neto | 6,52 % | 8,28 % |
| Drawdown máximo | -0,51 % | -0,87 % |
| Calmar | 12,7 | 9,5 |
| t-estadístico | 16,3 | 19,5 |
| Asimetría / curtosis (diarias) | 1,82 / 19,5 | -0,26 / 48,4 |

| Gate | Criterio | Valor | Resultado |
|---|---|---|---|
| G1 | Deflated Sharpe > 0.95 (N = 20) | 1,0000 | ✅ pasa |
| G2 | PBO < 0.5 | 0,1486 | ✅ pasa |
| G3 | t > 3.0 | 16,3182 | ✅ pasa |
| G4 | Sharpe > B1 (9.18) y CAGR > 4% | 7,6937 | ❌ no pasa |

**Descomposición del P&L** (capital inicial = 1): funding 0,361, precio y basis 0,005, costes -0,037; 25 ciclos de entrada/salida; invertido el 37,88 % del tiempo.

**Sensibilidad (solo informativa):** con costes maker y BNB, Sharpe 8,26; con un 4 % anual sobre el efectivo ocioso, Sharpe 10,72.

**Sharpe medio de prueba en CPCV (15 particiones)**

| Configuración | Sharpe CPCV |
|---|---|
| k3-theta20 ← elegida | 7,84 |
| k9-theta20 | 7,70 |
| k21-theta10 | 7,30 |
| k9-theta10 | 7,20 |
| k21-theta20 | 6,76 |
| k21-theta30 | 5,87 |
| k9-theta30 | 5,50 |
| k3-theta30 | 3,94 |
| k3-theta10 | 3,91 |

### H2 · SOLUSDT, BNBUSDT, XRPUSDT

| Métrica | Elegida (k9-theta20) | B1 siempre activo |
|---|---|---|
| Sharpe anualizado (neto) | **5,57** | 0,66 |
| CAGR neto | 5,03 % | 2,51 % |
| Drawdown máximo | -0,39 % | -11,16 % |
| Calmar | 12,8 | 0,2 |
| t-estadístico | 11,8 | 1,4 |
| Asimetría / curtosis (diarias) | 2,90 / 24,2 | -8,79 / 466,3 |

| Gate | Criterio | Valor | Resultado |
|---|---|---|---|
| G1 | Deflated Sharpe > 0.95 (N = 20) | 1,0000 | ✅ pasa |
| G2 | PBO < 0.5 | 0,0449 | ✅ pasa |
| G3 | t > 3.0 | 11,8198 | ✅ pasa |
| G4 | Sharpe > B1 (0.66) y CAGR > 4% | 5,5728 | ✅ pasa |

**Descomposición del P&L** (capital inicial = 1): funding 0,314, precio y basis 0,011, costes -0,079; 69 ciclos de entrada/salida; invertido el 27,19 % del tiempo.

**Sensibilidad (solo informativa):** con costes maker y BNB, Sharpe 6,75; con un 4 % anual sobre el efectivo ocioso, Sharpe 8,88.

**Sharpe medio de prueba en CPCV (15 particiones)**

| Configuración | Sharpe CPCV |
|---|---|
| k9-theta20 ← elegida | 5,77 |
| k21-theta20 | 5,52 |
| k21-theta30 | 5,04 |
| k3-theta20 | 4,99 |
| k9-theta30 | 4,42 |
| k9-theta10 | 3,16 |
| k3-theta30 | 2,90 |
| k21-theta10 | 2,76 |
| k3-theta10 | 1,15 |

## Figuras

![H1: curvas de capital](img/h1-curvas.png)

En gris, las 9 configuraciones; en naranja, la elegida por CPCV; en azul discontinuo, B1. En 2022
(mercado bajista, funding bajo o negativo) la estrategia se queda fuera mientras B1 sigue cobrando
el funding base. Por eso B1 termina por encima en BTC y ETH.

![H2: curvas de capital](img/h2-curvas.png)

En las altcoins, B1 sufre: paga funding negativo y aguanta la basis en los episodios de estrés
(drawdown de −11 %), y ahí el filtro por umbral sí aporta.

## Integridad del proceso

- **Ensayos (N = 20):** 9 configuraciones por hipótesis registradas en MLflow por Optuna
  `GridSampler`, más las 2 ejecuciones de la prueba de humo declaradas en la enmienda 2.
- **Prueba de humo:** detectó un error real (el apalancamiento crecía con el precio hasta ~4x). Se
  corrigió antes de la evaluación y se declaró en la enmienda 2.
- **Holdout:** cerrado. El código de evaluación corta todas las simulaciones en `HOLDOUT_START`
  (2024-07-01), y `development_only` anula el objetivo del modelo cuya siguiente liquidación cae en
  el holdout. Por la enmienda 1.11, el holdout de H2 no se abre hasta que PQ-17 verifique las
  comisiones desde la cuenta.
- **Lo que no se modela:** costes de financiación del margen, cambios de nivel VIP, latencia real
  de ejecución, ADL y liquidaciones (pre-registro §9).

## Próximo paso

Ver [decision.md](decision.md).
