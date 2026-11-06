# ADR-0007: MkDocs Material para el sitio de documentación

- **Estado:** Aceptada
- **Fecha:** 2026-10-23
- **Ticket:** PQ-16

## Contexto y problema

La documentación (ADR, metodología, investigación, arquitectura) vive en Markdown dentro de
`docs/`. Evaluadores y compañeros necesitan leerla como un sitio navegable, con búsqueda y
diagramas, sin clonar el repositorio. El presupuesto es 0 USD.

## Opciones consideradas

1. **MkDocs + Material for MkDocs**, publicado en GitHub Pages.
2. **Zensical**, el sucesor de Material escrito por el mismo equipo.
3. Sphinx con MyST.

## Decisión

Opción 1, con una configuración que se mantiene compatible con Zensical.

- Material es la opción más madura para Markdown puro y renderiza Mermaid sin plugins extra,
  así que los diagramas C4 se versionan como texto.
- El 5 de noviembre de 2025 el equipo de Material anunció el **modo mantenimiento**: la 9.7 es la
  última versión con funcionalidades nuevas y los arreglos de errores y seguridad están
  comprometidos hasta noviembre de 2026
  ([anuncio](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)).
- Zensical lee el mismo `mkdocs.yml`, pero el 2026-10-23 sigue en versiones 0.0.x
  ([PyPI](https://pypi.org/project/zensical/)). Adoptarlo hoy sería apostar por una herramienta
  que aún no tiene versión estable.
- Sphinx está pensado para documentar APIs desde docstrings, y aquí casi todo el contenido es prosa.

MkDocs 2.0 no será compatible con Material: elimina el sistema de plugins y reescribe el de temas
([análisis del equipo de Material](https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/)).
Por eso la dependencia fija `mkdocs<2`.

Para que la migración sea barata, `mkdocs.yml` solo usa el tema y extensiones estándar de
Python-Markdown y pymdownx. No usa plugins de terceros.

## Consecuencias

- Positivas: sitio gratuito en GitHub Pages; `mkdocs build --strict` en CI detecta enlaces rotos;
  los diagramas se revisan en el diff del PR.
- Negativas y riesgos: Material dejará de recibir parches después de noviembre de 2026. Es un
  generador estático sin código en el servidor, así que el riesgo es bajo, pero existe.
- Qué la revertiría: que Zensical publique una versión estable que construya este sitio sin
  advertencias. Entonces se migra y se reemplaza este ADR.
