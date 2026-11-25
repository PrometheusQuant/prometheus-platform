# Estrategia 4 · Polymarket (sesgo favorito-longshot): evaluación en desarrollo (PQ-93)

- **Fecha:** 2026-11-25.
- **Ejecución:** una sola, con el [pre-registro](pre-registro.md) y su enmienda 1 (§12). La CLI se
  niega a ejecutarse si ya hay ensayos de Polymarket en el registro.
- **Comando:** `pq research polymarket`, carril `boris`.
- **Registro de ensayos:** las 6 configuraciones (P1 y P2, bandas B70, B80 y B90) se registraron
  antes de evaluar (`docs/estrategias/ensayos/boris.jsonl`). Familia `polymarket`, N = 6.
- **Datos:**
  - Catálogo: 1.127.465 mercados cerrados, de 2022-01 a 2026-10.
  - Precios diarios del CLOB de los mercados que la evaluación necesita (silver
    `prices_1440`, 2.691.950 puntos).
  - Universo con cierre de 2023-01 a 2025-06: 37.001 mercados. El 1,5 % de sus tokens no tiene
    historial en el CLOB.
  - Antes de ejecutar se registró **KE-023**: un punto diario con precios 1,0025 y −0,0025 se
    conserva crudo con el precio en nulo, igual que el relleno de §4. Son 2 filas.
- **Periodo:** entradas del 2023-01-01 al 2025-06-30, con corte point-in-time al
  2025-06-30 23:59:59 UTC. **El holdout (julio de 2025 a junio de 2026) no se leyó.**
- **Artefactos:** `data/research/polymarket/P1|P2/summary.json`, el PnL diario y las apuestas de la
  configuración principal.

## Resultado de los gates (escenario de costes principal)

La configuración principal de cada hipótesis es la banda **B80** (0,80 a 0,95), fijada en el
pre-registro. Las bandas B70 y B90 cuentan en N y en el PBO.

| Gate | Criterio | P1, fuera de deportes (P1-B80) | P2, deportes, control (P2-B80) |
|---|---|---|---|
| G1 | Deflated Sharpe > 0,95 (N = 6) | 0,010 ❌ | 0,085 ❌ |
| G2 | PBO < 0,5 | **0,42** ✅ | 0,93 ❌ |
| G3 | t agrupado por evento > 3 | −2,07 ❌ | −0,43 ❌ |
| G4 | Retorno por apuesta > 0, > B1 y por dólar-año > 4 % | −0,59 % ❌ | −0,20 % ❌ |
| G5 | Retorno ponderado por evento > 0 | −0,67 % ❌ | −1,43 % ❌ |
| | **Veredicto** | **No pasa: descartada** | **No pasa: descartada** |

| Configuración | Apuestas | Eventos | Acierto | Retorno por apuesta | t agrupado | Por dólar-año |
|---|---|---|---|---|---|---|
| P1-B70 (0,70 a 0,85) | 11.276 | 5.117 | 79,0 % | +0,23 % | 0,52 | +2,9 % |
| **P1-B80 (0,80 a 0,95)** | 13.220 | 5.845 | 88,3 % | **−0,59 %** | −2,07 | −6,3 % |
| P1-B90 (0,90 a 0,98) | 12.342 | 5.495 | 94,5 % | −0,57 % | −2,91 | −6,4 % |
| B1 de P1: todo favorito | 23.166 | 9.217 | 74,8 % | −1,68 % | −3,72 | −21,4 % |
| P2-B70 | 6.852 | 3.802 | 77,9 % | −0,05 % | −0,08 | −1,0 % |
| **P2-B80** | 5.674 | 2.391 | 88,7 % | **−0,20 %** | −0,43 | −2,9 % |
| P2-B90 | 4.666 | 1.283 | 95,5 % | −0,58 % | −1,87 | −6,0 % |

**Sensibilidades de P1-B80 (solo se informan):**

| Escenario | Retorno por apuesta | t agrupado |
|---|---|---|
| Principal | −0,59 % | −2,07 |
| Sin comisión | +0,05 % | 0,18 |
| Diferencial de entrada 0 | +0,49 % | 1,71 |
| Diferencial de entrada +0,02 | −1,66 % | −5,85 |
| Sin diferencial de salida | −0,47 % | −1,63 |
| Volumen mínimo de 10.000 USD | −1,41 % | −4,34 |

**Correlación diaria** de P1 con el carry H2: 0,05; con la tendencia T1: 0,00 (547 días comunes,
2023 a junio de 2024).

**Exclusiones del universo de P1:** 39 mercados no binarios y 48 con pago sin definir conocido al
corte. Ningún punto a más de 1 minuto de las 00:00 UTC.

## Lectura

- **El sesgo favorito-longshot no se ve neto de costes.** El favorito gana en el 88 % de los casos,
  pero lo que se paga por él (0,80 a 0,95 más 1 centavo de diferencial y la comisión) se come la
  ventaja. Neto, P1 pierde un 0,59 % por apuesta, y el t de −2,07 apunta más a una pérdida que a
  una ganancia.
- **Ni siquiera con costes optimistas hay ventaja significativa.** Sin comisión, el retorno es de
  +0,05 % por apuesta (t = 0,18). Comprando exactamente al precio de la instantánea, +0,49 %
  (t = 1,71). Ninguno se acerca a t > 3. El escenario principal es pesimista a propósito, porque
  aplica las comisiones de 2026 a todo el periodo (§6), pero eso no cambia la conclusión.
- **Más volumen no ayuda; empeora.** Con mercados de 10.000 USD o más, la pérdida sube a −1,41 % por
  apuesta. Es lo esperable si los mercados líquidos están mejor valorados.
- **El control se comporta como el principal.** En deportes tampoco hay ventaja (−0,20 %).
- **Lo único que se cumple es la diversificación.** El retorno de Polymarket no tiene correlación
  con el carry ni con la tendencia, pero no hay retorno que diversificar.

## Decisión

**P1 y P2 se descartan en el desarrollo.** El holdout no se abre. Ver [decision.md](decision.md).
