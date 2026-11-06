# ADR-0008: Especificación versionada con las plantillas de Spec Kit, solo en historias grandes

- **Estado:** Aceptada
- **Fecha:** 2026-10-30
- **Ticket:** PQ-30 (spike)

## Contexto y problema

[GitHub Spec Kit](https://github.com/github/spec-kit) (v1.2.5, MIT) propone el *Spec-Driven
Development*: primero se escribe la especificación, luego el plan y las tareas, y al final el
código. La pregunta era si mejora nuestro flujo (historia en Jira → plan en un comentario →
commits atómicos) sin crear una segunda fuente de verdad.

## Qué se probó

1. Se instaló en un directorio aislado: `uvx --from git+https://github.com/github/spec-kit.git@v1.2.5 specify init demo --integration claude --non-interactive`.
2. Se revisó lo que genera: `.specify/` con 5 plantillas (591 líneas), scripts de bash para crear
   ramas y carpetas, y **10 skills** en `.claude/skills/` (`speckit-specify`, `-plan`, `-tasks`,
   `-implement`, `-clarify`, `-analyze`, `-checklist` y otras).
3. Se aplicó a una historia real, **PQ-21 (capa silver)**: [`specs/PQ-21-capa-silver/`](https://github.com/PrometheusQuant/prometheus-platform/tree/develop/specs/PQ-21-capa-silver),
   antes de escribir el código.

## Comparación con el flujo actual (sobre PQ-21)

| Aspecto | Flujo actual | Con las plantillas de Spec Kit |
|---|---|---|
| Criterios de aceptación | 4 casillas en Jira | 8 escenarios *Dado / Cuando / Entonces*, cada uno convertible en test |
| Casos límite | No se pedían | La sección obligatoria hizo aparecer 3 que faltaban (símbolo sin datos, cambio ms → µs dentro de un símbolo, intervalo de funding inválido) |
| Criterios de éxito medibles | Implícitos | SC-001..004 explícitos (tiempo, escala, cobertura) |
| Trazabilidad para la defensa | Comentario en Jira | Documento versionado junto al código y revisado en el PR |
| Coste | ~10 min | ~25 min |
| Ramas | `feature/PQ-<n>-…` | El script crea `001-nombre`, que **choca** con GitFlow y con GitHub for Jira |
| Tareas | Commits atómicos y Jira | `tasks.md` duplica Jira: dos fuentes de verdad |
| Skills del agente | — | 10 skills en `.claude/` que se superponen con nuestras reglas |

## Decisión

**Adoptar en parte: solo las plantillas, solo en historias de 5 puntos o más.**

- Para cada historia de ≥ 5 puntos se escriben `specs/PQ-<n>-<nombre>/spec.md` y `plan.md` con el
  formato de las plantillas (en español), en el mismo PR que el código.
- **No** se instala la CLI `specify`, ni sus scripts, ni sus skills en el repositorio.
- **No** se usa `tasks.md`: las tareas siguen en Jira y en los commits.
- **Jira es la fuente de verdad del estado.** `specs/` guarda solo el diseño.
- La "constitución" de Spec Kit ya existe: `CONTRIBUTING.md`, los ADR y la Definición de Terminado.

## Consecuencias

- Positivas: criterios de aceptación que se convierten directamente en tests, casos límite
  pensados antes de programar y evidencia versionada para el capítulo 3 y el code review del
  capítulo 9.
- Negativas: unos 15 minutos más por historia grande y un documento más que mantener.
- Qué la revertiría: que las specs se desactualicen respecto al código en dos sprints seguidos. Se
  revisa en la retrospectiva del Sprint 3.
