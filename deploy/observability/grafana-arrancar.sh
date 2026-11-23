#!/bin/sh
# Arranque de Grafana (PQ-71): sin PQ_GRAFANA_ADMIN_PASSWORD se genera una contraseña al azar,
# para que nunca quede el admin/admin de fábrica. Grafana solo la aplica al crear su base de
# datos (primer arranque); para cambiarla después: grafana cli admin reset-admin-password.
set -eu
if [ -z "${GF_SECURITY_ADMIN_PASSWORD:-}" ]; then
  GF_SECURITY_ADMIN_PASSWORD="$(head -c 24 /dev/urandom | base64)"
  export GF_SECURITY_ADMIN_PASSWORD
  echo "grafana: sin PQ_GRAFANA_ADMIN_PASSWORD; contraseña de admin generada al azar (no se muestra)"
fi
exec /run.sh
