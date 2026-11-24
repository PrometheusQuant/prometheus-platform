# Observabilidad: métricas, logs, SLO y verificación externa (PQ-71, PQ-97)

El runner del paper trading publica sus métricas en `/metrics`. Prometheus las guarda 15 días,
Grafana las muestra en un tablero versionado y Alertmanager reenvía las alertas al mismo grupo de
Telegram que el resto de la plataforma ([alertas](alertas.md)).

Todo escucha **solo en 127.0.0.1**: en la VM no se abre ningún puerto, y se llega por túnel SSH.

```text
pq paper run --metrics-port 9108 ──/metrics──▶ Prometheus :9090 ──▶ Alertmanager :9093 ──▶ Telegram
                                                    │
                                                    └──▶ Grafana :3000 (tablero «Paper trading»)
```

## Arrancar

1. El runner con métricas (en el servidor, el mismo comando del runbook de
   [paper trading](paper-trading.md), con el puerto):

    ```bash
    uv run pq paper run --interval 60 --metrics-port 9108
    curl -s 127.0.0.1:9108/metrics | grep pq_paper_equity_usd     # comprobación
    ```

2. La pila de observabilidad, con el perfil `observability` de docker compose. Lee del `.env`:

    - `PQ_TELEGRAM_BOT_TOKEN` y `PQ_TELEGRAM_CHAT_ID`;
    - `PQ_GRAFANA_ADMIN_PASSWORD`;
    - `PQ_LOG_DIR`: carpeta de los logs, por defecto `./data/logs`.

    Nombra los servicios: el `dashboard` no tiene perfil y, sin nombres, `up` lo levanta también.

    ```bash
    docker compose --profile observability up -d prometheus alertmanager grafana loki alloy
    docker compose --profile observability ps
    ```

    Sin `PQ_GRAFANA_ADMIN_PASSWORD`, Grafana genera una contraseña al azar en su primer arranque
    y no la muestra: nunca queda el `admin/admin` de fábrica. Para fijarla después:
    `docker compose exec grafana grafana cli admin reset-admin-password '<nueva>'`.

3. Desde tu computadora, el túnel (deja la terminal abierta):

    ```bash
    ssh -N -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 usuario@IP_DE_LA_VM
    ```

    Abre <http://127.0.0.1:3000> (Grafana) o <http://127.0.0.1:9090/alerts> (reglas de Prometheus).

Cada proceso de la plataforma escribe sus logs JSON en `$PQ_LOG_DIR/<proceso>.log`, y Alloy los
lee de ahí:

```bash
uv run pq paper run --interval 60 --metrics-port 9108 >> "$PQ_LOG_DIR/runner.log" 2>&1
uv run pq paper watchdog --interval 120 >> "$PQ_LOG_DIR/watchdog.log" 2>&1
```

## Métricas

Las calcula `api/paper/metrics.py` con las mismas funciones que el dashboard y los resúmenes de
Telegram, así que las cifras son las mismas. La vista del diario se reconstruye solo cuando el
archivo cambia.

| Métrica | Qué es |
|---|---|
| `pq_paper_equity_usd`, `pq_paper_pnl_usd`, `pq_paper_drawdown_ratio` | Equity, PnL desde la primera valoración y caída desde el máximo |
| `pq_paper_exposure_usd{instrument,symbol,leg}` | Nocional abierto por pata, a la última marca |
| `pq_paper_hedge_imbalance_ratio{symbol}` | Desbalance de la cobertura spot/perp (`hedge_imbalances`) |
| `pq_paper_funding_usd` | Funding neto acumulado (gauge: también se paga) |
| `pq_paper_costs_usd_total` | Comisiones más slippage |
| `pq_paper_orders_filled_total`, `pq_paper_order_latency_seconds` | Órdenes ejecutadas y latencia de la orden a su fill |
| `pq_paper_risk_rejections_total{rule}` | Órdenes rechazadas por el riesgo pre-trade |
| `pq_paper_heartbeat_timestamp_seconds`, `pq_paper_heartbeat_ok` | Último heartbeat y si el ciclo terminó bien |
| `pq_paper_kill_switch_active` | 1 si la bandera global del kill-switch existe |

## Alertas

Las reglas están en `deploy/observability/alertas.yml`, con los mismos umbrales del runner y el
vigilante (`ops/settings.py`): si cambian allí, cambian allí también.

