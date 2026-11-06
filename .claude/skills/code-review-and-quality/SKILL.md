---
name: code-review-and-quality
description: Revisión de código en seis ejes (corrección, legibilidad, arquitectura, seguridad, rendimiento y rigor de investigación) con etiquetas de severidad. Úsala antes de fusionar cualquier PR, al revisar código escrito por ti, por otro agente o por una persona, después de corregir un error, o cuando pidan revisar un diff o un PR, aunque venga pegado en el chat. También sirve de guía para las revisiones humanas del equipo.
---

# Revisión de código y calidad

Adaptada de `code-review-and-quality` de [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
(MIT). Cambios:

- un sexto eje de rigor de investigación (CRISP-ML(Q));
- las capas de import-linter del proyecto;
- las reglas de Python, mypy y uv;
- las etiquetas en español;
- la política de dependencias adaptada a los grupos de Dependabot.

## Criterio de aprobación

Aprueba un cambio cuando **mejora claramente la salud del código**, aunque no sea perfecto. No
bloquees un cambio porque no está escrito como lo harías tú. Sí bloquea cuando rompe una regla del
protocolo de investigación o de seguridad: ahí no hay término medio.

Código generado por IA: **más escrutinio, no menos**. Es plausible y seguro de sí mismo incluso
cuando está mal.

## Proceso

1. **Contexto.** Lee el ticket PQ-<n>, sus criterios de aceptación y, si existe, `specs/PQ-<n>-*/`.
   ¿Qué debe cambiar y por qué?
2. **Primero los tests.** ¿Existen? ¿Prueban comportamiento y no detalles internos? ¿Cubren los
   bordes? ¿Fallarían si el código se rompe? Compruébalo con un experimento, no leyendo:
   - invierte una condición que el cambio agrega y corre las pruebas;
   - si siguen en verde, falta un caso: nómbralo;
   - restaura el archivo.
3. **La implementación**, archivo por archivo, con los seis ejes.
4. **Clasifica** cada hallazgo con su severidad (abajo). Antes de reportarlo, verifica que los
   llamadores, guardas o tests no lo descarten. Separa los defectos que ya estaban de los que
   introduce este cambio. Cero hallazgos es un resultado válido.
5. **Verifica la verificación.** ¿Corrió `make check`? ¿`make e2e` si tocó el dashboard o el
   Dockerfile? ¿`make docs-build` si tocó docs? ¿Hay capturas si cambió algo visual? ¿La CI está en
   verde?

## Los seis ejes

### 1. Corrección
- ¿Cumple los criterios de aceptación del ticket?
- Bordes:
  - DataFrames vacíos;
  - huecos en series temporales;
  - zonas horarias (todo en UTC);
  - empates;
  - NaN;
  - el primer y el último periodo.
- ¿Se manejan los caminos de error? ¿Fallan en voz alta? Ver `debugging-and-error-recovery`.
- Errores de uno, ventanas que incluyen la observación actual, `shift` en la dirección equivocada.

### 2. Legibilidad y simplicidad
- Nombres claros y coherentes con el resto del módulo. Docstrings y comentarios en español.
- ¿Se puede hacer con menos líneas o menos conceptos? ¿La abstracción se gana su complejidad? No
  generalices antes del tercer caso de uso.
- Código muerto, variables sin uso o capas de compatibilidad sin motivo.
- ¿Se pegó un condicional nuevo a un flujo ajeno? Eso es un problema de diseño, no un detalle.

### 3. Arquitectura
- Capas: `api → adapters → strategies|portfolio_risk|execution|research → data_platform → ops → domain`.
  - `make arch` lo verifica.
  - Revisa también lo que import-linter no ve: lógica de negocio en `api/`, I/O en `domain/`.
- Los puertos nuevos van en `domain/ports.py` y sus implementaciones en `adapters/`.
- ¿Reutiliza el helper canónico existente o crea uno casi idéntico?
- ¿El refactor reduce complejidad o solo la mueve de sitio?
- ¿Un archivo supera unas ~1000 líneas por este cambio? Primero descompón.
- ¿Es una decisión difícil de revertir? Entonces falta el ADR en `docs/adr/`.

### 4. Seguridad
- Ningún secreto en código, tests, logs ni fixtures. En tests, los secretos falsos se construyen por
  concatenación.
- Datos externos tratados como no confiables y validados en el borde:
  - respuestas de Binance;
  - archivos de Data Vision (con checksum);
  - variables de entorno (pydantic-settings).
- Logs con información sensible pasan por `redact_text`.
- Claves de exchange sin permiso de retiro. El contenedor sigue en solo lectura con `cap_drop: ALL`.
- Dependencias nuevas: licencia compatible con Apache-2.0, mantenidas y sin CVE (`make audit`).

### 5. Rendimiento
- polars: preferir expresiones vectorizadas y `lazy`, nunca bucles de Python sobre filas grandes.
  DuckDB para consultas sobre el lakehouse.
- Nada de cargar todo el histórico en memoria si basta una partición.
- En backtests y Monte Carlo, ¿el coste crece con el número de configuraciones × simulaciones de
  forma razonable?

### 6. Rigor de investigación (CRISP-ML(Q))
Solo si el cambio toca `research/`, `strategies/`, features o resultados.
- **Pre-registro:**
  - ¿El cambio respeta `docs/estrategias/<n>/pre-registro.md`?
  - Si lo modifica, ¿hay una enmienda fechada?
- **N:**
  - ¿Toda ejecución nueva queda en el registro de experimentos?
  - ¿Se ajustó N en el Deflated Sharpe?
- **Costes:** ¿Se aplican `CostModel` (comisiones VIP0 y slippage) en cada lado y pata?
- **Point-in-time:**
  - ¿Los joins son as-of sobre `knowledge_time`?
  - ¿Alguna normalización, escalado o selección usa la muestra completa?
- **Holdout:**
  - ¿Algo lee datos desde 2024-07-01 para el carry?
  - Está cerrado hasta PQ-17 (enmienda 1.11).
- **Gates de la fase:** ¿Se cumplen o el descarte está documentado?
  Ver `docs/metodologia/definicion-de-listo-y-terminado.md`.
- **Resultados demasiado buenos:** exige que alguien intente refutarlos (`doubt-driven-development`)
  antes de aceptarlos.

## Bajar el listón es un hallazgo

Son **obligatorios**, salvo una justificación escrita en el PR:

- un `# type: ignore` o `# noqa` nuevo sin motivo en la misma línea;
- un `pytest.mark.skip` o `xfail` para que la CI pase;
- bajar `fail_under` en la cobertura o excluir archivos de ella;
- desactivar una regla de ruff, mypy o import-linter;
- tests borrados o debilitados (asserts menos estrictos) en un cambio que no es de tests.

## Severidad

| Prefijo | Significado | Qué hace el autor |
|---|---|---|
| **Crítico:** | Bloquea el merge: seguridad, pérdida de datos, fuga de información del futuro, protocolo violado | Corregir antes de fusionar |
| *(sin prefijo)* | Cambio requerido | Corregir o justificar por escrito |
| **Considera:** | Sugerencia | Opcional |
| **Nit:** | Estilo menor | Opcional |
| **FYI:** | Información | Nada |

Empieza por lo que importa: corrección, seguridad y rigor primero. Un problema estructural y diez
nits significa que la revisión es el problema estructural. Pocos comentarios con convicción valen
más que una lista larga.

Al marcar un problema estructural, propón la solución. Algunas posibles:

- reemplazar condicionales por un modelo tipado;
- separar la orquestación de la lógica;
- mover la lógica al módulo que la posee;
- reutilizar el helper canónico.

## Tamaño del cambio

- **~100 líneas:** bien.
- **~300 líneas:** aceptable si es un solo cambio lógico.
- **~1000 líneas:** divídelo, salvo borrados o refactors automáticos.

Un refactor y una funcionalidad nueva son dos PR.

## Dependencias

- Antes de agregar una: ¿la stdlib o lo que ya usamos lo resuelve? Cada dependencia es un pasivo.
- `uv add`, nunca a mano. Revisa el diff del `uv.lock`, no solo el del `pyproject.toml`.
- Las actualizaciones agrupadas de Dependabot se aceptan si la CI pasa. Si una falla, aísla el
  paquete culpable, por ejemplo con `uv lock --upgrade-package <pkg>` uno por uno, antes de fusionar.
- Un salto de versión mayor: lee las notas de migración.

## Cómo dejar la revisión en GitHub

```bash
gh pr diff <n>                                  # leer el cambio
gh pr review <n> --comment --body-file revision.md
gh pr review <n> --request-changes --body "..." # si hay hallazgos Crítico o requeridos
gh pr review <n> --approve --body "..."         # si no los hay
```

Para un comentario sobre una línea concreta, usa la pestaña *Files changed* en la web. Si la
revisión es posterior al merge, cada hallazgo requerido se convierte en un ticket con la etiqueta
`code-review` y el número del PR.

## Plantilla de revisión

```markdown
## Revisión: PR #<n> (PQ-<n>)

**Contexto:** <qué intenta hacer, en una línea>

### Hallazgos
- **Crítico:** <archivo:línea>: <problema> → <propuesta>
- <archivo:línea>: <problema> → <propuesta>
- **Considera:** ...

### Ejes revisados
- [ ] Corrección  - [ ] Legibilidad  - [ ] Arquitectura
- [ ] Seguridad   - [ ] Rendimiento  - [ ] Rigor (si aplica)

### Verificación del autor
- [ ] CI en verde  - [ ] `make check`  - [ ] `make e2e` / capturas si aplica

**Veredicto:** Aprobar / Pedir cambios
```

## Honestidad

- Nada de «LGTM» sin evidencia de revisión.
- No suavices un error real. Si tumba un backtest, dilo así.
- Cuantifica cuando puedas. Por ejemplo, «este join duplica filas cuando hay dos funding en la misma
  hora».
- Si el autor tiene más contexto y no está de acuerdo, decide con datos y no con preferencias.
- No aceptes «lo limpio después». Pide que se corrija ahora o que se abra un ticket.

## Verificación

- [ ] Todos los **Crítico** resueltos
- [ ] Los requeridos, resueltos o diferidos con justificación y ticket
- [ ] CI en verde
- [ ] La historia de verificación está escrita en el PR
- [ ] Dependencias nuevas revisadas: licencia, `uv.lock` y `make audit`
