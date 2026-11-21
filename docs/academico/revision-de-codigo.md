# Code review final y auditoría de trazabilidad (cap. 9.3)

**Ticket:** PQ-61 · **Fecha:** 21-nov-2026 · **Revisor:** Claude B, una sesión de agente distinta de
la que escribió los PR (Claude A), con contexto fresco · **Guía:**
[`code-review-and-quality`](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/.claude/skills/code-review-and-quality/SKILL.md)

El jurado técnico revisa commits, ramas y arquitectura. Este documento deja la evidencia de dos
cosas: que cada cambio del repositorio se puede rastrear hasta su ticket, y que el código de mayor
riesgo fue revisado por alguien distinto de su autor, con hallazgos clasificados por severidad.

## 1. Auditoría de trazabilidad Jira ↔ GitHub

GitHub for Jira (PQ-13) aún no está instalado, así que la auditoría se hizo cruzando dos listas:
todos los PR fusionados (`gh pr list --state merged`) con todos los tickets en *Done* del proyecto
`PQ` (JQL `project = PQ AND statusCategory = Done AND issuetype != Epic`).

| Comprobación | Resultado |
|---|---|
| PR fusionados en el repositorio | 68 |
| PR con su clave `PQ-<n>` en el título o la rama | 57 |
| PR sin clave | 11, todos justificados (abajo) |
| Tickets en *Done* (sin épicas) | 50 |
| Tickets en *Done* con un PR que los cita | 50 de 50 |
| Claves citadas en PR cuyo ticket no está en *Done* | 3, coherentes con su estado (abajo) |

**PR sin clave.** Ninguno es trabajo de un ticket sin registrar:

