# Especificación: orquestación del lakehouse con Dagster

- **Ticket:** PQ-22 (5 puntos) · **Rama:** `feature/PQ-22-dagster` · **Fecha:** 2026-11-06 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** historia PQ-22 en Jira; [ADR-0003](../../docs/adr/0003-lakehouse-parquet-duckdb.md)

## Escenarios de usuario y pruebas

### Historia 1: la actualización diaria corre sola y deja rastro (P1)

Como operador, quiero que bronze → silver → gold se actualice sin escribir comandos y que el linaje
y la calidad queden visibles.

**Escenarios de aceptación**

1. **Dado** el schedule activado, **cuando** llega su hora, **entonces** se ingesta el último mes
   completo de cada símbolo y después se reconstruyen silver y gold.
2. **Dado** un check bloqueante que falla en silver, **cuando** corre el job, **entonces** gold no
   se reconstruye en esa ejecución y la interfaz muestra el check en rojo.
3. **Dados** huecos conocidos en silver (KE-007), **cuando** corre el job, **entonces** se ven como
   advertencia y no bloquean.

### Historia 2: research no se ejecuta por accidente (P1)

**Escenarios de aceptación**

1. **Dados** los artefactos de research, **cuando** se abre la interfaz, **entonces** aparecen en el
   linaje pero no se pueden materializar, y ningún schedule los incluye.

### Historia 3: el trading en vivo no depende de Dagster (P1)

**Escenarios de aceptación**

1. **Dado** cualquier módulo fuera de `api.orquestacion`, **cuando** importa `dagster`,
   **entonces** import-linter rompe la CI.

## Requisitos

- **FR-001** `bronze` particionado por mes × símbolo; `silver` y `gold` completos (sus checks
  necesitan la historia entera).
- **FR-002** Checks bloqueantes de silver (tablas y claves) y de gold (holdout e integridad);
  advertencia por huecos.
- **FR-003** Schedules diarios, detenidos por defecto.
- **FR-004** `make orquestador` abre la interfaz solo en 127.0.0.1.
- **FR-005** Dagster en un grupo de dependencias propio; la librería y la imagen Docker no lo instalan.

## Fuera de alcance

- **DuckLake.** Se difiere (ADR-0010): `gold.duckdb` ya da SQL sobre gold.
- **Mes en curso desde la API REST.** Llega con PQ-65 (TODO en el asset `bronze`).
