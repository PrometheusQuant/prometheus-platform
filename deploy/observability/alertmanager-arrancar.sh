#!/bin/sh
# Arranque de Alertmanager (PQ-71): completa la plantilla con el token y el chat de Telegram
# (PQ_TELEGRAM_BOT_TOKEN, PQ_TELEGRAM_CHAT_ID) y la escribe en /tmp, que es tmpfs: la
# configuración con el token nunca toca el disco ni el repo.
set -eu
sed -e "s|__BOT_TOKEN__|${PQ_TELEGRAM_BOT_TOKEN}|" -e "s|__CHAT_ID__|${PQ_TELEGRAM_CHAT_ID}|" \
  /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
exec /bin/alertmanager \
  --config.file=/tmp/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.listen-address=127.0.0.1:9093 \
  --cluster.listen-address=
