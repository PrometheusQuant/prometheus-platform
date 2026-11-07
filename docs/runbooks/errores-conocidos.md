# Errores conocidos (KEDB)

Registro de problemas ya analizados y su solución temporal (*workaround*) o definitiva, según la
práctica de gestión de problemas de ITIL 4. Antes de investigar un fallo, buscar aquí.

**Formato:** cada error tiene un identificador, síntomas, causa, workaround y estado. Al resolverse se
marca **Resuelto**, con el PR que lo arregló. No se borra: queda como historia.

| ID | Error | Estado |
|---|---|---|
| KE-001 | El rebalanceo no mantenía el apalancamiento 1x | Resuelto |
| KE-002 | Modelos por defecto sin la tasa base en la formulación residual | Resuelto |
| KE-003 | La CI rechaza el `uv.lock` aunque en local pasa | Resuelto |
| KE-004 | Material for MkDocs en mantenimiento; MkDocs 2.0 lo rompe | Workaround |
| KE-005 | MLflow completo exige `pyarrow < 24` | Workaround |
| KE-006 | El almacén en archivos de MLflow está en mantenimiento | Workaround |
| KE-007 | Días ausentes en las velas del perp de SOL y XRP en 2022 | Abierto |
| KE-008 | `docker` no se encuentra en WSL cuando Docker Desktop está cerrado | Resuelto |
| KE-009 | `gh pr edit` falla por la deprecación de Projects clásicos | Workaround |
| KE-010 | El modo automático bloquea el force-push | Workaround |
| KE-011 | La tabla oficial de comisiones de futuros no se lee sin sesión | Abierto |
| KE-012 | Dependencias de desarrollo con CVE (`filelock`, `virtualenv`) | Resuelto |
| KE-013 | Los tests leían el `.env` real de quien los ejecuta | Resuelto |
| KE-014 | La evaluación de desarrollo incluye la liquidación del 2024-07-01 00:00 (holdout) | Abierto |
| KE-015 | `CERTIFICATE_VERIFY_FAILED` contra Binance en una red con inspección TLS | Workaround |
| KE-016 | El backtest del carry ejecuta en la vela que abre en *t*, no en *t* + 1 h (enmienda 1.1) | Abierto |

---

### KE-001: el rebalanceo no mantenía el apalancamiento 1x

- **Síntoma:** en la prueba de humo, B1 cobraba un funding de 1,79 sobre un capital de 1.
- **Causa:** la regla literal igualaba la pata perp a la spot, pero no reducía el nocional cuando el
  precio subía. Llegaba a ~4x y el margen del short quedaba negativo.
