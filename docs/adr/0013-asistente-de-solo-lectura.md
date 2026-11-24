# ADR-0013: un asistente de LLM que solo explica (y no contradice ADR-0005)

- **Estado:** Aceptada
- **Fecha:** 2026-11-22
- **Ticket:** PQ-90

## Contexto y problema

Para la feria, el jurado debería poder preguntarle al bot de Telegram «¿por qué no hay posición
abierta hoy?» y recibir una respuesta con el estado real. ADR-0005 ordena las estrategias y deja
las capas de ML y de agentes de LLM **para después** de las estrategias base. Hay que decidir si un
asistente con la API de Claude choca con esa decisión.

## Decisión

Un asistente **de solo lectura** en el bot (`/pregunta`), con la API de Claude y tres herramientas
que solo leen archivos: el estado del paper, las decisiones recientes y las evaluaciones.

- **No decide ni opera.** No hay herramientas de órdenes, de bróker ni de kill-switch. El registro
  de herramientas es cerrado: cualquier otro nombre devuelve un error y no ejecuta nada. El módulo
  no importa ni el bróker ni el kill-switch, y una prueba lo verifica sobre su código fuente.
- **Coste acotado:** registra el coste de cada consulta y para al superar un límite diario.
- **Se aloja junto al bot** (Messages API con el bucle de herramientas en el propio proceso): las
  herramientas leen archivos locales del paper (diario, heartbeat, artefactos), que una sesión de
  Managed Agents en la nube no vería sin publicarlos.

## Por qué no contradice ADR-0005

ADR-0005 trata de **estrategias de inversión**: qué decide las posiciones y en qué orden se
construye. El asistente no decide ni influye en ninguna posición: explica lo que ya decidieron las
reglas pre-registradas. Es una interfaz de lectura, como el dashboard, no una capa de decisión.

## Consecuencias

- **Positivas:** el jurado pregunta en lenguaje natural y la respuesta sale de los datos reales, sin
  que nadie del equipo tenga que traducir.
- **Negativas y riesgos:**
  - el modelo puede equivocarse al explicar; el prompt le pide no inventar cifras y usar las
    herramientas, pero la fuente de verdad sigue siendo el dashboard;
  - hace falta una clave de la API en el `.env`, con coste (acotado por el límite diario).
- **Qué la revertiría:** dar al asistente cualquier capacidad de escritura. Eso sería un agente que
  opera y exigiría su propio ADR, posterior a las estrategias base, como dice ADR-0005.
