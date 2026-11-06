# Orquestación del lakehouse con Dagster

**Cuándo aplica:** para actualizar bronze → silver → gold sin escribir comandos, ver el linaje y
los resultados de calidad, o activar la actualización diaria (PQ-22, [ADR-0010](../adr/0010-dagster-para-orquestar-el-lakehouse.md)).

**El trading en vivo no depende de esto.** Si Dagster falla, el paper trading sigue. Un contrato
de import-linter lo garantiza.

## Abrir la interfaz

```bash
make orquestador    # http://127.0.0.1:3000 (solo en la máquina local)
```

- Consume unos 790 MB de RAM en reposo. En la laptop, ciérrala con Ctrl+C cuando termines.
- El estado de Dagster (ejecuciones e historial) se guarda en `data/.dagster/`, que no se versiona.

## Qué hay

| Asset | Qué hace | Partición |
|---|---|---|
| `bronze` | Descarga de Data Vision las velas spot, las del perpetuo y el funding de un mes | mes × símbolo |
| `silver` | Reconstruye las tablas validadas de los 5 símbolos | completa |
| `gold` | Reconstruye el modelo en estrella para BI | completa |
| `research/*` | **Solo linaje.** No se pueden materializar desde aquí | — |

Los assets de research no se ejecutan desde Dagster porque **cada ejecución suma ensayos a N**
(Deflated Sharpe). Se corren a mano con `uv run pq research …`, con su commit y su motivo.

## Checks de calidad

| Check | Asset | Si falla |
|---|---|---|
| `silver_tablas_y_claves` | silver | **Bloquea**: falta una tabla o hay claves temporales repetidas |
| `silver_huecos` | silver | Advertencia: hay huecos (se informan, no se imputan; KE-007) |
| `gold_holdout_cerrado` | gold | **Bloquea**: un hecho pasa del 2024-06-29 |
| `gold_integridad` | gold | **Bloquea**: esquema, claves o integridad referencial |

## Actualizar a mano

En **Assets**:
- Para bronze: elige `bronze` → **Materialize** → el mes y los símbolos.
- Para el resto: selecciona `silver` y `gold` → **Materialize selected**.

## Activar la actualización diaria

En **Automation**:
- Activa `bronze_diario` (06:00 UTC): reintenta el último mes completo de cada símbolo.
- Activa `silver_y_gold_diario` (06:30 UTC): reconstruye silver y gold.

Los dos arrancan **detenidos**. Mientras no esté PQ-65, el mes en curso no entra: Data Vision publica
cada mes cuando termina.

## Verificar que funcionó

- **Runs:** la ejecución termina en verde y los checks aparecen en la pestaña **Checks** de cada asset.
- Desde la terminal, `uv run pq gold build` debe dar los mismos conteos que muestra la metadata de `gold`.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `bronze` falla con «archivos rechazados» | Revisar `data/bronze/_rejections.jsonl`: es un checksum inválido de la fuente; reintentar más tarde |
| `silver` falla con el nombre de un check | Es un problema real de datos: ver el mensaje y la [KEDB](errores-conocidos.md) antes de tocar nada |
| `gold_holdout_cerrado` falla | **No forzar.** Algo dejó pasar datos del holdout: abrir un incidente |
| La interfaz no abre | `make orquestador` muestra el error; comprobar que el puerto 3000 esté libre |
