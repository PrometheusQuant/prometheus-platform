---
name: doubt-driven-development
description: Somete cada afirmación o decisión no trivial a una revisión adversarial con contexto fresco antes de darla por buena. Úsala antes de afirmar que no hay look-ahead, que el holdout sigue intacto, que N está bien contado, que un gate pasa o que algo es seguro; antes de una decisión de arquitectura con incertidumbre; antes de una acción irreversible (abrir el holdout, publicar a main, borrar datos, operar con dinero real); y al trabajar en código que no entiendes del todo.
---

# Desarrollo guiado por la duda

Adaptada de `doubt-driven-development` de [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
(MIT). Cambios: disparadores propios de la investigación cuantitativa; el revisor es un subagente
de Claude Code; la segunda opinión de otro modelo pasa de obligatoria a opcional y solo para
decisiones de alto impacto; se quitaron las referencias a personas del plugin.

## Por qué

Una respuesta segura no es una respuesta correcta. En una sesión larga, los supuestos se vuelven
«hechos» sin que nadie lo note. Ejemplo real: KE-008 se diagnosticó dos veces con seguridad y las
dos veces mal. En investigación el coste es mayor: una afirmación falsa como «no hay look-ahead»
invalida todos los resultados que se apoyan en ella, y el pre-registro no permite rehacerlos gratis.

## Cuándo aplica

Una decisión es **no trivial** si cumple al menos una de estas condiciones:

- Afirma una propiedad que ni mypy ni los tests verifican por sí solos:
  - **point-in-time**: ninguna feature usa datos posteriores a su `knowledge_time`;
  - **holdout intacto**: nada leyó datos de 2024-07-01 en adelante para H1/H2;
  - **N bien contado**: todas las ejecuciones están en el registro de experimentos (PQ-24);
  - **costes aplicados**: comisiones y slippage en cada lado y pata;
  - **un gate pasa**: DSR, PBO, t, Sharpe neto;
  - idempotencia, orden de eventos o ausencia de condiciones de carrera.
- Cruza un límite de capa (import-linter) o cambia un puerto de `domain/ports.py`.
- Es irreversible o difícil de revertir:
  - abrir el holdout;
  - release a `main`;
  - borrar o reescribir datos del lakehouse;
  - claves y órdenes reales.
- Su corrección depende de un contexto que el lector futuro no verá.

**No aplica** en estos casos:

- cambios mecánicos (renombrar, formatear, mover archivos);
- una instrucción clara del usuario;
- leer o resumir código;
- cambios de una línea con corrección evidente;
- ejecutar herramientas;
- si el usuario pidió explícitamente velocidad sobre verificación.

Si dudas de cada tecla, no entregas nada.

## Proceso

```text
Ciclo de duda:
- [ ] 1. AFIRMACIÓN: escribí qué afirmo y por qué importa
- [ ] 2. EXTRACCIÓN: aislé el artefacto y el contrato, sin mi razonamiento
- [ ] 3. DUDA: un revisor con contexto fresco intentó refutarlo
- [ ] 4. CONCILIACIÓN: clasifiqué cada hallazgo contra el texto del artefacto
- [ ] 5. PARADA: hallazgos triviales, 3 ciclos o el usuario dijo «adelante»
```

### 1. Afirmación

En dos o tres líneas:

```text
AFIRMACIÓN: las features de régimen del modelo de funding solo usan información
            disponible antes de cada predicción.
POR QUÉ IMPORTA: si hay fuga, las métricas del capítulo 5 son falsas.
```

Si no puedes escribirla así de corta, tienes una intuición, no una decisión.

### 2. Extracción

El revisor necesita el **artefacto** (el diff, la función, la consulta, la tabla de resultados) y el
**contrato** (qué debe cumplir: la sección del pre-registro, el criterio del gate, la regla de capas).
No le pases tu razonamiento: si le das conclusiones, te devuelve validación. Sí incluye la evidencia
que pueda contradecirte: un llamador, un test, un join. Si el artefacto no cabe en una lectura,
descompónlo.

### 3. Duda

Lanza un subagente nuevo (herramienta `Agent`, tipo `general-purpose`) con este prompt. Pásale el
artefacto y el contrato, **nunca la afirmación**:

```text
Revisión adversarial. Encuentra qué está mal en este artefacto.
Asume que el autor está demasiado seguro. Busca:
- supuestos no declarados
- casos borde sin manejar (vacíos, huecos de datos, zonas horarias, empates)
- fugas de información del futuro (joins, ventanas, normalizaciones con toda la muestra)
- estado compartido o acoplamiento oculto
- formas en que se viola el contrato
- convenciones del repositorio que rompe
No valides. No resumas. Encuentra problemas, o di explícitamente que no
encontraste ninguno tras una revisión exhaustiva, y qué revisaste.

ARTEFACTO: <rutas de archivo y líneas, o el diff>
CONTRATO: <texto del pre-registro, del gate o de la regla>
```

Da rutas en lugar de pegar archivos enteros: el subagente puede leer el repo.

**Segunda opinión de otro modelo** (Gemini CLI, Codex CLI o una revisión manual externa): es
opcional. Ofrécela solo antes de una acción irreversible, como abrir el holdout, la primera orden
real o un release con cambios de ejecución. Nunca ejecutes un CLI externo sin la autorización
explícita del usuario para ese comando concreto, y siempre en modo de solo lectura, con el prompt
por stdin desde un archivo. En contextos no interactivos se omite y se dice que se omitió.

### 4. Conciliación

La salida del revisor es información, no veredicto. Relee el artefacto ante cada hallazgo y
clasifícalo. La primera clase que encaje gana:

1. **Contrato mal entendido**: el contrato era ambiguo. Corrígelo y repite.
2. **Válido y accionable**: cambia el artefacto y repite.
3. **Compromiso válido**: es real, pero corregirlo cuesta más que aceptarlo. Documéntalo en el PR o
   en `evaluacion.md` para que el usuario lo vea.
4. **Ruido**: es correcto con un contexto que el revisor no tenía. Pregúntate si ese contexto
   debía estar en el contrato.

### 5. Parada

Para en cualquiera de estos casos:

- la siguiente vuelta solo trae hallazgos triviales o ya considerados;
- se completaron 3 ciclos (escala al usuario; no hagas un cuarto por tu cuenta);
- el usuario dijo «adelante».

Si tras 3 ciclos siguen saliendo problemas sustantivos, el artefacto no está listo, y eso también es
un resultado.

## Dónde queda constancia

Para afirmaciones de investigación, resume el ciclo en la descripción del PR o en el
`evaluacion.md` de la estrategia: qué se afirmó, qué encontró el revisor y cómo se clasificó.
Esa constancia es parte de la evidencia del protocolo.

## Señales de alarma

- Lanzar un revisor para un renombrado.
- Aceptar lo que dice el revisor sin releer el artefacto.
- Preguntar «¿está bien?» en lugar de «encuentra problemas».
- Pasarle la afirmación al revisor.
- **Teatro de la duda**: dos o más ciclos con hallazgos sustantivos y ninguno clasificado como
  accionable. Estás validando, no dudando.
- Dudar solo después de fusionar. Eso es revisión de código, no esta skill.

## Relación con otras skills

- `code-review-and-quality`: revisión al final del PR. Esta skill actúa durante el trabajo y
  decisión por decisión.
- `debugging-and-error-recovery`: si el revisor encuentra un fallo real, pasa a localizarlo y
  corregirlo.
- Un test que falla primero (TDD) ya es una duda concreta para afirmaciones de comportamiento.
