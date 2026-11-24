# CLAUDE.md

Las reglas del proyecto viven en `AGENTS.md`, que también lee Codex (carril de Boris). Ese archivo
es la fuente única: no dupliques reglas aquí.

@AGENTS.md

## Solo para Claude Code

- Las skills de `.claude/skills/` se cargan solas; úsalas en los momentos que indica `AGENTS.md`.
- Hay dos sesiones de Claude Code en la misma máquina (Claude A y Claude B): sigue la sección
  «Coordinación entre agentes» de `AGENTS.md`. Trabaja siempre en tu worktree de `~/code/wt/`,
  nunca en `~/code/prometheus-platform` ni en `~/code/pq-runtime`.
- Antes de fusionar, revisa el diff con la skill `code-review-and-quality` y deja el resultado
  como comentario en el PR.
