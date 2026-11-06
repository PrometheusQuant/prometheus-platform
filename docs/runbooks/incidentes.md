# Gestión de incidentes

Qué hacer cuando algo falla. La meta es restaurar rápido (incidente) y después encontrar la causa
(problema, que se registra en los [errores conocidos](errores-conocidos.md)).

> **Estado:** todavía no hay proceso de trading en vivo. Los procedimientos de las severidades 1 y 2
> se aplican desde el paper trading (épica PQ-7). Lo marcado como *planeado* aún no existe.

## Severidades

| Severidad | Ejemplos | Respuesta |
|---|---|---|
| **SEV-1 Crítica** | Clave de API filtrada; fondos en riesgo; quiebra o congelamiento de retiros del exchange | Inmediata. Kill-switch, revocar la clave y avisar a los dos miembros del equipo |
| **SEV-2 Mayor** | Proceso live caído con posición abierta; datos de mercado congelados; error de una pata (spot sin su cobertura) | Menos de 1 h. Restaurar la cobertura o cerrar la posición |
| **SEV-3 Menor** | Falla la ingesta de un mes; la CI se rompe; el dashboard no carga | Dentro del día. Ticket en Jira |

## Detección

| Fuente | Estado |
|---|---|
| Logs JSON con nivel, evento y entorno (`ops/logging.py`) | Existe |
| Rechazos de ingesta en `data/bronze/_rejections.jsonl` | Existe |
| Informe de calidad de silver (`data/silver/_quality/`) | Existe |
| CI: lint, tipos, tests, gitleaks, CodeQL y `pip-audit` | Existe |
| Alertas ERROR/CRITICAL a Telegram (PQ-38) | Planeado |
| Heartbeat del proceso live y alerta si se calla | Planeado (PQ-7/PQ-8) |

## Respuesta por severidad

### SEV-1: clave filtrada o fondos en riesgo

1. Activar el kill-switch: cancelar órdenes y cerrar posiciones (*planeado, PQ-7*). Mientras no
   exista, hacerlo a mano desde la web del exchange.
2. Revocar la clave en Binance. Las claves no tienen permiso de retiro, lo que limita el daño
   ([SECURITY.md](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/SECURITY.md)).
3. Si la clave llegó a git: rotarla y limpiar el historial, aunque gitleaks debería haberlo frenado
   en el pre-commit y en la CI.
4. Post-mortem el mismo día.

### SEV-2: proceso caído con posición abierta

El carry es delta-neutral: una caída del proceso **no** deja exposición al precio mientras las dos
patas sigan abiertas. El riesgo es que el short se liquide si el precio sube mucho sin rebalancear.

1. Verificar en el exchange que las dos patas siguen abiertas y con margen suficiente.
2. Reiniciar el proceso. Si no arranca en el RTO del [BIA](analisis-de-impacto.md), cerrar ambas patas a mano.

### SEV-3

Ticket en Jira con la etiqueta `incidente` y, si se repite, una entrada en los errores conocidos.

## Post-mortem (sin culpables)

Para SEV-1 y SEV-2, en `docs/runbooks/postmortems/AAAA-MM-DD-titulo.md`: qué pasó (línea de tiempo),
impacto, causa raíz, qué funcionó, qué no y acciones (cada una con ticket). Se describe el sistema,
no a las personas.
