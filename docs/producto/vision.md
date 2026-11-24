# Visión de producto

- **Ticket:** PQ-107 · **Fecha:** 2026-11-13 · **Responsable:** David Quintela
- **Enlaza con:** [Impact Mapping](../academico/impact-map.md) (PQ-43),
  [modelo de negocio](../academico/modelo-de-negocio.md) (PQ-44),
  [mapa de historias](mapa-de-historias.md) (PQ-108) y la [primera entrega](entregas/2026-11-13-mvp.md) (PQ-110)

## Visión en una frase

> **Para quien quiere invertir con estrategias cuantitativas en cripto sin engañarse a sí mismo,
> PrometheusQuant es una plataforma que solo deja avanzar una estrategia cuando la evidencia
> sobrevive a los costes reales, al sobreajuste y al riesgo, y que la opera primero en simulación,
> con frenos.**

A diferencia de los bots y las plataformas de backtest que muestran la curva más bonita,
PrometheusQuant cuenta **todos** los intentos, descuenta los costes reales y dice cuándo una
estrategia **no** sirve.

## Product Vision Board

| Bloque | Contenido |
|---|---|
| **Visión** | Decisiones de inversión cuantitativa basadas en evidencia que se puede auditar, no en capturas de rentabilidad |
| **Grupo objetivo** | El equipo cuantitativo, con capital propio, como operador; el profesor y el jurado como cliente evaluador; el inversor minorista como usuario que aprende y simula |
| **Necesidades** | Saber si una estrategia funciona de verdad, cuánto se puede perder, y operarla sin poner dinero en riesgo antes de tiempo |
| **Producto** | Lakehouse con datos point-in-time; investigación con protocolo (pre-registro, CPCV, Deflated Sharpe, PBO); simulación de riesgo; paper trading con riesgo, kill-switch y alertas; dashboard |
| **Objetivos del negocio** | Aprobar el proyecto integrador con evidencia trazable (cap. 1–9); decidir con datos si el carry H2 merece capital propio; dejar una plataforma que crezca a más estrategias |

**Cómo sabremos que funciona.** Son criterios que se pueden comprobar; los valores actuales salen
de los artefactos enlazados.

| Pregunta | Indicador | Dónde se ve |
|---|---|---|
| ¿Decide con rigor? | Cada estrategia tiene pre-registro, N contado en el registro compartido y gates G1–G4 | [Evaluación del carry](../estrategias/01-carry/evaluacion.md), `pq research registro resumen` |
| ¿Es reproducible? | La CI pasa en cada PR; los resultados citan el commit | GitHub Actions; [errores conocidos](../runbooks/errores-conocidos.md) |
| ¿Opera de forma segura? | Paper sin dinero real, con riesgo pre-trade, kill-switch y alertas; el diario permite reconstruir cada decisión | Pestaña «¿Cómo va en vivo?», [runbook de paper trading](../runbooks/paper-trading.md) |
| ¿Lo entiende un no técnico? | Tareas completadas en la prueba de usabilidad (PQ-76) | Pendiente: MMP |
| ¿Merece capital propio? | H2 en el holdout con comisiones reales (PQ-50) y paper estable | Pendiente: PQ-17 y PQ-50 |

## Cliente y personas

| Persona | Rol | Qué quiere | Qué le duele | Cómo la sirve hoy el producto |
|---|---|---|---|---|
| **El profesor** (y el jurado) | **Cliente**: compra el incremento con su evaluación y decide qué sigue | Ver un producto funcionando, rastrear cada afirmación hasta su evidencia y evaluar el rigor | Rentabilidades sin respaldo, demos que solo funcionan en la laptop del alumno, documentación desconectada del código | Entrega por incrementos con notas y demo; cada cifra enlaza a un artefacto, un PR o un commit |
| **El inversor minorista** | **Usuario** que aprende y simula. No compra señales: el modelo de negocio no aprueba ofrecerlas a terceros | Entender cuánto podría ganar o perder con su capital, y si «el carry» es seguro | Promesas de rentabilidad, jerga, no saber qué riesgo está corriendo | Pestañas «¿Y si invierto?» (Monte Carlo con su capital y horizonte) y «¿Qué predice hoy?», en lenguaje llano |
| **El equipo cuantitativo** (David y Boris) | **Operador**: investiga, decide y opera con capital propio | Probar hipótesis rápido sin hacerse trampa, operar en paper y dormir tranquilo | Sobreajuste, olvidar ensayos, costes ocultos, procesos que se caen sin avisar | Protocolo y registro de ensayos compartido; runner con riesgo, kill-switch, vigilante y alertas al grupo de Telegram |

