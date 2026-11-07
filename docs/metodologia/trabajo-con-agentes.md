# Trabajo en dos carriles con agentes de IA

Desde el Sprint 3 el equipo trabaja en **dos carriles en paralelo**, cada uno con su agente:

| Carril | Persona | Agente | Lee las reglas en |
|---|---|---|---|
| David | David Quintela | Claude Code | `CLAUDE.md`, que importa `AGENTS.md` |
| Boris | Boris Miranda | Codex CLI (ChatGPT) | `AGENTS.md` (Codex lo lee solo) |

Las reglas del proyecto viven en un solo lugar, [`AGENTS.md`](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/AGENTS.md).
Esta página explica **cómo arrancar** y **cómo trabajar un ticket** de principio a fin.

## 1. Preparar la máquina (una vez)

**Atajo para Boris:** el [prompt inicial para Codex](prompt-inicial-codex.md) hace todo esto y lo
que sigue, fase por fase.


Requisitos: Linux o WSL2 con Ubuntu, `git`, [`uv`](https://docs.astral.sh/uv/) 0.13 o superior,
[`gh`](https://cli.github.com/) con sesión iniciada, y Codex CLI instalado según la documentación
oficial de OpenAI. Docker Desktop es opcional (solo para `make e2e`).

```bash
git clone https://github.com/PrometheusQuant/prometheus-platform.git
cd prometheus-platform
make setup                 # entorno con uv y hooks de git (commit-msg valida el formato)
cp .env.example .env       # tu configuración local; nunca se sube a git
make check                 # debe pasar entero antes de empezar a programar
```

### Conectar Codex con Jira

Codex CLI puede leer y actualizar los tickets con el
[servidor MCP oficial de Atlassian](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/):

```bash
codex mcp add atlassian --url https://mcp.atlassian.com/v2/mcp
codex mcp login atlassian     # abre el navegador: inicia sesión con tu cuenta de Jira y autoriza
codex mcp list                # debe mostrar «atlassian» autenticado
```

El endpoint `v2` es el que Atlassian recomienda en su
[guía de migración](https://support.atlassian.com/atlassian-ai-gateway/docs/how-to-upgrade-from-atlassian-rovo-mcp-v1-to-atlassian-rovo-mcp-v2/).
Si tu versión de Codex no lo acepta, usa el de la guía de inicio (`…/v1/mcp/authv2`).

Prueba: pídele a Codex «lista mis tickets del sprint activo del proyecto PQ». Si no responde, la
autorización de OAuth no se completó: repite `codex mcp login atlassian`.

## 2. Reconstruir el lakehouse (una vez, y cuando haga falta)

`data/` no está en git. Los **tests no lo necesitan**: usan datos sintéticos. Sí lo necesitas para
investigar y para ver el dashboard con datos reales.

```bash
for s in BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT; do
  uv run pq ingest funding --symbol $s --start 2020-01
  uv run pq ingest klines --market spot --symbol $s --interval 1h --start 2020-01
  uv run pq ingest klines --market um   --symbol $s --interval 1h --start 2020-01
  uv run pq ingest --source api funding --symbol $s                       # mes en curso
  uv run pq ingest --source api klines --market spot --symbol $s --interval 1h
  uv run pq ingest --source api klines --market um   --symbol $s --interval 1h
  uv run pq silver build --symbol $s
done
uv run pq gold build
```

También se puede hacer desde la interfaz de Dagster (`make orquestador`).

!!! warning "No regeneres los resultados de research por tu cuenta"
    `pq research carry`, `funding-model` y similares son **ensayos**: cada ejecución suma a N en el
    Deflated Sharpe. Si necesitas los artefactos ya evaluados (`data/research/`), pídeselos a David.
    Ejecuta research solo para tus propias hipótesis pre-registradas, y deja registro de cada
    ejecución (ver la sección 4).

## 3. Trabajar un ticket con Codex

1. **Toma un ticket de tu carril** (asignado a ti, en el sprint activo). Puedes pedírselo a Codex:
   «lee PQ-<n> y muévelo a In Progress».
2. **Crea la rama** desde `develop` actualizado:
   ```bash
   git switch develop && git pull
   git switch -c feature/PQ-<n>-descripcion-corta
   ```
3. **Arranca Codex en la raíz del repo** y dale el ticket con este molde:

   ```text
   Lee AGENTS.md antes de nada. Trabajas en el ticket PQ-<n> del carril de Boris.
   Lee el ticket en Jira (proyecto PQ) y cumple sus criterios de aceptación.

   Reglas: rama actual feature/PQ-<n>-…; commits Conventional Commits con la clave PQ-<n>;
   si es research, primero el pre-registro y nunca el holdout; si la historia es de 5 puntos o
   más, escribe primero specs/PQ-<n>-<nombre>/spec.md y plan.md. Antes de afirmar algo no
   trivial, aplica .claude/skills/doubt-driven-development/SKILL.md. Al terminar corre
   `make check` y `make docs-build`, y no inventes cifras.
   ```

4. **Revisa lo que hizo Codex** antes de commitear. Tú eres el responsable del PR, no el agente.
5. **Abre el PR** a `develop` con la plantilla (`gh pr create`). Pide la revisión del carril de
   David. **No fusiones tu propio PR**: la regla de GitHub exige 1 aprobación y la CI en verde.
6. Con la aprobación y la CI en verde, fusiona con **squash** y mueve el ticket a *Done* (Codex
   puede hacerlo por ti).

## 4. Reglas que no se negocian (resumen de `AGENTS.md`)

- **Pre-registro antes de mirar resultados.** El holdout se abre una sola vez.
- **Cada ejecución de research cuenta en N.** Anótala: hipótesis, configuración, commit y métricas,
  en la descripción del PR. Cuando exista el registro compartido (PQ-112), en ese registro.
- **Costes reales** (`CostModel`) y **point-in-time** (`knowledge_time`) siempre.
- **Secretos** solo en tu `.env`. Nunca en el código, en los logs ni en el chat con el agente.
- **No toques el núcleo del otro carril.** Usa los puertos de `domain/ports.py`. Si te falta algo,
  pídelo en un ticket.

## 5. Revisión cruzada

Cada carril revisa los PR del otro con la guía
[`code-review-and-quality`](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/.claude/skills/code-review-and-quality/SKILL.md).
Es también la evidencia del code review del capítulo 9.3. Además, dos modelos distintos
(Claude y GPT) detectan errores distintos.

| Prefijo | Significado |
|---|---|
| **Crítico:** | Bloquea el merge |
| *(sin prefijo)* | Cambio requerido |
| **Considera:** / **Nit:** | Opcional |