| Alerta | Condición | Severidad |
|---|---|---|
| `RunnerSinMetricas` | Prometheus no lee `/metrics` durante 5 min | critical |
| `HeartbeatViejo` | Heartbeat con más de 10 min | critical |
| `CicloConFallos` | Último ciclo con fallos durante 10 min | warning |
| `KillSwitchActivo` | Bandera global activada | critical |
| `CoberturaDesbalanceada` | Desbalance > 15 % durante 15 min | critical |
| `DrawdownAlto` | Caída > 3 % desde el máximo | warning |
| `RechazosDeRiesgo` | Algún rechazo pre-trade en la última hora | warning |

Repiten avisos del runner y del vigilante (PQ-55) a propósito. Alertmanager es un **segundo
camino independiente**: si el proceso del runner y el del vigilante caen juntos, sigue avisando
`RunnerSinMetricas`.

El token de Telegram no se escribe en el repo ni en el disco. `alertmanager-arrancar.sh` completa
la plantilla `alertmanager.yml.tmpl` al arrancar y deja el resultado en `/tmp`, que es memoria
(tmpfs). El contenedor recibe solo las dos variables de Telegram, no el `.env` entero.

## Logs centralizados (Loki, PQ-97)

**Grafana Alloy** lee los `.log` de `PQ_LOG_DIR` y los manda a **Loki**, que los guarda 15 días.

- **Por qué Alloy:** el ticket pedía Promtail, pero Grafana lo declaró obsoleto y lo reemplazó
  por Alloy, que hace lo mismo.
- **Etiquetas:** de cada línea JSON de structlog salen `level` y `component`. Las líneas que no
  son JSON (un `print`, un traceback) se guardan igual, sin esas etiquetas.
- **Sin secretos:** los logs ya salen limpios de los procesos, porque structlog los pasa por
  `redact_text` (`ops/logging.py`, KE-017). Alloy no ve nada que no esté en el archivo.

En Grafana → *Explore* → fuente **Loki**:

```text
{job="prometheusquant", level=~"warning|error|critical"}       # lo que merece mirarse
{job="prometheusquant", component="paper_runner"} |= "order"     # órdenes del runner
{job="prometheusquant"} | json | event="paper_order_rejected"    # rechazos del riesgo
```

El tablero trae un panel con las líneas `warning`, `error` y `critical` de todos los procesos.

## SLO de disponibilidad (PQ-97)

| Objetivo | Medida | Margen de error |
|---|---|---|
| **Heartbeat sano el 99 % de la semana** | Minutos con heartbeat fresco (< 10 min) **y** runner leído por Prometheus, sobre los últimos 7 días | 1 % ≈ 1 h 41 min por semana |

- Lo calculan dos reglas de registro de `alertas.yml`:
  - `pq:heartbeat_ok:bool` vale 1 o 0 en cada evaluación;
  - `pq:slo_heartbeat:ratio_7d` es su media en 7 días.
- Un minuto en que Prometheus no puede leer al runner cuenta como caído, no se ignora (verificado
  deteniendo las métricas).
- La alerta `SLOHeartbeatIncumplido` avisa si la media de 7 días baja del 99 %.
- El panel «Disponibilidad 7 días» del tablero muestra el valor en verde o en rojo.

**Qué no mide:** si la VM entera cae, Prometheus también cae y no mide nada. Eso lo cubre la
verificación externa.

## Verificación externa (Healthchecks.io, PQ-97)

Es la única alerta que no depende de la VM. Funciona como un *dead man's switch*:

1. El vigilante (`pq paper watchdog`) llama a `PQ_HEALTHCHECK_URL` en cada revisión, cada 1 o
   2 min:
   - a la URL tal cual, si el runner está sano;
   - a `<URL>/fail`, si no lo está.
2. Si los pings **dejan de llegar** (VM apagada, sin red, Docker caído o el vigilante muerto),
   Healthchecks.io avisa al grupo de Telegram tras el periodo de gracia.
3. Un `/fail` avisa al momento: el runner existe pero está enfermo.

La VM no abre ningún puerto: los pings salen de ella. El plan gratuito de Healthchecks.io alcanza
(20 verificaciones). La URL es un secreto, porque con ella cualquiera podría fingir que la VM vive:
va solo en el `.env` y el código nunca la escribe en logs.

