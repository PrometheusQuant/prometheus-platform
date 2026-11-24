#!/usr/bin/env bash
# Reintenta el apply del stack de Resource Manager hasta que Oracle tenga capacidad A1 (PQ-56).
#
# En sa-bogota-1 la forma VM.Standard.A1.Flex responde casi siempre «Out of host capacity», y la
# E2.1.Micro da 404 (no parece ofrecerse en esa región). Oracle libera capacidad en momentos
# impredecibles: este script lanza un apply cada pocos minutos y se detiene en cuanto la VM existe.
#
# Requisitos: OCI CLI configurado (`oci setup config`, ver docs/runbooks/oracle-cloud.md) y el
# OCID del stack de Resource Manager que crea la VM A1.
#
# Uso:
#   deploy/oci/reintentar-a1.sh <OCID_DEL_STACK> [segundos_entre_intentos]
#   nohup deploy/oci/reintentar-a1.sh <OCID> > ~/reintento-a1.log 2>&1 &
#
# Si `uv` y el .env del repo tienen Telegram configurado, avisa al grupo de alertas al terminar.
set -uo pipefail

STACK_ID="${1:?uso: reintentar-a1.sh <OCID del stack> [segundos entre intentos]}"
ESPERA="${2:-300}"
ESPERA_429=900  # Oracle limita la frecuencia: ante un 429 se espera más
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

avisar() {  # $1 = severidad (info|warning|error), $2 = título; nunca hace fallar el script
  (cd "$REPO" && uv run --quiet python - "$1" "$2" <<'PY'
import sys
from prometheus_platform.adapters.clock import SystemClock
from prometheus_platform.adapters.notifiers import notifier_from_settings
from prometheus_platform.domain.alerts import Alert, AlertSeverity
from prometheus_platform.ops.settings import load_settings

settings = load_settings()
notifier = notifier_from_settings(settings)
if notifier is not None:
    notifier.notify(Alert(
        severity=AlertSeverity(sys.argv[1]),
        title=sys.argv[2],
        occurred_at=SystemClock().now(),
        environment=settings.environment.value,
        details={"origen": "deploy/oci/reintentar-a1.sh", "ticket": "PQ-56"},
    ))
PY
  ) >/dev/null 2>&1 || true
}

command -v oci >/dev/null || { log "ERROR: falta el OCI CLI (uv tool install oci-cli)"; exit 2; }

intento=0
while true; do
  intento=$((intento + 1))
  job_id="$(oci resource-manager job create-apply-job \
      --stack-id "$STACK_ID" \
      --execution-plan-strategy AUTO_APPROVED \
      --display-name "reintento-a1-$intento" \
      --wait-for-state SUCCEEDED --wait-for-state FAILED --wait-for-state CANCELED \
      --max-wait-seconds 1800 \
      --query 'data.id' --raw-output 2>/tmp/reintento-a1.err)"
  if [[ -z "$job_id" ]]; then
    if grep -q "TooManyRequests\|429" /tmp/reintento-a1.err; then
      log "intento $intento: 429 de Oracle, espero ${ESPERA_429}s"
      sleep "$ESPERA_429"
      continue
    fi
    log "ERROR al crear el job: $(tail -3 /tmp/reintento-a1.err)"
    avisar error "Reintento A1 detenido: no se pudo crear el job de Resource Manager"
    exit 1
  fi

  estado="$(oci resource-manager job get --job-id "$job_id" \
      --query 'data."lifecycle-state"' --raw-output)"

  if [[ "$estado" == "SUCCEEDED" ]]; then
    salidas="$(oci resource-manager job get-job-tf-state --job-id "$job_id" --file - 2>/dev/null \
      | python3 -c 'import json,sys; o=json.load(sys.stdin).get("outputs",{}); print(" ".join(k + "=" + str(v.get("value")) for k, v in o.items()))' \
      || true)"
    log "VM creada en el intento $intento. $salidas"
    avisar info "VM A1 de Oracle creada (intento $intento). $salidas"
    exit 0
  fi

  registro="$(oci resource-manager job get-job-logs-content --job-id "$job_id" --query data --raw-output 2>/dev/null || true)"
  if grep -q "Out of host capacity" <<<"$registro"; then
    log "intento $intento: sin capacidad A1, reintento en ${ESPERA}s"
    sleep "$ESPERA"
    continue
  fi
  if grep -q "TooManyRequests\|429" <<<"$registro"; then
    log "intento $intento: 429 de Oracle, espero ${ESPERA_429}s"
    sleep "$ESPERA_429"
    continue
  fi

  log "ERROR distinto de la capacidad (estado $estado), me detengo:"
  grep -iE "error|suggestion" <<<"$registro" | tail -5
  avisar error "Reintento A1 detenido en el intento $intento: error distinto de la falta de capacidad"
  exit 1
done
