# Observabilidad: métricas del runner, Prometheus y Grafana (PQ-71)

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

2. La pila de observabilidad, con el perfil `observability` de docker compose. Lee
   `PQ_TELEGRAM_BOT_TOKEN`, `PQ_TELEGRAM_CHAT_ID` y `PQ_GRAFANA_ADMIN_PASSWORD` del `.env`:

    ```bash
    docker compose --profile observability up -d
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

## El tablero

`deploy/observability/grafana/dashboards/paper-trading.json` se carga solo al arrancar Grafana
(*provisioning*) y no se puede editar desde la interfaz. Se cambia en el JSON, con su PR.
Paneles:

- **Estado:** equity, PnL, caída, antigüedad del heartbeat, kill-switch y último ciclo.
- **Curvas:** equity, funding y costes, exposición por pata y desbalance de la cobertura.
- **Órdenes:** latencia p50/p95 y órdenes ejecutadas y rechazadas por hora.

## Memoria

Cada contenedor tiene su límite (`mem_limit`) para no competir con el runner en la VM gratuita:

| Servicio | Límite |
|---|---|
| Prometheus | 256 MB, retención 15 días o 1 GB en disco |
| Grafana | 192 MB |
| Alertmanager | 64 MB |

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
