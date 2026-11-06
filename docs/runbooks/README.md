# Runbooks

Procedimientos paso a paso para operar la plataforma, escritos para usarse bajo presión.
Cada runbook indica: cuándo aplica, pasos exactos, cómo verificar que funcionó y a quién avisar.

## Operación y continuidad

- [Errores conocidos (KEDB)](errores-conocidos.md): problemas analizados y su workaround.
- [Gestión de incidentes](incidentes.md): severidades, respuesta y post-mortem.
- [Dashboard de investigación](dashboard.md): abrirlo en local o con Docker.
- [Alertas a Telegram](alertas.md): configurar el bot y probar el canal.
- [Análisis de impacto (BIA)](analisis-de-impacto.md): MTPD y RTO por proceso, riesgos y mitigación.

## Runbooks pendientes

Previstos con la épica de riesgo y ejecución (PQ-7) y la de monitoreo (PQ-8):

- Arrancar y detener el proceso de paper trading / live.
- Activar el kill-switch y verificar que no quedan órdenes abiertas.
- Rotar una clave de API comprometida.
- Responder a una desconexión del exchange o a datos desactualizados.
- Restaurar desde backup.
