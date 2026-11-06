# Dashboard de investigación

Panel de **solo lectura** con los resultados: calidad de los datos, carry y gates, modelo del
funding y simulación. Decisión en [ADR-0009](../adr/0009-streamlit-y-docker-para-el-dashboard.md).

## Abrirlo

**En local:**

```bash
make dashboard          # http://localhost:8501
```

**Con Docker** (Docker Desktop abierto y con la integración WSL, ver KE-008):

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
| ¿Y si invierto? | ¿Qué me pasaría con mi capital? | Silver de H2 (desarrollo): Monte Carlo del cap. 6 con tu capital, horizonte y riesgo de quiebra; θ solo pre-registrado | `uv run pq silver build --symbol <S>` |
| ¿Qué predice hoy? | ¿Habrá funding alto en la próxima liquidación? | Clasificador del cap. 5 entrenado con el desarrollo; predice solo con datos **posteriores** al holdout | `uv run pq ingest --source api ...` + `pq silver build` |

Si falta un artefacto, la pestaña muestra el comando que lo genera.

## Seguridad del contenedor

- `data/` se monta con `:ro`: el panel no puede modificar el lakehouse.
- Root filesystem en solo lectura, usuario `pq` (uid 10001), sin capacidades (`cap_drop: ALL`).
- Puerto publicado solo en `127.0.0.1`: no queda expuesto a la red.
- La imagen no contiene `.env` ni datos (`.dockerignore`).

## Pruebas en navegador y capturas (PQ-41)

[Playwright](https://playwright.dev/python/) abre el dashboard en un Chromium sin ventana, como lo vería
un usuario. Complementa las pruebas de `AppTest` (que ejecutan el script sin navegador) y comprueba lo
que ellas no ven: que el contenedor sirve la página, que las 4 pestañas se pueden abrir y que ninguna
muestra un error.

```bash
make e2e            # levanta el contenedor, instala Chromium la primera vez y corre tests/e2e/
make screenshots    # una imagen PNG por pestaña en reports/storytelling/_img/dashboard/
```

- Las pruebas aceptan datos reales o un lakehouse vacío: cada pestaña debe mostrar una tabla o el aviso
  con el comando que genera el artefacto.
- En la CI corren en el job *Imagen Docker del dashboard*, contra el contenedor recién construido.
- Las capturas sirven para el informe y la presentación; quedan fuera de git porque se regeneran.
- El grupo de dependencias `e2e` no se instala por defecto: `uv sync --group e2e`.
