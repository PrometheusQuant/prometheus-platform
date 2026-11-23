#!/bin/sh
# Arranque de Alertmanager (PQ-71): completa la plantilla con el token y el chat de Telegram
# (PQ_TELEGRAM_BOT_TOKEN, PQ_TELEGRAM_CHAT_ID) y la escribe en /tmp, que es tmpfs: la
# configuración con el token nunca toca el disco ni el repo.
set -eu
if [ -z "${PQ_TELEGRAM_BOT_TOKEN:-}" ] || [ "${PQ_TELEGRAM_CHAT_ID:-0}" = "0" ]; then
  echo "alertmanager: faltan PQ_TELEGRAM_BOT_TOKEN o PQ_TELEGRAM_CHAT_ID en el .env" >&2
  echo "alertmanager: ver docs/runbooks/alertas.md; sin canal no hay a quién avisar" >&2
  exit 1
fi
sed -e "s|__BOT_TOKEN__|${PQ_TELEGRAM_BOT_TOKEN}|" -e "s|__CHAT_ID__|${PQ_TELEGRAM_CHAT_ID}|" \
  /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
exec /bin/alertmanager \
  --config.file=/tmp/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.listen-address=127.0.0.1:9093 \
  --cluster.listen-address=
