# Carry · ciclo PDCA tras el drift de funding (PQ-123)

- **Origen:** el 23-nov-2026, `pq monitor drift` (PQ-86) dio la alerta de **drift de datos** en los
  cinco símbolos ([issue #120](https://github.com/PrometheusQuant/prometheus-platform/issues/120),
  `data/monitoring/drift/drift-2026-11-23.json`). Desde octubre de 2026 no hubo ninguna liquidación
  por encima de θ = 20 %, y el paper de H2 no abrió posiciones.
- **Fecha de este análisis:** 2026-11-25. **Agente:** Claude B.
- **Qué cambió desde que se abrió el ticket:** el 24-nov se abrió el holdout del carry (PQ-50) y
  **H2 se descartó** (0,22 % anual con datos nunca vistos). Por eso este ciclo ya no decide si se
  retoca H2: decide qué se hace con el carry como línea de trabajo.
- **Estado:** diagnóstico y opciones escritos. **La decisión es del titular** y se registra al
  final.

## Plan · diagnóstico: ¿régimen temporal o estructural?

**Los datos propios.** `uv run python scripts/pdca_regimen_funding.py` describe el funding
anualizado del silver por semestre. Es descriptivo: no evalúa ninguna regla y no es un ensayo.

Mediana del funding anualizado, y parte de las liquidaciones por encima de θ = 20 %:

| Semestre | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 2021-S1 | 28,1 % · 54 % | 40,1 % · 61 % | 15,8 % · 49 % | 16,5 % · 49 % | 48,6 % · 65 % |
| 2021-S2 | 10,9 % · 20 % | 10,9 % · 22 % | 10,9 % · 24 % | 0,0 % · 16 % | 10,9 % · 30 % |
| 2022-S1 | 7,3 % · 0 % | 6,1 % · 0 % | 4,3 % · 0 % | −2,8 % · 0 % | 8,7 % · 0 % |
| 2022-S2 | 4,7 % · 0 % | 2,8 % · 0 % | −0,6 % · 0 % | 0,0 % · 0 % | −0,1 % · 0 % |
| 2023-S1 | 8,3 % · 1 % | 8,4 % · 1 % | 10,7 % · 2 % | 0,0 % · 2 % | 10,9 % · 0 % |
| 2023-S2 | 10,4 % · 7 % | 9,9 % · 9 % | 10,9 % · 10 % | 0,0 % · 11 % | 10,9 % · 12 % |
| 2024-S1 | 10,9 % · 19 % | 10,9 % · 20 % | 10,9 % · 25 % | 0,0 % · 14 % | 10,9 % · 24 % |
| 2024-S2 | 9,9 % · 6 % | 10,3 % · 9 % | 8,1 % · 9 % | 0,0 % · 10 % | 10,9 % · 7 % |
| 2025-S1 | 4,4 % · 0 % | 5,2 % · 0 % | 1,1 % · 0 % | 0,0 % · 0 % | 4,5 % · 0 % |
| 2025-S2 | 5,9 % · 0 % | 5,3 % · 0 % | 3,8 % · 0,2 % | 0,0 % · 1,1 % | 6,2 % · 0,7 % |
| 2026-S1 | 1,7 % · 0 % | 1,2 % · 0 % | −1,6 % · 0 % | 0,0 % · 0 % | −1,8 % · 0 % |
| 2026-S2 (hasta el 20-nov) | 6,5 % · 0 % | 4,9 % · 0 % | 4,0 % · 0 % | 2,3 % · 1,9 % | 4,8 % · 0 % |

10,95 % es el piso habitual de Binance: el interés de 0,01 % cada 8 h. Una mediana por debajo de
ese valor significa que la prima fue negativa buena parte del semestre. BNB tiene otro esquema y su
mediana suele ser 0.

**Lo que muestran:**

- **El régimen alto es cíclico.** Aparece en las fases de apalancamiento alcista (2021-S1 y
  2024-S1) y desaparece en las bajistas (2022).
- **Pero esta vez dura más.** Desde 2025-S1 hay **cuatro semestres seguidos** prácticamente sin
  liquidaciones por encima del 20 %. El tramo bajista de 2022 a 2023-S1 duró unos tres. Y la mediana
  de 2025 a 2026 queda por debajo del piso incluso fuera de los momentos de pánico.

**Las fuentes públicas** coinciden y añaden una causa estructural:

- **El funding medio de BTC** fue del 11 % en 2024, el 4,9 % en 2025 y el 2,2 % en 2026 hasta
  agosto, según cifras de Ethena citadas por
  [FXStreet](https://www.fxstreet.com/cryptocurrencies/news/ethena-looks-beyond-crypto-to-squeeze-yield-from-booming-equity-perpetuals-202608281313).
- **La competencia por el mismo trade.** El capital institucional compite por el mismo carry, así
  que los picos alcistas duran menos y el funding se normaliza antes
  ([Blockworks](https://blockworks.com/newsletter/the-breakdown/issue/post_999b16ee-0fe0-4631-a1d0-2aa15a1d18a7)).
  BitMEX describe a Ethena, con unos 7.800 millones de USD listos para operar a finales de 2025,
  como uno de los arbitrajistas que venden en corto cuando la prima sube: hace de «techo» del
  funding ([BitMEX, 2025-Q3](https://www.bitmex.com/blog/2025q3-derivatives-report)).
  - Es la lectura de la industria, no un estudio con control. Las fuentes no se ponen de acuerdo
    sobre cuánto pesa cada causa.
- **Lo cíclico de 2025 a 2026.** La caída del 10-oct-2025 desapalancó el mercado, y el funding de
  BTC estuvo 67 días seguidos con media negativa de 30 días hasta mayo de 2026. Para finales de
  octubre de 2026 se recuperó a cerca del 8 % anual
  ([The Block](https://theblock.co/news/markets/2026-11-19-sygnum-bitcoin-carry-trades-beating-treasury-bills-2027-443547)).

**Diagnóstico.** Las dos causas se suman.

- **Hay un ciclo:** el desapalancamiento de 2025 y 2026 ya empezó a revertirse.
- **Y un techo estructural:** más capital de arbitraje hace el mismo carry, así que los episodios
  por encima del 20 %, que son los que H2 necesita, serán más raros y más cortos que en 2021 o 2024.

Para una regla que solo entra con más del 20 %, el techo importa más que el ciclo. Aunque el funding
vuelva al 8 o 10 %, eso está por debajo de θ.

## Do · opciones

| Opción | Qué cambia | Ensayos nuevos en N | Cómo se valida | Riesgo |
|---|---|---|---|---|
| **A. Archivar el carry con condiciones para retomarlo** (como H4) | Nada en el código. El paper sigue como demostración y el monitor de drift, como alerta temprana | 0 | No hace falta | Perder un régimen alto si vuelve. Lo cubren las condiciones de abajo |
| B. Una hipótesis nueva de carry (otra θ, otra *k* u otra regla) | Pre-registro nuevo | Los que declare | **Solo con datos futuros**: todos los históricos ya se vieron. Hacen falta ≥ 6 meses posteriores al 2026-09-30 | Diseñarla viendo esta tabla es data snooping; la validación tardaría más que el semestre |
| C. H4, varios exchanges (PQ-94) | Ya pre-registrada | Los suyos | Igual que B: su holdout ya está usado | Archivada el 24-nov por el mismo motivo |
| D. Reasignar el capital del carry (PQ-83) | Ya hecho: el presupuesto da 0 % al carry y 100 % a efectivo | 0 | `pq research budget` | Ninguno nuevo |

**Recomendación: A, que incluye D.**

- H2 ya está descartado y un régimen sin prima no se arregla con otra regla.
- Las condiciones para retomarlo son las mismas que se fijaron para H4, ampliadas a los cinco
  símbolos:
  1. **Régimen alto:** la media de 90 días del funding anualizado supera θ = 20 % durante al
     menos 30 días seguidos, en al menos tres de los cinco símbolos.
  2. **Validación nueva:** al menos 6 meses de datos posteriores al 2026-09-30, sin mirar, que
     sirvan de holdout para cualquier hipótesis nueva, que necesitará su pre-registro.
- **Act, si se aprueba:** añadir la condición 1 al monitor de drift como «señal de reactivación»,
  sin cambiar ninguna regla. Cerrar el issue #120 con el enlace a la decisión.

## Check y Act · decisión del titular

**Pendiente.** Se presenta en la sesión manual del 25-nov (19:00 a 20:00, hora de Bolivia).
