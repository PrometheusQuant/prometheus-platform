#!/usr/bin/env bash
# Respaldo cifrado (cada hora) de data/paper al repo privado PrometheusQuant/paper-respaldos (PQ-73).
#
# 1. `pq paper backup create` cifra data/paper con la clave pública age (PQ_BACKUP_AGE_RECIPIENT)
#    y borra los respaldos de más de PQ_BACKUP_KEEP_DAYS (14) en la carpeta del repo.
# 2. Un commit huérfano con lo que queda reemplaza la historia (push --force): la retención de
#    14 días se cumple también en git. Los respaldos van cifrados; el servidor no puede leerlos.
#
# Si algo falla, avisa al canal de alertas y sale con error (el cron lo deja en el log).
# Uso (cron, cada hora: se pierde como mucho una hora de eventos):
#   7 * * * * /ruta/prometheus-platform/deploy/respaldos/respaldar.sh >> ~/respaldos.log 2>&1
set -euo pipefail

PLATFORM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_DIR="${PQ_BACKUP_REPO_DIR:-$HOME/paper-respaldos}"

avisar_fallo() {
  (cd "$PLATFORM_DIR" && uv run --quiet python - <<'PY'
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.notifiers import notifier_from_settings
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.ops.settings import load_settings

settings = load_settings()
notifier = notifier_from_settings(settings)
if notifier is not None:
    notifier.notify(Alert(
        severity=AlertSeverity.ERROR,
        title="falló el respaldo diario de data/paper",
        occurred_at=SystemClock().now(),
        environment=settings.environment.value,
        details={"origen": "deploy/respaldos/respaldar.sh", "ticket": "PQ-73"},
    ))
PY
  ) >/dev/null 2>&1 || true
}
trap avisar_fallo ERR

[[ -d "$REPO_DIR/.git" ]] || { echo "falta el clon de paper-respaldos en $REPO_DIR"; false; }

cd "$PLATFORM_DIR"
uv run --quiet pq paper backup create --out "$REPO_DIR/respaldos"

cd "$REPO_DIR"
git checkout -q --orphan respaldo-nuevo
git add -A respaldos
git commit -q -m "respaldo $(date -u +%Y-%m-%dT%H:%MZ)"
git branch -q -M respaldo-nuevo main
git push -q --force origin main
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) respaldo subido: $(ls respaldos | wc -l) archivo(s) en la ventana"
