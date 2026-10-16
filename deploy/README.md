# deploy/: despliegue e infraestructura

Todo lo necesario para levantar la plataforma fuera del entorno de desarrollo, versionado como
código (*infrastructure as code*). La infraestructura crece por fases de presupuesto:

| Fase | Coste | Infraestructura | Qué se despliega |
|---|---|---|---|
| 0 | 0 USD/mes | Laptop (WSL2) + Oracle Cloud Always Free | Paper trading en testnet, pipeline de datos, MLflow |
| 1 | ~20 USD/mes | VPS (Hetzner) | Proceso live 24/7, Prometheus + Grafana, alertas a Telegram, backups |
| 2 | ~100 USD/mes | Nodo live cerca del exchange + nodo de research | NATS JetStream entre nodos, Loki, monitoreo de drift |

```text
deploy/
├── compose/        # docker compose con perfiles: research, pipeline, live, observability
├── systemd/        # unidades para el proceso live en el VPS
├── observability/  # configuración de Prometheus, Grafana (dashboards) y alertas
└── runbooks/ →     # los procedimientos de operación viven en docs/runbooks/
```

## Reglas

- Secretos con `sops` + `age` o variables del servidor; nunca en texto plano en este directorio.
- Las claves de exchange en producción: **sin permiso de retiro** y con lista blanca de IP.
- Cada cambio de infraestructura entra por PR con su ticket, igual que el código.
