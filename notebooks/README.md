# notebooks/: exploración e investigación

Análisis exploratorio, spikes y prototipos. **El código que se reutiliza no vive aquí**: en cuanto
una función se usa dos veces, se mueve a `src/prometheus_platform/` con sus tests.

## Convenciones

- Nombre: `<ticket>-<iniciales>-<tema>.ipynb`, p. ej. `PQ-19-dq-auditoria-data-vision.ipynb`.
  El ticket enlaza el notebook con la hipótesis y la decisión que produjo.
- Organizados por épica o estrategia cuando crezcan: `notebooks/datos/`, `notebooks/carry/`, …
- Las **salidas se eliminan antes de cada commit** (hook `nbstripout`): evita subir datos, tokens o
  imágenes pesadas, y deja diffs legibles.
- Los datos se leen del lakehouse (`data/`) a través de `prometheus_platform`, nunca de rutas
  absolutas de una máquina.
- Un notebook de investigación de estrategia **no** puede abrir el holdout final; eso solo lo hace
  `final_eval` (ver [ADR-0004](../docs/adr/0004-crisp-mlq-con-protocolo-financiero.md)).
- Las conclusiones se pasan al ticket o a `docs/`; el notebook es evidencia, no el entregable.