## Value Proposition Canvas

Se hace para los dos segmentos que deciden: el **cliente** (profesor) y el **operador** (equipo).

### Perfil del cliente: el profesor

| Trabajos (*jobs*) | Frustraciones (*pains*) | Alegrías (*gains*) |
|---|---|---|
| Evaluar si el producto cumple lo prometido en cada incremento | Avances que no se pueden verificar | Ver la demo funcionando con datos reales |
| Calificar con una rúbrica por capítulos | Resultados que no se pueden reproducir | Rastrear capítulo → evidencia → commit |
| Decidir el alcance del siguiente incremento | Rentabilidades exageradas | Un equipo que dice qué **no** funciona y por qué |

### Mapa de valor para el profesor

| Productos y servicios | Aliviadores de frustraciones | Creadores de alegrías |
|---|---|---|
| Entregas por incremento con notas y demo ([MVP 13-nov](entregas/2026-11-13-mvp.md)) | Cada cifra cita su artefacto; las limitaciones se declaran (KE-014, KE-016) | Demo en vivo: el runner decide con el funding real de Binance |
| Sitio de documentación y [mapa académico](../academico/README.md) | CI pública: lint, tipos, arquitectura, más de 380 pruebas y documentación estricta | El dashboard responde a las preguntas del jurado, una por pestaña |
| Jira y PR con revisión cruzada | El holdout está cerrado hasta verificar las comisiones | Decisiones honestas: H1 se descartó aunque su Sharpe era alto |

### Perfil del operador: el equipo cuantitativo

| Trabajos | Frustraciones | Alegrías |
|---|---|---|
| Formular y probar hipótesis | Sobreajuste y backtests que mienten | Saber cuánto pesa cada ensayo en N |
| Operar sin arriesgar capital | Procesos que mueren en silencio | Una alerta al móvil antes de que algo se rompa |
| Coordinar dos carriles con dos agentes de IA | Pisarse el código y contar mal los ensayos | Conectar una estrategia nueva sin tocar el núcleo |

### Mapa de valor para el operador

| Productos y servicios | Aliviadores | Creadores |
|---|---|---|
| Lakehouse y protocolo de investigación | Datos point-in-time; pre-registro; registro de ensayos compartido (PQ-112) | Deflated Sharpe y PBO calculados solos |
| Runner de paper (PQ-54) y monitoreo (PQ-55) | Riesgo pre-trade, kill-switch, reconciliación tras caídas, vigilante | Pestaña en vivo y resumen diario en Telegram |
| Puerto `Strategy` (PQ-113) y prueba de contrato | La paridad backtest ↔ paper se comprueba en la CI | Boris conecta la tendencia sin tocar el runner |

## Qué no es PrometheusQuant (por ahora)

- **No vende señales ni gestiona fondos de terceros.** Requeriría habilitación legal
  ([modelo de negocio](../academico/modelo-de-negocio.md), [compliance](../compliance/README.md)).
- **No opera con dinero real.** Antes deben cumplirse PQ-17 (comisiones reales), PQ-50 (holdout),
  PQ-104 (go/no-go) y la decisión expresa del titular.
- **No promete rentabilidad.** El carry es una prima por riesgo de cola: la decisión se toma
  frente al 4 % de una stablecoin, no frente a cero.
