# Monitoreo de drift (PQ-86)

Fase 6 de CRISP-ML(Q): vigilar si el mundo dejó de parecerse al periodo en que se diseñó y validó
la estrategia. Tres detectores, cada uno con un umbral fijo. Si alguno lo cruza, **avisa y no
cambia nada**. Lo manda la [definición de terminado](../metodologia/definicion-de-listo-y-terminado.md),
fase 6: «prohibido retocar sin un nuevo ciclo PDCA».

```bash
uv run pq monitor drift                    # informe en pantalla y en data/monitoring/drift/
uv run pq monitor drift --send --ticket    # además: alerta al grupo e issue en GitHub
```

Sale con código 1 si algún detector cruzó su umbral, y con 0 si no; sirve para cron.

## Los tres detectores

| Detector | Qué compara | Estadístico | Umbral de alerta |
|---|---|---|---|
| Datos | Funding anualizado posterior al holdout frente al del desarrollo, por símbolo (BTC, ETH, SOL, BNB y XRP) | PSI con los deciles del desarrollo como tramos; KS de dos muestras como contraste | **PSI ≥ 0,25** |
| Modelo | Calibración del clasificador del capítulo 5 («¿la siguiente tasa superará el 20 %?»), entrenado solo con el desarrollo, sobre las liquidaciones posteriores al holdout con resultado conocido | ECE con 10 tramos de probabilidad; Brier y AUC como contexto | **ECE ≥ 0,10** |
| Desempeño | Capital del paper trading (inicio = 1) frente a la banda del Monte Carlo del carry H2 para los mismos días | Remuestreo por bloques de los retornos diarios del desarrollo, como la pestaña de cartera (PQ-84) | **Fuera de p5–p95** |

Por qué esos umbrales:

- **PSI:** es la convención de riesgo de crédito: < 0,10 estable, 0,10–0,25 cambio moderado,
  ≥ 0,25 cambio grande. El KS no decide la alerta porque, con cientos de liquidaciones, casi
  cualquier diferencia sale significativa. El PSI, en cambio, mide **cuánto** cambió.
  - Los tramos vacíos se suavizan sumando 0,5 a cada conteo.
  - Con muchos empates (el funding clavado en la tasa base de 0,01 %) quedan menos de 10 tramos.
- **ECE:** una diferencia media de 10 puntos entre la probabilidad que dice el modelo y la
  frecuencia observada ya cambia decisiones: el modelo dice «80 %» y pasa en el 70 %.
- **Banda p5–p95:** una de cada diez veces el paper cae fuera solo por azar. Por eso la alerta
  pide revisar y no decide nada.

Los umbrales viven en `research/drift.py` (`PSI_ALERT`, `ECE_ALERT`). Si cambian, este runbook
cambia en el mismo PR.

## El holdout no se toca

- La **referencia** es el desarrollo (`development_only`, hasta el 30-jun-2024).
- **En vivo** es todo lo posterior al fin del holdout (`HOLDOUT_END`, 30-sep-2026), que llega a
  silver con la ingesta de la API (`pq ingest --source api`, PQ-65).
- El holdout (2024-07-01 → 2026-09-30) no se lee: una prueba lo verifica metiendo valores
  imposibles en ese periodo.
- Es monitoreo, no un ensayo: no escribe filas en el registro de ensayos ni cuenta en N.

## Qué hacer con una alerta

1. **No ajustes nada:** ni parámetros, ni umbrales, ni el modelo. Ningún ajuste automático existe a
   propósito.
2. Con `--ticket` se abre un issue en GitHub con la etiqueta `drift`, uno por detector: si ya hay
   uno abierto, se reutiliza. Necesita `gh` con sesión iniciada en la máquina que lo corre.
3. Revisa el informe `data/monitoring/drift/drift-<fecha>.json`:
   - en **datos**, las medianas de referencia y en vivo, por símbolo;
   - en **modelo**, la tabla de calibración por tramos.
4. Decide con el titular si hace falta un **ciclo PDCA nuevo**:
   - si hace falta, se crea un ticket PQ en Jira (Plan), con pre-registro o enmienda fechada si
     toca la estrategia;
   - si no, se cierra el issue explicando por qué. Por ejemplo: un régimen de funding bajo es
     justo lo que la regla de entrada ya filtra.
5. Si además el paper está en pérdidas, sigue los runbooks de
   [incidentes](incidentes.md) y [kill-switch](kill-switch.md): el drift no los reemplaza.

## Programarlo

En el servidor (PQ-57), una vez por semana: el drift de datos se mueve lento, y correrlo a diario
repetiría la misma alerta.

```bash
# los lunes a las 07:00 UTC, después de la ingesta diaria y del informe semanal
0 7 * * 1 cd /ruta/prometheus-platform && uv run pq monitor drift --send --ticket >> ~/drift.log 2>&1
```

## Primera medición (23-nov-2026)

`pq monitor drift` sobre el lakehouse de la laptop, con 153 liquidaciones por símbolo posteriores
al holdout (hasta el 20-nov):

- **Datos:** alerta en los cinco símbolos, con PSI entre 1,07 y 1,97.
  - El funding bajó: la mediana anualizada de BTC pasó de 10,95 % a 5,9 %, y la de ETH a 4,1 %.
  - El régimen alto (> 20 %) no apareció ni una vez desde octubre.
  - Encaja con que el carry H2 no abra posiciones en el paper.
- **Modelo:** sin alerta (ECE 0,012; AUC 0,972 sobre 730 liquidaciones). Sigue reconociendo bien
  cuándo no viene un régimen alto.
- **Desempeño:** sin alerta: el paper sigue plano dentro de la banda a 10 días.

La alerta de datos no se envió ni abrió un issue: esa primera decisión es del titular.
