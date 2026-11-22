# Checklist go/no-go para capital real (TRL 6, PQ-104)

Qué tiene que cumplirse **antes** de poner un solo dólar real en una estrategia. No se opera con
dinero real en este semestre: este documento deja escrito el criterio para cuando llegue el momento.

**Reglas:**

- **La decisión es del titular, nunca de un agente.** Un agente puede actualizar el estado de cada
  criterio con su evidencia, pero no puede marcar GO ni firmar.
- **Sin evidencia, no se cumple.** Cada criterio dice cómo se verifica: un comando, un artefacto o
  un documento. «Creo que sí» no cuenta.
- **Todos o ninguno.** Basta con un criterio sin cumplir para que la decisión sea NO-GO.
- **Se revisa de nuevo** cada vez que se cierra uno de sus tickets bloqueantes y, en cualquier
  caso, antes de cada aumento de capital.

## Criterios

| # | Criterio | Cómo se verifica | Estado al 22-nov-2026 |
|---|---|---|---|
| 1 | **Acceso y comisiones reales verificados** desde la cuenta: futuros USDⓈ-M habilitados para Bolivia y comisiones VIP 0 iguales o menores que las del modelo | [Binance](binance.md) §3 completado por el titular (PQ-17) | ❌ Pendiente: PQ-17 en curso |
| 2 | **Holdout de H2 aprobado**, abierto una sola vez, con las correcciones de KE-014 y KE-016: los cuatro gates y un CAGR neto mayor que el 4 % | Evaluación de PQ-50 y su fila en el registro de ensayos | ❌ Pendiente: PQ-50 bloqueado por PQ-17 |
| 3 | **Presupuesto positivo** para la estrategia: con CVaR ≤ 5 % y la probabilidad de quiebra supuesta, el optimizador le asigna capital | `uv run pq research budget`: el presupuesto de la estrategia es mayor que 0 % | ❌ Hoy asigna **0 %** al carry H2 (100 % en efectivo) |
| 4 | **30 días seguidos de paper trading**: runner sano al menos el 95 % del tiempo, sin incidentes abiertos, y el retorno de esos 30 días dentro de la banda p5–p95 del Monte Carlo para ese plazo | Diario y heartbeat (`pq report public`), alertas del vigilante, [incidentes](../runbooks/incidentes.md) | ❌ Paper desde el 13-nov, intermitente (corre en la laptop) y sin operaciones todavía. La banda de 30 días aún no la calcula `pq research simulate`: hay que agregarla |
| 5 | **Kill-switch probado en Demo**: el simulacro del runbook contra el entorno Demo del exchange, con las órdenes canceladas y las posiciones cerradas verificadas **en el exchange** | [Kill-switch](../runbooks/kill-switch.md), sección «Simulacro» | ❌ Solo probado con el bróker simulado; falta el adaptador Demo (PQ-52) |
| 6 | **Control de exposición con órdenes pendientes** corregido antes de usar un bróker asíncrono | PQ-119 cerrado, con su prueba | ❌ PQ-119 pendiente |
| 7 | **Servidor 24/7** con vigilante, alertas y respaldos cifrados cada hora | PQ-57 cerrado; [respaldos](../runbooks/respaldos.md) con el cron activo en el servidor | ⚠️ Respaldos listos y probados (PQ-73); falta el servidor (PQ-57) |
| 8 | **Claves de API** solo de lectura y trading, **sin permiso de retiro** y con lista blanca de la IP del servidor | Pantalla de la clave en el exchange, revisada por el titular (no se sube captura) | ❌ No hay claves ni IP fija todavía |
| 9 | **Situación tributaria resuelta**: qué se declara y cómo, para ganancias en un exchange extranjero | `tributacion.md` (PQ-27) | ❌ PQ-27 pendiente |
| 10 | **Límite de capital por exchange** fijado con la probabilidad de quiebra de equilibrio | `uv run pq research budget` (tope por exchange, [ADR-0012](../adr/0012-presupuesto-de-capital-con-cvar.md)) | ✅ Implementado: tope de 12,5 % del capital en Binance con la quiebra supuesta del 2 % anual |
| 11 | **Capital máximo inicial** decidido por el titular: un monto cuya pérdida total sea aceptable, porque la quiebra del exchange no se recupera | Este documento, en la sección de la decisión | ❌ Sin fijar. Tope técnico actual: `PQ_RISK_MAX_NOTIONAL_TOTAL_USD` = 1.000 USD; la pregunta de investigación asume menos de 1.000 USD |

**Resumen al 22-nov-2026:**

- Se cumple 1 de 11 criterios; uno más está a medias.
- Con lo que hay hoy, el estado técnico **no permite GO**.
- Aunque se cumplieran los bloqueantes operativos (1, 2 y 4 a 9), el criterio 3 seguiría en contra.
  El propio sistema dice que, con el riesgo de contraparte supuesto, conviene más la stablecoin.
  Es la misma conclusión del informe final (el exceso sobre el 4 % no es significativo) y de la
  simulación (el óptimo es 0 % en carry).

## Cómo se reevalúa

1. Cuando se cierra un ticket bloqueante (PQ-17, PQ-50, PQ-52, PQ-57, PQ-119 o PQ-27), se actualiza
   su fila con la evidencia: el enlace al PR, el artefacto o el comando y su salida.
2. Se vuelve a correr `uv run pq research budget` con los datos del holdout. Si la estrategia sigue
   en 0 %, la respuesta es NO-GO aunque el resto esté en verde.
3. El titular completa la sección siguiente. Un GO se registra en el mismo PR que lo actualiza, y
   el capital empieza por el mínimo fijado en el criterio 11.

## Decisión del titular

| Campo | Valor |
|---|---|
| Fecha | ____ |
| Decisión | GO / NO-GO |
| Estrategia y exchange | ____ |
| Capital inicial (USD) | ____ |
| Criterios cumplidos (con su evidencia) | ____ de 11 |
| Firma | David Andrés Quintela Saavedra: ____ |

Mientras esta tabla esté vacía, la decisión vigente es **NO-GO**.
