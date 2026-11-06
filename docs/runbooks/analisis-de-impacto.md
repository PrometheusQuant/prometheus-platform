# Análisis de impacto en el negocio (BIA)

Cuánto tiempo puede estar caído cada proceso antes de que el daño sea inaceptable (MTPD), en cuánto
tiempo queremos recuperarlo (RTO) y qué lo protege. Sigue la ISO 22301, adaptado a un equipo de dos
con menos de 1.000 USD.

> Hoy solo existen los procesos de datos y de investigación. Los del proceso live se definen ahora
> para diseñar el kill-switch y las alertas (PQ-7, PQ-8) desde el principio.

| Proceso | Impacto si se cae | MTPD | RTO | Protección que existe | Protección planeada |
|---|---|---|---|---|---|
| **Ingesta histórica** (`pq ingest`) | Bajo: el histórico no cambia y se puede reintentar | 7 días | 1 día | Idempotente; reintentos con backoff; checksum | Ingesta diaria orquestada (PQ-22) |
| **Silver, research y simulación** | Bajo: se regenera desde bronze | 7 días | 1 día | Reconstrucción determinista (`pq silver build`); semillas fijas | Respaldo de bronze fuera de la laptop |
| **Proceso live con posición abierta** | Medio: el carry está cubierto, pero el short puede liquidarse en una subida brusca sin rebalanceo | 4 h | 1 h | — | Heartbeat, kill-switch y rebalanceo automático (PQ-7) |
| **Alertas** | Alto mientras haya posición: sin alertas, nadie se entera de lo anterior | 1 h | 30 min | Logs JSON | Telegram (PQ-38) y heartbeat del propio canal |
| **Claves de API** | Crítico si se filtran | 0 (prevenir) | 15 min para revocar | Sin permiso de retiro; `SecretStr`; gitleaks | Lista blanca de IP al tener servidor fijo |
| **Custodia en el exchange** | Crítico: quiebra o congelamiento de retiros | No aplica (no se recupera) | No aplica | — | Límite de capital por exchange calibrado con la [simulación](../investigacion/2026-11-05-simulacion-carry.md) (probabilidad de quiebra de equilibrio: 0,40 % anual) |
| **Dashboard** (PQ-34) | Bajo: es de consulta | 7 días | 1 día | — | Imagen Docker reproducible |
| **CI/CD** | Bajo: frena los cambios, no la operación | 3 días | 1 día | GitHub Actions; `make check` en local | — |

## Riesgos principales y mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Quiebra del exchange (tipo FTX) | Baja, pero no despreciable | Pérdida total de lo depositado | Límite por exchange; retirar lo que no opera; diversificar exchanges |
| Liquidación del short por una subida brusca | Media en altcoins | Pérdida de la pata corta | Apalancamiento 1x; rebalanceo al 10 %; alerta de margen |
| Filtración de claves | Baja | Operaciones no autorizadas (sin retiro) | Sin retiro; gitleaks; `.env` fuera de git; revocación en 15 min |
| Datos de mercado corruptos o atrasados | Media | Decisiones con información falsa | Checksum en bronze; checks de silver; alerta por datos viejos (planeado) |
| Pérdida de la laptop | Baja | Se pierde el lakehouse local | Se regenera desde Data Vision; el código está en GitHub |
