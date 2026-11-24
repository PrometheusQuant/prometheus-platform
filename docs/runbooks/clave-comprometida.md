# Clave de API comprometida (SEV-1)

## Cuándo aplica

Cualquiera de estas señales, aunque no sea seguro que la clave se filtró:

- Órdenes o posiciones en el exchange que el diario (`data/paper/diario.jsonl`) no registró.
- gitleaks, CodeQL o un aviso de GitHub detectan una clave en un commit, un PR o un log.
- La clave aparece en un chat, una captura, un archivo compartido o la salida de un agente.
- El exchange avisa de un acceso desde una IP que no es la del servidor.
- Se perdió o se comprometió la laptop o el servidor donde vive el `.env`.

**No hay que confirmar antes de actuar.** Revocar una clave sana cuesta 15 minutos; dudar con una
clave filtrada puede costar el capital.

## Pasos (objetivo: clave revocada en 15 min, según el BIA)

1. **Detener la operación** desde donde estés:
   - desde el celular: `/kill` en el grupo de Telegram y el código que devuelve el bot;
   - desde la terminal: `uv run pq paper kill --reason "clave comprometida"`.

   El runner cancela las órdenes y cierra las posiciones en su ciclo siguiente
   ([kill-switch](kill-switch.md)).
2. **Revocar la clave en el exchange:** *Gestión de API* → borrar la clave. Hazlo aunque el
   kill-switch ya haya actuado: el kill-switch para **nuestro** proceso, no a quien tenga la clave.
3. **Revisar el exchange a mano:** órdenes abiertas, posiciones, historial de operaciones y de
   retiros. Las claves se crean **sin permiso de retiro**, así que no puede haber retiros con ellas.
   Si los hay, la que se filtró es la cuenta, no la clave: cambia la contraseña, el 2FA y escribe
   al soporte del exchange.
4. **Si la clave llegó a git:** revocarla (paso 2) ya la vuelve inútil. Después limpia el historial
   del repositorio y avisa en el PR. Un secreto en un repo público se considera publicado aunque
   se borre.
5. **Crear una clave nueva** con lo mínimo: solo lectura y trading, sin retiro y con la **lista
   blanca de la IP del servidor**. Ponla solo en el `.env` del servidor, nunca en el chat ni en git.
6. **Rearmar** con `uv run pq paper kill --reset --confirm --by <nombre>` y arrancar el runner.

## Cómo verificar

- `uv run pq paper status` muestra el kill-switch activado tras el paso 1, y armado tras el 6.
- El exchange ya no muestra la clave vieja y tiene la nueva con su IP en la lista blanca.
- `/estado` en Telegram: posiciones en cero tras el paso 1, y el runner sano tras el 6.

## A quién avisar

- Al otro miembro del equipo, por el grupo de Telegram, **en el momento** del paso 1.
- Post-mortem el mismo día ([incidentes](incidentes.md)).

## Simulacros

| Fecha | Tipo | Resultado |
|---|---|---|
| 2026-11-22 | De escritorio: recorrido de los pasos sin claves reales | Los pasos 1 y 6 existen y están probados (kill-switch, PQ-53; bot, PQ-72). Los pasos 2, 3 y 5 dependen del exchange: **pendiente** repetirlos con la clave de Demo (PQ-52) y cronometrar el tiempo hasta la revocación |
