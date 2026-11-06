# Especificación: capa gold y modelo en estrella para BI

- **Ticket:** PQ-46 (5 puntos) · **Rama:** `feature/PQ-46-capa-gold` · **Fecha:** 2026-11-06 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** historia PQ-46 en Jira; ítem 7.1 del Proyecto Integrador («Data Warehouse o modelo
  tabular automatizado… trazabilidad del dato crudo hasta la tabla de hechos»); [ADR-0003](../../docs/adr/0003-lakehouse-parquet-duckdb.md)

## Escenarios de usuario y pruebas

### Historia 1: un analista de BI arma el dashboard sin tocar el código de research (P1)

Como analista de BI, quiero tablas de hechos y dimensiones con claves simples para conectarlas en
Power BI (PQ-47) y construir las medidas sin entender la plataforma por dentro.

**Prueba independiente:** con el lakehouse real, `uv run pq gold build` produce las tablas, y cada
hecho se puede unir a sus dimensiones por una sola columna.

**Escenarios de aceptación**

1. **Dado** silver y los artefactos de research, **cuando** se ejecuta `pq gold build`, **entonces**
   se escriben `data/gold/<tabla>.parquet`, `data/gold/gold.duckdb` y `data/gold/export/<tabla>.csv`.
2. **Dado** cualquier hecho, **cuando** se une a sus dimensiones, **entonces** no hay filas
   huérfanas (integridad referencial) ni claves duplicadas.
3. **Dada** la exportación, **cuando** el analista abre `export/DICCIONARIO.md`, **entonces**
   encuentra el grano, las claves, el origen y la descripción de cada columna.

### Historia 2: trazabilidad del dato crudo a la tabla de hechos (P1)

Como jurado del ítem 7.1, quiero ver de dónde sale cada número para auditar el modelo.

**Escenarios de aceptación**

1. **Dada** una tabla gold, **cuando** se consulta el diccionario, **entonces** declara sus fuentes
   (tablas silver o artefactos de research), y estas, a su vez, su linaje hasta bronze.
2. **Dado** el código, **cuando** cambia una tabla, **entonces** la página de documentación
   generada lo refleja, y un test falla si quedó desactualizada.

### Historia 3: el holdout sigue cerrado (P1)

**Escenarios de aceptación**

1. **Dados** datos silver hasta 2026-09-30, **cuando** se construye gold, **entonces** ningún hecho
   con fecha pasa del 2024-06-29. Ese es el último día cuyo devengo (hasta la liquidación y la
   valoración de las 00:00 del día siguiente) no toca el holdout, que empieza el 2024-07-01
   (pre-registro §7, KE-014).
2. **Dado** el retorno diario valorado a las 00:00 del día siguiente (enmienda 1.3), **cuando** se
   pasa a gold, **entonces** su `fecha` es el día al que corresponde el retorno.

### Casos límite

- Falta un artefacto de research: su hecho queda vacío con el esquema declarado y el informe lo
  lista. El resto se construye igual.
- Un JSON corrupto se trata como faltante.
- Una métrica que no aplica a un modelo (AUC en regresión) queda nula, no en cero.

## Requisitos

- **FR-001** Un único comando, `pq gold build`, reconstruye toda la capa de forma idempotente.
- **FR-002** Cada tabla declara en código su tipo (dimensión o hecho), su grano, su clave, sus
  fuentes y la descripción de cada columna. El esquema producido debe coincidir con el declarado.
- **FR-003** Las claves de las dimensiones son de una sola columna y únicas. Las claves de los
  hechos son únicas.
- **FR-004** Todo valor de una clave foránea existe en su dimensión.
- **FR-005** Los hechos con fecha terminan el último día cuyo devengo no toca el holdout. La
  fecha del funding es la de su devengo, igual que la de los retornos. La constante vive en
  `domain`, y research y gold usan la misma.
- **FR-006** Salidas: Parquet (fuente de verdad), DuckDB (consultas SQL) y CSV UTF-8 con
  diccionario (Power BI).
- **FR-007** `pq gold docs` genera la página del modelo en la documentación desde las mismas
  declaraciones.

## Criterios de éxito

- Con el lakehouse real: 13 tablas, 0 huérfanos, 0 claves duplicadas, 0 filas después del 2024-06-29.
- Cobertura de tests ≥ 80 % y los contratos de arquitectura intactos.
