# scripts/: utilidades de desarrollo y mantenimiento

Tareas puntuales que **no forman parte del producto**: preparar un entorno, migrar datos una vez,
generar un informe ad hoc o automatizar algo del repositorio.

## Reglas

- La funcionalidad del sistema (ingesta, backtests, ejecución) **no** va aquí: va en
  `src/prometheus_platform/` y se expone con la CLI `pq` (`prometheus_platform.api`).
- Cada script empieza con un docstring o comentario que dice qué hace, cómo se ejecuta y si
  modifica algo.
- Se ejecutan dentro del entorno del proyecto: `uv run python scripts/<script>.py` o
  `bash scripts/<script>.sh`.
- Idempotentes cuando sea posible: ejecutarlos dos veces no debe romper nada.
- Sin secretos ni rutas absolutas de una máquina concreta.

## Scripts disponibles

| Script | Qué hace |
|---|---|
| `audit_data_vision.py` | Auditoría de las fuentes de Binance Data Vision (spike PQ-19) |
| `comisiones_binance.py` | Lee de la cuenta real el nivel VIP, los productos habilitados y las comisiones de spot y USDⓈ-M con una clave de **solo lectura** (se niega si tiene más permisos); no opera ni guarda nada (PQ-17) |
| `capture_dashboard.py` | Captura cada pestaña del dashboard en PNG con Playwright para el informe y la presentación (PQ-41) |
| `export_sessions.py` | Exporta las sesiones de Claude Code a Markdown para NotebookLM, con secretos enmascarados; la salida (`notebooklm/`) queda fuera de git (PQ-40) |
| `spike_polymarket.py` | Mide qué datos históricos dan las API públicas de Polymarket: mercados cerrados por mes, historial de precios en una muestra y coherencia con la resolución; no guarda series ni usa credenciales (spike PQ-78) |
| `verificar_universo_polymarket.py` | Comprueba con dos consultas a Gamma que el catálogo «cerrado al ingerir» no deja fuera mercados anteriores al corte de evaluación (enmienda 1 de PQ-87, PQ-93) |
| `verificar_punto_diario.py` | Comprueba en una muestra estratificada que el punto diario del CLOB de Polymarket es el precio de ese instante y no uno posterior (enmienda 1 de PQ-87, PQ-93) |
| `spike_sentimiento.py` | Mide si el Crypto Fear & Greed Index es point-in-time: historia y huecos de la API de alternative.me, y comparación con las copias de la Wayback Machine para detectar revisiones y el retraso de publicación (spike PQ-103) |
| `pdca_regimen_funding.py` | Describe el funding anualizado de los cinco símbolos del carry por semestre: mediana y parte por encima de θ = 20 % y por debajo de 0. Es el diagnóstico del ciclo PDCA tras el drift; no es un ensayo (PQ-123) |
| `powerbi.py` | Genera las consultas de Power Query del modelo gold y calcula los valores de control del dashboard de Power BI (PQ-47) |
