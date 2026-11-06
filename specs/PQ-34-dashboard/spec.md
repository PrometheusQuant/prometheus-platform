# Especificación: dashboard de investigación (Streamlit + Docker)

- **Ticket:** PQ-34 (8 puntos) · **Rama:** `feat/PQ-34-dashboard-streamlit` · **Fecha:** 2026-11-05 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** historia PQ-34 en Jira; capítulo 7.2–7.3 del informe; [ADR-0009](../../docs/adr/0009-streamlit-y-docker-para-el-dashboard.md)

## Escenarios de usuario y pruebas

### Historia 1: entender los resultados sin leer código (P1)

Como jurado o stakeholder no técnico, quiero un panel con los resultados (datos, carry, modelo y
simulación) para entender el producto sin leer código.

**Prueba independiente:** con los artefactos reales de `data/`, abrir el panel y recorrer las 4
pestañas sin errores.

**Escenarios de aceptación**

1. **Dado** el lakehouse con los artefactos generados, **cuando** se abre el panel, **entonces**
   hay 4 pestañas en orden de storytelling: ¿qué pasó?, ¿funciona?, ¿qué predice? y ¿qué riesgo hay?
2. **Dada** la evaluación de H2, **cuando** se abre «¿Funciona?», **entonces** se ven la configuración
   elegida por CPCV, el PBO, el Deflated Sharpe, los gates G1 a G4 y la curva de capital.
3. **Dada** la simulación, **cuando** se abre «¿Qué riesgo hay?», **entonces** se ven la matriz de
   transición, la validación contra la historia, los escenarios y la probabilidad de quiebra de equilibrio.

### Historia 2: el panel nunca se rompe por un artefacto faltante (P1)

**Escenarios de aceptación**

1. **Dado** un lakehouse vacío, **cuando** se abre el panel, **entonces** cada pestaña explica qué
   falta y con qué comando `pq` se genera, sin excepciones.
2. **Dado** un JSON corrupto, **cuando** se carga, **entonces** se ignora y el resto se muestra.
3. **Dada** una métrica NaN, **cuando** se muestra, **entonces** la celda queda vacía.

### Historia 3: misma app en local y en Docker, sin poder dañar los datos (P2)

**Escenarios de aceptación**

1. **Dado** el repo, **cuando** se ejecuta `make dashboard`, **entonces** la app abre en `:8501`.
2. **Dado** Docker, **cuando** se ejecuta `docker compose up --build`, **entonces** la misma app
   abre en `127.0.0.1:8501`, con `data/` montado en solo lectura y el sistema de archivos del
   contenedor también en solo lectura.

### Casos límite

- Hay summary de carry pero falta `daily_returns.parquet`: se muestran las tablas sin la curva.
- La configuración seleccionada no está entre las columnas de retornos: no hay curva y no hay error.
- El holdout: el panel nunca lo muestra, porque los artefactos terminan antes de 2024-07-01.

## Requisitos

- **FR-001:** el panel solo **lee** artefactos; no entrena, no descarga y no escribe (SRP).
- **FR-002:** la lectura de artefactos vive en un módulo sin Streamlit, para poder testearla.
- **FR-003:** cada artefacto faltante se informa con el comando que lo genera.
- **FR-004:** la imagen Docker corre sin root, con el root filesystem en solo lectura y sin capacidades.
- **FR-005:** el puerto se publica solo en `127.0.0.1`.

## Criterios de éxito

- **SC-001:** 0 excepciones con los artefactos reales y con el lakehouse vacío (tests con `AppTest`).
- **SC-002:** la CI construye la imagen y su `/_stcore/health` responde en menos de 60 s.
- **SC-003:** la cobertura total se mantiene ≥ 80 %.
