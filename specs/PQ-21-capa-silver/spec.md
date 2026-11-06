# Especificación: capa silver (datos validados y point-in-time)

- **Ticket:** PQ-21 · **Rama:** `feature/PQ-21-capa-silver` · **Fecha:** 2026-10-30 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit v1.2.5, adaptada al español (spike PQ-30)
- **Entrada:** historia PQ-21 en Jira y hallazgos 1–5 de la [auditoría de Data Vision](../../docs/investigacion/2026-10-23-auditoria-binance-data-vision.md)

## Escenarios de usuario y pruebas

### Historia 1: velas limpias para investigar (P1)

Como investigador, quiero las velas de 1 h de spot y del perpetuo en un formato único, con tipos
numéricos y en UTC, para poder unirlas sin errores de unidad.

**Prueba independiente:** construir silver de BTCUSDT a partir de bronze y comprobar que spot 2024-12
(ms) y 2025-01 (µs) quedan alineados en la misma escala.

**Escenarios de aceptación**

1. **Dado** un bronze de spot con `open_time` en µs (2025), **cuando** se construye silver,
   **entonces** `open_time` sale en UTC con la misma escala que los archivos en ms.
2. **Dado** un CSV de futuros sin cabecera (2021) y otro con cabecera (2022), **cuando** se construye
   silver, **entonces** ambos dan las mismas columnas y tipos.
3. **Dado** un hueco real de mercado, **cuando** se construye silver, **entonces** el hueco queda
   en el informe de calidad y **no se imputa**.

### Historia 2: funding comparable entre símbolos (P1)

Como investigador, quiero el funding con su intervalo real y anualizado, para no subestimar el
pago cuando el exchange cambia de 8 h a 2 h.

**Escenarios de aceptación**

1. **Dada** una tasa con `funding_interval_hours = 2`, **cuando** se anualiza, **entonces**
   `tasa × 8760 / 2`.
2. **Dado** un `calc_time` con jitter (`16:00:00.002`), **cuando** se construye silver,
   **entonces** `funding_time` = 16:00:00 y el valor original se conserva.

### Historia 3: la construcción falla ante datos imposibles (P2)

**Escenarios de aceptación**

1. **Dada** una vela con `high < low` o un precio ≤ 0, **cuando** se valida, **entonces** la
   construcción falla con el nombre del check y la fila.
2. **Dadas** dos filas con la misma clave y valores distintos, **cuando** se deduplica,
   **entonces** falla. Si son idénticas, se deja una y se cuenta.

### Casos límite

- Símbolo sin datos en bronze: error claro, no un archivo vacío.
- Rango que cruza el cambio ms → µs dentro del mismo símbolo.
- Intervalo de funding fuera de {1, 2, 4, 8} h: falla.

## Requisitos

### Requisitos funcionales

- **FR-001**: normalizar timestamps a ms UTC según el número de dígitos, nunca según la fecha.
- **FR-002**: detectar la cabecera por contenido. Bronze ya resuelve los nombres (PQ-20); silver
  tipa las columnas.
- **FR-003**: `event_time` y `knowledge_time` en cada fila. En las velas,
  `knowledge_time = open_time + intervalo`; en el funding, `knowledge_time = funding_time`.
- **FR-004**: anualizar el funding con el `funding_interval_hours` de cada fila.
- **FR-005**: deduplicar por clave y fallar si hay duplicados en conflicto.
- **FR-006**: checks que fallan la construcción: clave única, sin nulos, OHLC coherente, precios > 0,
  volumen ≥ 0, timestamps alineados al intervalo y `knowledge_time ≥ event_time`.
- **FR-007**: informe de calidad en JSON por tabla: filas, duplicados eliminados, huecos (número,
  mayor, lista) y resultado de cada check.
- **FR-008**: los outliers reales (p. ej. un flash crash) **no se eliminan**: se marcan con
  `is_outlier` cuando el retorno logarítmico de 1 h supera 10 desviaciones típicas móviles
  (ventana de 30 días).
- **FR-009**: esquemas declarativos con **pandera** para velas y funding (tipos, rangos, UTC).
- **FR-010**: join *as-of* sobre `knowledge_time`, con un test que falla si una fila de la
  derecha posterior a t llega a la izquierda.
- **FR-011**: el informe de calidad incluye estadística descriptiva por variable (cap. 4.2):
  n, media, desviación típica, mínimo, p25, mediana, p75 y máximo.
- **FR-012**: CLI `pq silver build --symbol S` idempotente: reconstruye desde bronze.

### Entidades clave

- **Vela silver**: mercado, símbolo, intervalo, apertura y cierre (UTC), OHLCV, volumen en quote,
  trades, volumen taker, `event_time`, `knowledge_time` y archivo de origen.
- **Funding silver**: símbolo, `funding_time`, `calc_time` original, intervalo, tasa, tasa
  anualizada, `knowledge_time` y archivo de origen.

## Criterios de éxito

- **SC-001**: el silver de los 5 símbolos se construye sin fallos en menos de 1 minuto en la laptop.
- **SC-002**: 0 diferencias de escala entre spot y perp después de 2025-01-01.
- **SC-003**: cada hallazgo 1–5 de la auditoría tiene un test que lo cubre.
- **SC-004**: cobertura de tests ≥ 80 % y contratos de arquitectura en verde.

## Supuestos

- Bronze ya contiene los archivos (PQ-20). Silver no descarga nada.
- Basta un Parquet por (mercado, intervalo, símbolo): ≈ 60 000 filas de 1 h por símbolo.
- Los huecos del perp de SOL y XRP en 2022 se documentan; contrastarlos con los archivos diarios
  queda para un ticket aparte (descargar los diarios es otra fuente).
