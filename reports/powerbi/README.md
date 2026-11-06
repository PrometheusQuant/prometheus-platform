# reports/powerbi/: dashboard de negocio en Power BI (PQ-47, cap. 7.2)

**La guía paso a paso está en la documentación:**
[`docs/academico/dashboard-power-bi.md`](../../docs/academico/dashboard-power-bi.md). Allí se
publica en el sitio y `mkdocs --strict` comprueba sus enlaces. Esta carpeta guarda los artefactos.

| Archivo | Qué es | Quién lo produce |
|---|---|---|
| `consultas.pq` | Consultas de Power Query (M), una por tabla gold, tipadas con `en-US` | Generado: `uv run python scripts/powerbi.py consultas` |
| `medidas.dax` | Medidas DAX comentadas (rendimiento, riesgo, calidad, modelo) | A mano, con las fórmulas de `research/validation.py` |
| `tema-prometheusquant.json` | Tema del informe (paleta Okabe-Ito, accesible) | A mano |
| `prometheusquant.pbix` | El informe | Se arma en Power BI Desktop (Windows) siguiendo la guía |
| `prometheusquant.pdf`, `capturas/` | Exportación para el informe y la presentación | Power BI Desktop |

Valores de control para verificar el `.pbix`: `uv run python scripts/powerbi.py control`.