- 6 son actualizaciones de Dependabot (#1, #3, #4, #8, #16, #17);
- 3 son release y back-merge (#9, #40, #41), que siguen la convención de `CONTRIBUTING.md`;
- 2 son del arranque del repositorio (#2, ajuste de la CI de gitleaks, y #5, licencia Apache-2.0),
  anteriores a que existiera el tablero de Jira.

**Tickets entregados en un PR que no los nombra en el título.** PQ-24 y PQ-25 se entregaron en el
PR #24, cuyo título solo cita PQ-23; el cuerpo del PR y el commit sí los nombran. Es trazable, pero
ese PR agrupa tres historias en casi 2.500 líneas (ver §3).

**Claves citadas que siguen abiertas.** Las tres tienen entregas parciales, coherentes con su
estado:

- PQ-17 (*In Progress*): falta la verificación de comisiones del titular;
- PQ-47 (*To Do*): la guía de Power BI está fusionada, falta el `.pbix`;
- PQ-56 (*In Progress*): la guía y el reintento automático están fusionados, falta la VM.

**Conclusión:** la trazabilidad es completa. Todo ticket terminado tiene su PR y todo PR de trabajo
tiene su ticket.

## 2. Revisión de código

### Alcance

Se revisó el **código actual** de `develop`, no los diffs históricos: varios PR posteriores
corrigieron a los anteriores, y lo que importa es lo que corre hoy. Prioridades del ticket y lo que
se revisó de cada una:

| PR | Qué | Revisión |
|---|---|---|
| #24 | Validación anti-sobreajuste (`research/validation.py`) | Completa: fórmulas contrastadas con los papers |
| #28 | Simulación (`research/simulation.py`) | Parcial: estimación de Markov y muestreo |
| #30 | Alertas (`ops/logging.py`, `adapters/notifiers.py`) | Completa |
| #31 | Dashboard y Docker (`Dockerfile`, `docker-compose.yml`) | Endurecimiento del contenedor |
| #57 | Riesgo y kill-switch (`portfolio_risk/`) | Completa, con experimento |
| #62, #70 | Runner de paper trading (`api/paper/runner.py`) | Ciclo, ejecución y kill-switch |

Quedan fuera de esta revisión, y se revisan en la siguiente: #25 (modelo del cap. 5), #63
(monitoreo), #65 (puerto `Strategy`) y #73 (motor de tendencia; tuvo su propia revisión adversarial
con 15 de 15 mutantes detectados).

### Hallazgos

Siguiendo la guía, cada hallazgo se verificó con un experimento antes de reportarlo, y cada
requerido se convirtió en un ticket con la etiqueta `code-review`.

- **Requerido (seguridad) → PQ-118.** `ops/logging.py`: el procesador `redact_secrets` solo
  enmascara `SecretStr` y claves con nombre sensible. Los **valores de texto** no pasan por
  `redact_text`, aunque `AGENTS.md` dice que sí. **Experimento:** un token falso con el formato de
  Telegram dentro de `detail=` aparece tal cual en el log; `redact_text` sobre el mismo texto lo
  tapa. El riesgo hoy es bajo, porque los adaptadores loguean el tipo de excepción y no la URL. Pero
  el runner loguea `str(exc)` de cualquier excepción, y los adaptadores firmados (PQ-52, PQ-100)
  aumentan la superficie. **Propuesta:** aplicar `redact_text` a todo valor `str` en `_redact`.
- **Requerido (riesgo, latente) → PQ-119.** `portfolio_risk/risk.py`: `_exposure_check` suma a las
  posiciones el incremento de la orden nueva, pero **no las órdenes pendientes que aumentan**.
  **Experimento:** límite de 100 USD por símbolo, sin posición, 90 USD pendientes y una compra
  nueva de 90 USD: se aprueba, y quedan 180 USD comprometidos. Hoy no ocurre, porque el bróker
  simulado ejecuta al instante (el comentario de `runner.py:581` lo asume). Con un bróker asíncrono
  sí ocurre. **Propuesta:** calcular nocional y apalancamiento sobre la cantidad comprometida
  (posición más pendientes), antes de PQ-52.
- **Considera.** `research/simulation.py:260`: si la suma acumulada de una fila de la matriz de
  transición queda por debajo de 1, por redondeo o porque un régimen nunca aparece como origen, el
  muestreo devuelve el índice 3. Esas celdas de `rates` quedan **sin inicializar** (`np.empty`) sin
  ningún aviso. Con los datos actuales los tres regímenes aparecen y la probabilidad por redondeo es
  despreciable. **Propuesta:** fallar en voz alta si una fila suma 0, y acotar el índice con
  `np.minimum(…, 2)`.
- **Nit.** `research/validation.py`: si la equity llega a 0 o a un valor negativo, `cagr` devuelve
  `nan` en vez de −100 %. Además, la asimetría y la curtosis mezclan momentos poblacionales con la
  desviación muestral (`ddof=1`); el sesgo es despreciable con más de mil días.
- **Nit.** `api/paper/runner.py:591`: en las órdenes del kill-switch, el `client_order_id` repite la
  marca de tiempo, porque ya viene en la etiqueta. Es inofensivo.

### Lo que se verificó y está bien

- **Deflated Sharpe, SR₀, PBO y CPCV** (`validation.py`) coinciden con Bailey y López de Prado
  (2014), Bailey et al. (2017) y López de Prado (2018, cap. 12): la curtosis no excesiva en el
  denominador, el rango relativo de PBO en (0, 1), y el purge y el embargo a ambos lados del bloque.
- **Kill-switch:** la bandera se crea de forma exclusiva y atómica (`O_EXCL`) y se escribe con
  `fsync`. Rearmar exige autor, y si el diario falla se restaura la bandera. La activación manual
  (archivo creado a mano) se completa en el siguiente `observe`.
- **Runner:**
  - llama a `observe` al inicio de cada ciclo;
  - aprueba **todas** las patas antes de enviar ninguna;
  - con el kill-switch activado solo cierra, y reducir exposición nunca se bloquea;
  - un símbolo con fallos no detiene a los demás.
- **Notificador de Telegram:** ante un error solo registra el tipo de la excepción, nunca la URL,
  que lleva el token.
- **Contenedor del dashboard:**
  - puerto solo en `127.0.0.1`;
  - sistema de archivos de solo lectura y datos montados `:ro`;
  - `cap_drop: ALL` y `no-new-privileges`;
  - usuario sin privilegios.

## 3. Observaciones de proceso

- **PR demasiado grandes.** #24 (+2.491 líneas, tres historias) y #62 (+2.933) superan el tamaño
  que la guía considera revisable (~1.000 líneas). Desde PQ-117 la regla es un ticket por rama y PR
  pequeños.
- **Revisión a posteriori.** Los PR del Sprint 2 se fusionaron con bypass de administrador por
  decisión del titular. Este documento es su revisión posterior. Desde el 21-nov, cada PR lleva una
  revisión propia escrita como comentario antes de fusionarse (`AGENTS.md`, «Coordinación entre
  agentes»), que sirve de evidencia continua para este capítulo.
- **Pendiente:** instalar GitHub for Jira (PQ-13) para que la trazabilidad se vea en cada ticket sin
  hacer el cruce a mano.
