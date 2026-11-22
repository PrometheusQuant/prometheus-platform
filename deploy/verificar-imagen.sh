#!/usr/bin/env bash
# Verifica la firma y el SBOM de una imagen antes de desplegarla (PQ-81).
#
#   deploy/verificar-imagen.sh ghcr.io/prometheusquant/pq-dashboard:develop
#
# Solo acepta imágenes firmadas sin clave por el workflow imagen.yml de este repo en develop o
# main. Si la verificación pasa, imprime la referencia por digest (inmutable): despliega esa, nunca
# la etiqueta, porque la etiqueta puede moverse entre la verificación y el pull.
set -euo pipefail

ref="${1:?uso: verificar-imagen.sh <imagen[:etiqueta]|imagen@sha256:...>}"
identidad='^https://github\.com/PrometheusQuant/prometheus-platform/\.github/workflows/imagen\.yml@refs/heads/(develop|main)$'
emisor='https://token.actions.githubusercontent.com'

if [[ "$ref" == *@sha256:* ]]; then
  fijada="$ref"
else
  nombre="$ref"
  # Quita la etiqueta solo si el último tramo la tiene (un registro puede llevar :puerto).
  [[ "${ref##*/}" == *:* ]] && nombre="${ref%:*}"
  digest="$(docker buildx imagetools inspect "$ref" --format '{{.Manifest.Digest}}')"
  [[ "$digest" == sha256:* ]] || { echo "No pude resolver el digest de $ref" >&2; exit 1; }
  fijada="${nombre}@${digest}"
fi

cosign verify --certificate-identity-regexp "$identidad" --certificate-oidc-issuer "$emisor" \
  "$fijada" >/dev/null
cosign verify-attestation --type cyclonedx --certificate-identity-regexp "$identidad" \
  --certificate-oidc-issuer "$emisor" "$fijada" >/dev/null
echo "Firma y SBOM verificados: $fijada" >&2
echo "$fijada"
