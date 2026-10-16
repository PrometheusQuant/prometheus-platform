# Seguridad

Este repositorio es **público**. Cualquier secreto que llegue a git debe considerarse filtrado.

## Reglas

1. **Nunca** se versionan claves de API, tokens, archivos `.env` ni datos personales. Las
   credenciales viven en `.env` (ignorado por git) en desarrollo y en *GitHub Secrets* o
   `sops` + `age` en servidores.
2. Las claves de exchanges se crean **sin permiso de retiro** y con **lista blanca de IP**.
   El sistema solo necesita leer datos y operar.
3. Se usan subcuentas o claves separadas para `paper` y `live`.
4. `gitleaks` revisa cada commit (pre-commit) y cada push (CI).
5. El kill-switch (`portfolio_risk`) debe poder cancelar todas las órdenes aunque falle el resto
   del sistema.

## Si se filtra una clave

1. Revocarla de inmediato en el exchange.
2. Revisar el historial de órdenes y retiros de la cuenta.
3. Reescribir el historial de git no basta: la clave ya es pública.

## Reportar una vulnerabilidad

Escribe a los mantenedores por un canal privado (no abras un issue público).
