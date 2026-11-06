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
| KE-008 | Docker sin integración WSL en la máquina de desarrollo | Abierto |
| KE-009 | `gh pr edit` falla por la deprecación de Projects clásicos | Workaround |
| KE-010 | El modo automático bloquea el force-push | Workaround |
| KE-011 | La tabla oficial de comisiones de futuros no se lee sin sesión | Abierto |
| KE-012 | Dependencias de desarrollo con CVE (`filelock`, `virtualenv`) | Resuelto |

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

### KE-008: Docker sin integración WSL en la máquina de desarrollo

- **Síntoma:** `The command 'docker' could not be found in this WSL 2 distro`.
- **Solución (la aplica el titular):** Docker Desktop → *Settings* → *Resources* → *WSL integration* →
  activar la distribución. Bloquea probar en local la imagen del dashboard (PQ-34).

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
