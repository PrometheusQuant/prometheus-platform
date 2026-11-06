# Plan de implementación: dashboard de investigación

- **Ticket:** PQ-34 · **Fecha:** 2026-11-05 · **Spec:** [spec.md](spec.md)

## Contexto técnico

| | |
|---|---|
| Dependencia nueva | `streamlit` en el grupo `dashboard` del `pyproject.toml` (no es dependencia de la librería) |
| Ubicación | `api/dashboard/`: es un punto de entrada, como la CLI (capa `api` de import-linter) |
| Pruebas | `artifacts.py` con JSON sintéticos; la app completa con `streamlit.testing.v1.AppTest` |
| Empaquetado | `Dockerfile` de dos etapas con uv 0.13.6 (la misma versión que la CI) |

## Verificación contra la "constitución"

| Regla | Cumplimiento |
|---|---|
| ADR-0001 (hexagonal) | El panel está en `api/`; no lo importa ninguna capa inferior |
| Holdout cerrado | Solo lee artefactos del periodo de desarrollo |
| Seguridad (SECURITY.md) | Sin secretos en la imagen (`.dockerignore` excluye `.env`); usuario sin root; `read_only`; `cap_drop: ALL`; puerto en loopback |
| DoD | Tests, tipos, lint y documentación (runbook y ADR-0009) |

## Estructura

```
src/prometheus_platform/api/dashboard/
├── artifacts.py   # carga y tablas (polars), sin Streamlit
└── app.py         # 4 pestañas; solo presentación
Dockerfile · docker-compose.yml · .dockerignore
tests/unit/api/test_dashboard.py
```

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Docker sin integración WSL en la máquina de desarrollo (KE-008) | La CI construye la imagen y la prueba en cada PR |
| Streamlit agrega muchas dependencias | Grupo aparte; `make audit` las audita igual |
