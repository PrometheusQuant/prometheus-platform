# Cómo contribuir

## Flujo de trabajo

Todo trabajo empieza con un ticket en Jira (proyecto **PQ**). **Sin ticket no se programa.**

```text
Backlog → To Do → Plan de implementación → In Progress → Code Review → Done
```

- **Plan de implementación:** antes de programar, el responsable escribe en el ticket un plan breve
  (qué módulos toca, cómo se probará). El compañero lo aprueba con un comentario.
- **Done** exige el PR fusionado y CI en verde (ver la [Definición de Terminado](docs/metodologia/definicion-de-listo-y-terminado.md)).

## Ramas (GitFlow simplificado)

| Rama | Uso | Protección |
|---|---|---|
| `main` | Versiones estables, etiquetadas (`v0.2.0`) | PR + CI + 1 aprobación |
| `develop` | Integración continua del sprint | PR + CI + 1 aprobación |
| `feature/PQ-<n>-<descripcion>` | Una historia o tarea | — |
| `fix/PQ-<n>-<descripcion>` | Corrección | — |
| `spike/PQ-<n>-<descripcion>` | Investigación con time-box | — |
| `hotfix/PQ-<n>-<descripcion>` | Corrección urgente sobre `main` | — |

### Cómo se fusiona cada PR

| PR | Método | Por qué |
|---|---|---|
| `feature/`, `fix/`, `spike/` → `develop` | **Squash** | Un commit por ticket en `develop` |
| Release `develop` → `main` y back-merge `main` → `develop` | **Merge commit** (nunca squash) | Con squash, `main` y `develop` dejan de compartir historial y cada release choca con el anterior |
| `hotfix/` → `main` | Merge commit, y después back-merge a `develop` | Ídem |

Las ramas nacen de `develop` (los `hotfix/` de `main`). La clave `PQ-<n>` en el nombre de la rama
hace que la app **GitHub for Jira** muestre la rama, los commits y el PR dentro del ticket.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/es/) + la clave de Jira. El hook de
`commit-msg` rechaza mensajes que no cumplan el formato.

```text
<tipo>(<ámbito>): <descripción en imperativo> PQ-<n> [comandos de smart commit]

feat(data_platform): ingesta de funding rates desde Data Vision PQ-12
fix(domain): rechazar velas sin zona horaria PQ-15 #comment validación UTC añadida
test(research): CV purgada con embargo PQ-21 #time 2h
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`.

Los *smart commits* (`#comment`, `#time`, `#<transición>`) solo funcionan si el email de tu
`git config user.email` coincide con tu usuario de Jira.

## Antes de abrir un PR

```bash
make check   # lint, tipos estrictos, límites de arquitectura y tests con cobertura ≥ 80 %
```

Título del PR: el mismo formato que los commits, con la clave `PQ-<n>`.

## Decisiones de arquitectura

Toda decisión difícil de revertir se documenta como ADR en [`docs/adr/`](docs/adr/) usando la
[plantilla](docs/adr/0000-plantilla.md), en el mismo PR que la implementa.
