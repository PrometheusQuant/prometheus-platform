# Skills del proyecto

Claude Code las carga automáticamente cuando la tarea coincide con su `description`. También sirven
como guía para las personas: son Markdown, sin código ejecutable.

| Skill | Cuándo se usa |
|---|---|
| [`debugging-and-error-recovery`](debugging-and-error-recovery/SKILL.md) | Falla un test, la CI, el build o algo que funcionaba |
| [`doubt-driven-development`](doubt-driven-development/SKILL.md) | Antes de afirmar algo no trivial o de una acción irreversible |
| [`code-review-and-quality`](code-review-and-quality/SKILL.md) | Antes de fusionar un PR; guía de revisión del equipo |

## Origen y licencia

Adaptadas de [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), commit
`301b02b12bff98e4688e6984af6556802322bbde`, bajo licencia MIT (copia en
[`LICENSE-agent-skills`](LICENSE-agent-skills)). Cada `SKILL.md` indica qué se cambió respecto al
original. Las adaptaciones forman parte de este repositorio (Apache-2.0).

## Qué se descartó del repositorio original y por qué (PQ-42)

- **Planificación y especificación** (`spec-driven-development`, `planning-and-task-breakdown`):
  duplican Spec Kit y Jira (ADR-0008).
- **`git-workflow-and-versioning`**: propone trunk-based y desaconseja squash; contradice
  `CONTRIBUTING.md`.
- **Documentación, CI/CD, seguridad web, rendimiento web, frontend y publicación**: ya cubiertos por
  los ADR, la CI y `SECURITY.md`, o pensados para aplicaciones web en JavaScript.
- **Comandos y hooks del plugin**: ejecutan código. Por ejemplo, instalan paquetes de npm sin
  versión fija, reescriben archivos al leerlos o sirven resultados web desde caché. No aportan
  frente a su riesgo.
- **Candidatas para más adelante**: `test-driven-development`, `source-driven-development` y
  `observability-and-instrumentation` (útil para PQ-7 y PQ-8).

Para actualizar desde el original, compara contra el commit de arriba y conserva las adaptaciones.
