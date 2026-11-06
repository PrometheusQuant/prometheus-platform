# CLAUDE.md

Las reglas del proyecto viven en `AGENTS.md`, que también lee Codex (carril de Boris). Ese archivo
es la fuente única: no dupliques reglas aquí.

@AGENTS.md

## Solo para Claude Code

- Las skills de `.claude/skills/` se cargan solas; úsalas en los momentos que indica `AGENTS.md`.
- Al fusionar PRs del carril de Boris, revísalos primero con la skill `code-review-and-quality` y
  deja la revisión en GitHub (`gh pr review`). Su aprobación cuenta como la del carril de David.
