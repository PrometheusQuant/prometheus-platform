#!/usr/bin/env bash
# Secretos del servidor cifrados con sops + age (PQ-81). Guía: docs/runbooks/cadena-de-suministro.md
#
#   deploy/secretos.sh cifrar <archivo.env>  # en la máquina del titular: cifra la .env del servidor
#   deploy/secretos.sh editar                # la abre descifrada en $EDITOR y la vuelve a cifrar
#   deploy/secretos.sh destinatarios         # recifra tras cambiar las claves en .sops.yaml
#   deploy/secretos.sh descifrar <destino>   # en la VM: escribe la .env con permisos 600
#
# Solo se versiona deploy/secretos/servidor.sops.env (cifrado). Los destinatarios están en
# .sops.yaml; las claves privadas age existen solo en la VM y en la máquina del titular.
set -euo pipefail
cd "$(dirname "$0")/.."
cifrado=deploy/secretos/servidor.sops.env
formato=(--input-type dotenv --output-type dotenv)

case "${1:-}" in
  cifrar)
    origen="${2:?uso: secretos.sh cifrar <archivo.env>}"
    trap 'rm -f "$cifrado.tmp"' EXIT
    sops encrypt "${formato[@]}" --filename-override "$cifrado" "$origen" >"$cifrado.tmp"
    mv "$cifrado.tmp" "$cifrado"
    echo "Cifrado en $cifrado; ya se puede versionar." >&2
    ;;
  editar) sops edit "${formato[@]}" "$cifrado" ;;
  destinatarios) sops updatekeys --yes --input-type dotenv "$cifrado" ;;
  descifrar)
    destino="${2:?uso: secretos.sh descifrar <destino>}"
    umask 077
    trap 'rm -f "$destino.tmp"' EXIT
    sops decrypt "${formato[@]}" "$cifrado" >"$destino.tmp"
    mv "$destino.tmp" "$destino"
    echo "Descifrado en $destino (permisos 600)." >&2
    ;;
  *)
    sed -n '2,10p' "$0" >&2
    exit 2
    ;;
esac
