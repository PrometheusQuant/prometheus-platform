# Estrategia 2 · Tendencia: evaluación en desarrollo (PQ-68)

- **Fecha:** 2026-11-23.
- **Ejecución:** una sola, tras verificar las comisiones reales en PQ-17. Son iguales al escenario
  principal, así que el pre-registro no necesitó enmienda.
- **Comando:** `pq research trend`, carril `boris`.
- **Registro de ensayos:** las 12 configuraciones quedaron registradas antes de evaluar
  (`docs/estrategias/ensayos/boris.jsonl`).
- **Periodo:** desarrollo, del 2020-05-02 al 2024-06-30 (1522 días). **El holdout no se leyó:** las
  velas y el funding se recortan antes del 2024-07-01 al cargarlos.
- **Artefactos:** `data/research/trend/T1|T2/summary.json` y `daily_returns.parquet`.
- **Figuras:** [T1](img/t1-curvas.png) y [T2](img/t2-curvas.png).

## Resultado de los gates (escenario de costes principal)

| Gate | Criterio | T1 (larga, elegida L120-vol20) | T2 (larga y corta, elegida L120-vol40) |
|---|---|---|---|
| G1 | Deflated Sharpe > 0,95 con N de la familia = 12 | **0,987** ✅ | 0,867 ❌ |
| G2 | PBO < 0,5 | **0,355** ✅ | 0,626 ❌ |
| G3 | t de los retornos diarios netos > 3 | **3,52** ✅ | 2,43 ❌ |
| G4 | Sharpe > B1 (1,18) y CAGR > 4 % | **1,73** y 32,6 % ✅ | 1,19 y 46,6 % ✅ |
| | **Veredicto** | **Pasa los cuatro** | **No pasa: descartada** |

| Métrica de T1 elegida | Valor | B1 comprar y mantener | B3 sin vol targeting |
|---|---|---|---|
| Sharpe neto | 1,73 | 1,18 | 1,45 |
| CAGR neto | 32,6 % | 80,8 % | 97,4 % |
| Drawdown máximo | −11,9 % | −77,4 % | −51,5 % |
| Calmar | 2,73 | 1,04 | 1,89 |
| Volatilidad realizada frente a σ* | 17,2 % frente a 20 % | | |
| Tiempo invertido | 66 % | | |
| Costes totales | −4,3 % del capital en 4,2 años | | |

**Sensibilidad (solo se informa):**

- Sharpe con costes de maker con BNB: 1,74.
- Sharpe con el efectivo ocioso remunerado al 4 %: 1,80.

**N global de la plataforma:** 75 ensayos. Son 18 de carry, 45 del modelo de funding y 12 de
tendencia (`pq research registro resumen`, 2026-11-23). El §5 del pre-registro pide informarlo,
aunque G1 se mide con el N de la familia.

## Revisión adversarial (doubt-driven-development)

Antes de aceptar el resultado, un revisor con contexto fresco intentó refutarlo. No recibió la
conclusión, solo el código, los datos y el pre-registro. **No encontró nada que invalide el
resultado:**

- **Sin look-ahead.**
  - Se decide con el cierre de la vela de las 23:00 y se ejecuta al open de la vela de la hora
    siguiente.
  - Una prueba sintética con un salto concentrado entre las 00:00 y las 01:00 no lo captura.
  - Con precios martingala y sin costes, el Sharpe sale compatible con cero (30 semillas).
- **Costes en cada ejecución,** incluidos los rebalanceos del vol targeting. El total reportado
  cuadra con rotación × años × coste por lado.
- **Holdout intacto.** B1 usa los mismos días, los mismos costes de entrada y la misma latencia.
- **Fórmula del Deflated Sharpe correcta;** el valor reportado se recalcula exacto. La varianza de
  Sharpe entre ensayos mezcla T1 y T2, lo que es conservador.

Sí encontró **fragilidades que matizan el resultado.** Se registran aquí antes de abrir el holdout,
para que nadie las descubra después:

1. **La selección es, en la práctica, dentro de la muestra.**
   - El §8 elige «la configuración con mejor Sharpe medio de prueba en las 15 particiones». Con
     6 grupos y 2 de prueba, cada día cae en prueba 5 de 15 veces. Así, la media de prueba ordena las
     configuraciones igual que el Sharpe de toda la muestra.
   - Las reglas no tienen parámetros que ajustar con el tramo de entrenamiento, así que el purge y
     el embargo no cambian nada.
   - Se cumple la letra del pre-registro, pero no hay validación fuera de muestra. **La única
     corrección por selección es el Deflated Sharpe, y la prueba de verdad es el holdout.**
2. **G1 pasa con el N de la familia, no con el global.**
   - Con N = 12, como fija el contrato, el Deflated Sharpe es 0,987.
   - Con el N global de 75 sería 0,948, por debajo de 0,95.
3. **El resultado depende mucho de mayo a diciembre de 2020.**
   - Esos 244 días (el 16 % de la muestra) aportan el 42 % de la suma de retornos.
   - Sharpe por año: 3,65 (2020), 1,41 (2021), 0,01 (2022), 1,30 (2023) y 2,16 (primer semestre
     de 2024).
   - Sin 2020, el Sharpe sería 1,27 y la t 2,37: no pasaría G3.
4. **G4 es una comparación de puntos.** La diferencia de Sharpe con B1 no es estadísticamente
   significativa (prueba de Jobson-Korkie/Memmel, z ≈ 1,1–1,7, según la correlación supuesta). El
   CAGR de T1 es muy inferior al de B1: la ventaja de T1 está en el riesgo (drawdown de −12 % frente
   a −77 %), no en el retorno.
5. **Menores:**
   - con corrección de Newey-West por autocorrelación, la t baja a 3,1–3,5 (entre 5 y 20 lags) y
     sigue pasando;
   - la «rotación anual» (8,63) suma nocional en unidades absolutas, no como fracción del capital,
     y la sobreestima;
   - la sensibilidad del efectivo al 4 % subestima el efectivo ocioso;
   - con correlaciones de 0,76 o más entre las 6 configuraciones, el PBO tiene poca potencia.
6. **Ejecuciones sin registrar:** ninguna. La evaluación con datos reales se ejecutó solo esta vez,
   y el registro tiene exactamente sus 12 filas.

Las correcciones de método (selección fuera de muestra de verdad, rotación como fracción del
capital, t con Newey-West, N global en los informes) se aplicarán a pre-registros **futuros**, no a
este, en [PQ-122](https://prometheusquant.atlassian.net/browse/PQ-122). Cambiarlas ahora, después de
ver el resultado, sería ajustar el método a los datos.

## Decisión

- **T2 se descarta** (§8). Una variante necesitaría un pre-registro nuevo y un holdout nuevo.
- **T1 pasa los gates del pre-registro.** Según el §7, el siguiente paso es **abrir el holdout de la
  tendencia** (2024-07-01 → 2026-09-30) una sola vez, con la configuración elegida y sin
  re-ajustes. El criterio de éxito está fijado: Sharpe neto > 0,5, CAGR neto > 4 % y drawdown
  máximo < 30 %.
- **Abrir el holdout es irreversible. Lo hace el titular presente**, y su resultado irá en
  `holdout.md`. Dadas las fragilidades 1 a 3, el holdout es la única prueba fuera de muestra que
  tiene esta estrategia.