- **Solución:** ambas patas se llevan a capital/2 si una se desvía más del 10 %. Declarado en la
  enmienda 2 del pre-registro (las 2 ejecuciones cuentan en N). **Resuelto** (PR #23 y #24).

### KE-002: modelos por defecto sin la tasa base en la formulación residual

- **Síntoma:** Ridge con α = 1 daba R² −0,02, y con α = 10 daba 0,71.
- **Causa:** una edición de texto no se aplicó a una línea que ruff había partido en varias. Los
  modelos sin ajustar predecían el residuo sin sumar la tasa actual.
- **Solución:** corrección y test de regresión `test_default_and_tuned_ridge_are_close_in_residual_mode`.
  **Resuelto** (PR #25).

### KE-003: la CI rechaza el `uv.lock` aunque en local pasa

- **Síntoma:** `error: The lockfile at uv.lock needs to be updated, but --locked was provided`.
- **Causa:** la CI usa la última versión de uv y en local había una más vieja; además, Dependabot
  genera partes del lock con la versión nueva.
- **Solución:** `uv self update` antes de tocar dependencias. Workaround: `uvx uv@latest lock`.
  **Resuelto.**

### KE-004: Material for MkDocs en mantenimiento; MkDocs 2.0 lo rompe

- **Workaround:** `mkdocs<2` fijado en `pyproject.toml`; configuración sin plugins de terceros para
  poder migrar a Zensical ([ADR-0007](../adr/0007-mkdocs-material-para-la-documentacion.md)).

### KE-005: MLflow completo exige `pyarrow < 24`

- **Workaround:** `mlflow-skinny` (cliente de tracking) + SQLite. La interfaz se abre aparte con
  `uvx mlflow ui --backend-store-uri sqlite:///data/mlflow/mlflow.db`.

### KE-006: el almacén en archivos de MLflow está en mantenimiento

- **Síntoma:** `MlflowException: The filesystem tracking backend … is in maintenance mode`.
- **Workaround:** backend SQLite (`adapters/mlflow_registry.py`).

### KE-007: días ausentes en las velas del perp de SOL y XRP en 2022

- **Síntoma:** faltan del 2022-02-26 al 28 y del 2022-04-01 al 02 (120 velas de 1 h por símbolo);
  BTC y ETH no tienen el hueco.
- **Workaround:** silver lo informa y no lo imputa; el backtest ejecuta en la siguiente vela disponible.
- **Pendiente:** contrastar con los archivos diarios y la API REST.

### KE-008: `docker` no se encuentra en WSL cuando Docker Desktop está cerrado

- **Síntoma:** `The command 'docker' could not be found in this WSL 2 distro`, aunque la integración WSL
  esté activada; el binario de `/mnt/wsl/docker-desktop/cli-tools` se cae al arrancar.
- **Causa:** Docker Desktop no estaba abierto (`wsl.exe -l -v` muestra `docker-desktop  Stopped`). El
  enlace `/usr/bin/docker` y el socket `/var/run/docker.sock` solo existen mientras corre. La integración
  con Ubuntu siempre estuvo activa.
- **Diagnósticos erróneos previos:** primero se atribuyó a la integración WSL desactivada y luego (PR #37)
  a una limitación de la terminal del agente. Con Docker Desktop abierto el agente sí ejecuta `docker`.
- **Solución:** abrir Docker Desktop. Para no depender de acordarse: *Settings* → *General* →
  *Start Docker Desktop when you sign in*. **Resuelto** (2026-11-06).
- **Lección:** antes de culpar a la configuración, comprobar si el servicio del que depende está corriendo.

### KE-009: `gh pr edit` falla por la deprecación de Projects clásicos

- **Workaround:** `gh api -X PATCH repos/<org>/<repo>/pulls/<n> -F body=@archivo.md`.

### KE-010: el modo automático bloquea el force-push

- **Workaround:** subir la rama rebasada con un nombre nuevo y abrir un PR que reemplace al anterior.

### KE-011: la tabla oficial de comisiones de futuros no se lee sin sesión

- **Workaround:** fuentes secundarias y el taker más conservador (0,05 %). La verificación desde la
  cuenta queda en PQ-17 y bloquea el holdout de H2.

### KE-012: dependencias de desarrollo con CVE

- **Síntoma:** `make audit` encontró 25 CVE en `filelock 4.2.0` y `virtualenv 21.14.8`, que llegan
  por `pre-commit`.
- **Solución:** `uv lock --upgrade-package filelock --upgrade-package virtualenv`. La CI audita cada PR
  desde entonces (PQ-37). **Resuelto.**

### KE-013: los tests leían el `.env` real de quien los ejecuta

- **Síntoma:** al crear un `.env` con el bot de Telegram, `test_notifier_selection_by_settings` falló:
  en `dev` esperaba «sin canal» y obtuvo un `TelegramNotifier` con el token real.
- **Causa:** `Settings()` lee `.env` del directorio actual y las variables `PQ_*`. Solo los tests de
  `settings` se aislaban; los demás dependían de que no existiera `.env`. Ningún test llegó a enviar
  nada, pero uno mal escrito podría haber usado el token o las claves reales.
- **Solución:** fixture `autouse` en `tests/conftest.py` que desactiva el `.env` y borra las `PQ_*`
  en todos los tests; el test que prueba la lectura del `.env` lo reactiva sobre `tmp_path`.
  **Resuelto** (PQ-38).

### KE-014: la evaluación de desarrollo incluye la liquidación del 2024-07-01 00:00 (holdout)

- **Síntoma:** encontrado por la revisión adversarial de PQ-46 (skill `doubt-driven-development`).
  - `daily_returns.parquet` termina con la valoración del 2024-07-01 00:00.
  - Esa valoración incluye el cobro de la liquidación de ese instante y la decisión que se toma con ella.
  - El pre-registro (§7) pone el holdout **desde 2024-07-01 00:00 UTC**.
- **Causa:** el corte de `simulate_symbol` (`open_time < HOLDOUT_START`) se aplica solo a las velas.
  - La última vela cierra exactamente a las 00:00 y aplica `settle_and_decide` con la liquidación de ese instante.
  - Afecta a las evaluaciones de PQ-23 a PQ-25 desde el Sprint 2.
- **Impacto medido (insignificante):**
  - En H2, la configuración elegida estaba fuera de posición ese día (retorno 0) y B1 movió −0,003 %.
  - Sin ese día, el Sharpe pasa de 5,573 a 5,575, el CAGR de 5,030 % a 5,033 % y el de B1 de 0,659 a 0,660.
  - En H1 el cambio es igual de pequeño.
  - Ningún gate ni prueba de PQ-48 cambia de resultado.
- **Mitigación hoy:** la capa gold excluye esa valoración y todo lo que se devenga en el holdout.
  Sus hechos terminan el 2024-06-29.
- **Solución pendiente (PQ-50):**
  - La corrección del código exige volver a ejecutar la evaluación, que cuenta en N (pre-registro §10).
  - Se hará en la misma reejecución que pida PQ-17 si las comisiones reales son más altas, o
    al preparar la evaluación del holdout.
  - Sea como sea, la evaluación del holdout debe contar esa liquidación como suya, y la del
    desarrollo no.

### KE-015: `CERTIFICATE_VERIFY_FAILED` contra Binance en una red con inspección TLS

- **Síntoma:** `pq paper run` o `pq ingest --source api` fallan con
  `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate`.
  `curl` también falla. En otra red, el mismo comando funciona.
- **Causa:** un cortafuegos de la red (visto el 2026-11-06: Fortinet) intercepta el TLS hacia
  `*.binance.com` y presenta un certificado firmado por su propia CA, que no está en el almacén de
  `certifi`. Se confirma mirando el emisor:
  `openssl s_client -connect api.binance.com:443 -servername api.binance.com </dev/null | openssl x509 -noout -issuer`.
  Si el emisor no es una CA pública, la red está inspeccionando el tráfico. Otros dominios (p. ej.
  `github.com`) pueden no estar interceptados.
- **Workaround:** **nunca desactivar la verificación de certificados.**
  - Lo más simple: usar otra red (casa, datos móviles) o el servidor compartido (PQ-115).
  - Si la red es de confianza y su CA está disponible: `export SSL_CERT_FILE=/ruta/ca-de-la-red.pem`.
    `httpx` 0.28 la usa en lugar de `certifi` (`httpx/_config.py`). Sin esa variable, nada cambia.
  - Los tests no se ven afectados: no salen a la red (`httpx.MockTransport`).

### KE-016: el backtest del carry ejecuta en la vela que abre en *t*, no en *t* + 1 h

- **Síntoma:** lo encontró la revisión adversarial de PQ-54 al comparar el runner con el backtest.
  La enmienda 1.1 del pre-registro dice que las órdenes se ejecutan al `open` de la vela que
  **abre en t + 1 h**. Con un precio que sube 1 por hora, una decisión a las 00:00 se ejecuta al
  `open` de la vela de las 00:00 (124) y no al de la de las 01:00 (125).
- **Causa:** `simulate_symbol` decide al cierre de la vela que termina en *t* y marca la orden
  como pendiente. La ejecuta en la iteración siguiente, que es la vela que **abre** en *t*. Le
  falta esperar una vela más.
- **Qué no es:** no es look-ahead. La tasa liquidada en *t* se conoce en *t*, y se opera después.
  Es una latencia de 0 h en lugar de 1 h: el backtest opera una hora antes de lo pre-registrado.
- **Impacto:** por medir. Hay que volver a ejecutar la evaluación, y esa ejecución cuenta en N
  (pre-registro §10).
- **Solución pendiente:** se corrige junto con KE-014, en la misma reejecución (PQ-50 o la que
  pida PQ-17). El runner de paper (PQ-54) ya aplica la latencia de 1 h.