La cuenta y la integración con Telegram las crea el titular:
[paso 9 de la guía](../compliance/pasos-del-titular.md#paso-9-verificacion-externa-de-disponibilidad-pq-97).

## El tablero

`deploy/observability/grafana/dashboards/paper-trading.json` se carga solo al arrancar Grafana
(*provisioning*) y no se puede editar desde la interfaz. Se cambia en el JSON, con su PR.
Paneles:

- **Estado:** equity, PnL, caída, antigüedad del heartbeat, kill-switch y último ciclo.
- **Curvas:** equity, funding y costes, exposición por pata y desbalance de la cobertura.
- **Órdenes:** latencia p50/p95 y órdenes ejecutadas y rechazadas por hora.
- **Disponibilidad y logs (PQ-97):** el SLO de 7 días y los logs de advertencia y error.

## Memoria

Cada contenedor tiene su límite (`mem_limit`) para no competir con el runner en la VM gratuita:

| Servicio | Límite |
|---|---|
| Prometheus | 256 MB, retención 15 días o 1 GB en disco |
| Grafana | 192 MB |
| Alertmanager | 64 MB |
| Loki | 256 MB, retención 15 días |
| Alloy | 128 MB |

Lo medido está en la [verificación](#verificacion-de-la-pila).

## Verificación de la pila

Prueba del 23-nov-2026 en la laptop (Docker 28.5.1), con el diario real del paper:

| Comprobación | Resultado |
|---|---|
| `promtool check rules` y `check config` | 7 reglas, configuración válida |
| `amtool check-config` | 1 receptor (Telegram), válido |
| Prometheus lee `/metrics` del runner | `up{job="pq-runner"} = 1`; `pq_paper_equity_usd = 1000`, la misma cifra del dashboard |
| Reglas | Las 7 con `health = ok` e inactivas (paper sano) |
| Grafana | Tablero «PrometheusQuant · Paper trading» con 12 paneles; la fuente de datos responde; `admin/admin` da 401 |
| Camino de alerta | Exportador detenido a las 18:38:52 UTC. `RunnerSinMetricas` llega a Alertmanager a las 18:44:53 (5 min de `for` más un ciclo) y se intenta enviar a Telegram (rechazado: token falso a propósito) |
| Memoria (`docker stats`) | Prometheus 27 MB, Alertmanager 32 MB, Grafana 104 MB: **≈ 162 MB**, dentro de sus límites (256/64/192 MB) y de los 6 GB de la VM A1 |

En producción, el *collector* corre dentro del proceso del runner: no suma otro proceso de Python.

En la laptop, `network_mode: host` de Docker Desktop no ve el `127.0.0.1` de WSL
([KE-020](errores-conocidos.md#ke-020-en-docker-desktop-la-red-del-host-no-es-la-de-wsl)). Para
repetir la prueba allí:

- el exportador corre en un contenedor con `--network host` y la imagen del proyecto;
- las consultas se hacen con `docker exec <contenedor de prometheus> wget -qO- 127.0.0.1:9090/...`.

En la VM Linux del servidor no hace falta nada de eso.

### Con Loki, Alloy y el SLO (PQ-97)

Prueba del 23-nov-2026 con los cinco servicios y una copia de los logs reales del runner y del
vigilante:

| Comprobación | Resultado |
|---|---|
| `promtool check rules`, `alloy fmt`, `loki -verify-config` | 10 reglas (8 alertas y 2 de registro), sintaxis de Alloy y configuración de Loki válidas |
| Logs en Loki | Las 34 líneas, con las etiquetas `component` (`paper_runner`, `paper_watchdog`) y `level`; las 4 `warning` del vigilante salen en la consulta del panel |
| Grafana | La fuente Loki responde; el tablero tiene 14 paneles |
| SLO | `pq:slo_heartbeat:ratio_7d = 1` con el runner sano. Al detener las métricas, `pq:heartbeat_ok:bool` pasa a 0: la caída cuenta |
| Memoria (`docker stats`) | Prometheus 41 MB, Loki 80 MB, Grafana 111 MB, Alloy 39 MB, Alertmanager 23 MB: **≈ 293 MB** en total, muy lejos de la cuota de la VM (6 GB en la A1 de 1 OCPU; 12 GB con 2 OCPU) |

Hallazgo de la prueba: con `cap_drop: ALL`, root no puede entrar en la carpeta de datos de Alloy,
que es de su usuario (770). Por eso Alloy corre como su usuario `473:473`, sin privilegios, en
lugar de devolverle capacidades.
