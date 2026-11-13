# Runbooks

Procedimientos paso a paso para operar la plataforma, escritos para usarse bajo presión.
Cada runbook indica: cuándo aplica, pasos exactos, cómo verificar que funcionó y a quién avisar.

## Operación y continuidad

- [Errores conocidos (KEDB)](errores-conocidos.md): problemas analizados y su workaround.
- [Gestión de incidentes](incidentes.md): severidades, respuesta y post-mortem.
- [Dashboard de investigación](dashboard.md): abrirlo en local o con Docker.
- [Orquestación (Dagster)](orquestacion.md): actualizar el lakehouse, ver linaje y checks, activar el schedule diario.
- [Alertas a Telegram](alertas.md): configurar el bot y probar el canal.
- [Análisis de impacto (BIA)](analisis-de-impacto.md): MTPD y RTO por proceso, riesgos y mitigación.
- [Kill-switch](kill-switch.md): detener toda la operación, verificar, rearmar y el simulacro.
- [Oracle Cloud](oracle-cloud.md): crear la cuenta Always Free y la VM del paper trading.
- [Paper trading](paper-trading.md): arrancar y detener el runner, leer su estado y reiniciarlo.

## Runbooks pendientes

Previstos con la épica de riesgo y ejecución (PQ-7) y la de monitoreo (PQ-8):

- Arrancar y detener el proceso live.
- Rotar una clave de API comprometida.
- Responder a una desconexión del exchange o a datos desactualizados.
- Restaurar desde backup.
