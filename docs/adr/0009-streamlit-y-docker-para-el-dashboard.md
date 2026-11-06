# ADR-0009: Streamlit y Docker para el dashboard de investigación

- **Estado:** Aceptada
- **Fecha:** 2026-11-05
- **Ticket:** PQ-34

## Contexto y problema

El capítulo 7 pide un producto de datos que un jurado no técnico pueda recorrer. Los resultados
existen como JSON y Parquet en `data/research/` y `data/silver/_quality/`, pero solo se leen con
código o en los informes de MkDocs.

## Opciones consideradas

| Opción | A favor | En contra |
|---|---|---|
| **Streamlit** | Python puro: reutiliza polars y los artefactos tal cual; `AppTest` permite testearlo en la CI | Una dependencia grande; interactividad limitada |
| Power BI Desktop | Conocido por el jurado | Solo Windows; no se versiona bien; no corre en la CI |
| Dash / Plotly | Más control | Más código para el mismo resultado |
| Solo MkDocs | Ya existe | Estático: no hay navegación por los resultados |

## Decisión

**Streamlit, empaquetado con Docker.** Lo tomamos de OmniVoC, donde funcionó bien para la
presentación; nos quedamos con su forma de empaquetar y descartamos sus Singletons.

- El panel **solo lee** artefactos (SRP): calcular es tarea de `pq research …`.
- La lectura (`artifacts.py`) no depende de Streamlit; la presentación (`app.py`) es delgada.
- Docker con el lakehouse montado en solo lectura, usuario sin root, root filesystem de solo
  lectura y puerto en `127.0.0.1`.

## Consecuencias

- Hay `make dashboard` en local y `docker compose up --build` en cualquier máquina.
- La CI construye la imagen y comprueba su health check en cada PR.
- Si más adelante hace falta un dashboard **operativo** (posiciones en vivo), irá a Grafana con
  Prometheus (fase 1 de infraestructura), no aquí.
