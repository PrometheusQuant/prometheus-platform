# Prueba de usabilidad con usuarios no técnicos (cap. 7.2, PQ-76)

- **Ticket:** PQ-76 · **Evidencia de:** el ítem 7.2 del mapa académico («panel navegable por un
  usuario no técnico»)
- **Estado:** protocolo listo; **sesiones pendientes** (las hacen David o Boris con 3 personas).
  Las tablas de resultados se llenan aquí al terminar.

## Objetivo

Comprobar si una persona **sin formación técnica ni financiera** puede responder, sola y con el
dashboard, las preguntas que se haría antes de invertir. Las tareas y el criterio de éxito se fijan
**antes** de las sesiones, igual que un pre-registro: así no se ajustan a lo que salga.

## Participantes

- **3 personas** sin formación técnica, por ejemplo familiares o amigos que no estudian
  ingeniería, economía ni finanzas, y que no hayan visto el proyecto.
- **Sin datos personales:** se identifican como P1, P2 y P3. Solo se anota el rango de edad
  (18–30, 31–50, 51+) y si alguna vez invirtieron (sí o no).
- **Consentimiento verbal** antes de empezar: la sesión dura unos 15 minutos, se puede parar cuando
  quieran y no se graba la pantalla ni la voz.

## Preparación (5 minutos)

1. Dashboard abierto en http://localhost:8501 (modo normal, **no** `?modo=feria`: el recorrido
   guiado daría las respuestas).
2. Pestaña inicial: «Inicio: ¿cómo va?» (desde el rediseño de PQ-124, 2026-11-23, antes de cualquier sesión).
3. Un cronómetro (el del celular) y esta página impresa o en otra pantalla para anotar.
4. Para Power BI (opcional, si hay tiempo): el informe de [Power BI](dashboard-power-bi.md) abierto
   en la página principal.

## Guion del moderador

> «Gracias por ayudarnos. No te estamos evaluando a ti: estamos evaluando el tablero. Si algo no se
> entiende, es culpa del tablero. Te voy a hacer 4 preguntas; búscalas en la pantalla y dime en voz
> alta lo que vas pensando. Yo no te voy a ayudar, salvo que pasen 3 minutos en una tarea.»

- **No señales** dónde está la respuesta ni corrijas. Si la persona pregunta, devuelve la pregunta:
  «¿dónde crees que estaría?».
- A los **3 minutos** en una tarea se da por no completada y se pasa a la siguiente.
- Anota las frases textuales que delatan confusión: valen más que la nota.

## Las 4 tareas (fijadas antes de las sesiones)

| # | Pregunta para la persona | Dónde está la respuesta | Éxito si… |
|---|---|---|---|
| T1 | «¿Esta estrategia gana más que dejar el dinero en algo que paga un 4 % al año?» | «¿Y si invierto?» (capital mediano frente a la stablecoin al 4 % y P(ganarle a la stablecoin)) o «¿Funciona?» (CAGR frente al 4 %) | Dice que en el desarrollo rinde algo más que el 4 %, pero que no siempre le gana (da una probabilidad o un rango) |
| T2 | «¿Qué te pasaría si el exchange (la casa de cambio) quiebra?» | «¿Y si invierto?» (control de quiebra) y «¿Qué riesgo hay?» (probabilidad de quiebra de equilibrio) | Entiende que se pierde lo que está en el exchange y que, con más riesgo de quiebra, la estrategia rinde menos que el 4 % |
| T3 | «¿Está invirtiendo ahora mismo? ¿Tiene algo comprado?» | «¿Cómo va en vivo?» (posiciones, estado del runner y del kill-switch) | Dice si hay posiciones abiertas y que el sistema está en marcha (o detenido) |
| T4 | «Si pongo 1.000 USD un año, ¿cuánto podría perder en un año malo?» | «¿Y si invierto?» (pérdida media del peor 5 % y P(perder dinero)) | Da una cifra de pérdida en el peor 5 % o la probabilidad de perder |

## Qué se mide

| Medida | Cómo |
|---|---|
| Éxito por tarea | **Sí** (sin ayuda), **parcial** (respuesta incompleta o tras una pista) o **no** (3 minutos sin respuesta) |
| Tiempo por tarea | Del final de la pregunta a la respuesta, en segundos |
| Comentarios | Frases textuales, sobre todo de confusión («¿qué es funding?», «no encuentro…») |
| Facilidad percibida | Al final: «del 1 al 5, ¿qué tan fácil fue encontrar las respuestas?» |

## Resultados (por completar)

| Participante | Rango de edad | ¿Invirtió antes? | T1 | T2 | T3 | T4 | Facilidad (1–5) |
|---|---|---|---|---|---|---|---|
| P1 | | | | | | | |
| P2 | | | | | | | |
| P3 | | | | | | | |

Celdas de tareas: `sí 45 s`, `parcial 120 s` o `no`.

**Comentarios textuales:**

- P1: …
- P2: …
- P3: …

## De los resultados a las mejoras

1. Por cada tarea, cuenta los «no» y los «parcial» y anota la frase de confusión más repetida.
2. Elige las **3 mejoras más importantes**: primero las que afectan a más personas, después las que
   bloquean la tarea entera.
3. Crea un ticket por mejora en Jira (proyecto PQ), con la etiqueta `ux` y el enlace a esta página.
4. Escribe aquí la conclusión en dos frases: qué se entiende bien y qué no.

**Mejoras (por completar):**

| # | Problema observado | Personas | Ticket |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
