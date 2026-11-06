# Dashboard de investigación

Panel de **solo lectura** con los resultados: calidad de los datos, carry y gates, modelo del
funding y simulación. Decisión en [ADR-0009](../adr/0009-streamlit-y-docker-para-el-dashboard.md).

## Abrirlo

**En local:**

```bash
make dashboard          # http://localhost:8501
```

**Con Docker** (requiere Docker Desktop con la integración WSL activada, ver KE-008):

```bash
docker compose up --build    # http://127.0.0.1:8501
docker compose down
```

## Qué muestra

| Pestaña | Pregunta que responde | Artefacto | Se genera con |
|---|---|---|---|
| ¿Qué pasó? | ¿Los datos son confiables? | `data/silver/_quality/*.json` | `uv run pq silver build --symbol <S>` |
| ¿Funciona? | ¿El carry pasa los gates? | `data/research/carry/H*/` | `uv run pq research carry --hypothesis H2 --figures <dir>` |
| ¿Qué predice? | ¿Se puede anticipar el funding? | `data/research/funding_model/summary.json` | `uv run pq research funding-model --figures <dir>` |
| ¿Qué riesgo hay? | ¿Qué puede salir mal? | `data/research/simulation/summary.json` | `uv run pq research simulate --figures <dir>` |

Si falta un artefacto, la pestaña muestra el comando que lo genera.

## Seguridad del contenedor

- `data/` se monta con `:ro`: el panel no puede modificar el lakehouse.
- Root filesystem en solo lectura, usuario `pq` (uid 10001), sin capacidades (`cap_drop: ALL`).
- Puerto publicado solo en `127.0.0.1`: no queda expuesto a la red.
- La imagen no contiene `.env` ni datos (`.dockerignore`).
