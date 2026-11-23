# Runbooks

Procedimientos paso a paso para operar la plataforma, escritos para usarse bajo presión.
Cada runbook indica: cuándo aplica, pasos exactos, cómo verificar que funcionó y a quién avisar.

## Operación y continuidad

- [Errores conocidos (KEDB)](errores-conocidos.md): problemas analizados y su workaround.
- [Gestión de incidentes](incidentes.md): severidades, respuesta y post-mortem.
- [Dashboard de investigación](dashboard.md): abrirlo en local o con Docker.
- [Orquestación (Dagster)](orquestacion.md): actualizar el lakehouse, ver linaje y checks, activar el schedule diario.
- [Alertas a Telegram](alertas.md): configurar el bot y probar el canal.
- [Observabilidad](observabilidad.md): métricas del runner, Prometheus, Grafana y Alertmanager, por túnel SSH.
- [Monitoreo de drift](drift.md): datos, modelo y desempeño frente a lo esperado; qué hacer con una alerta.
- [Análisis de impacto (BIA)](analisis-de-impacto.md): MTPD y RTO por proceso, riesgos y mitigación.
- [Kill-switch](kill-switch.md): detener toda la operación, verificar, rearmar y el simulacro.
- [Oracle Cloud](oracle-cloud.md): crear la cuenta Always Free y la VM del paper trading.
- [Paper trading](paper-trading.md): arrancar y detener el runner, leer su estado y reiniciarlo.
- [Cadena de suministro](cadena-de-suministro.md): verificar la firma y el SBOM de la imagen antes de desplegar; secretos del servidor con sops + age.
- [Respaldos del paper trading](respaldos.md): respaldo cifrado cada hora, restauración y simulacro.
- [Clave de API comprometida](clave-comprometida.md): detener, revocar en 15 min y rotar (SEV-1).
- [Desconexión del exchange](desconexion-exchange.md): qué hace el runner solo y cómo diagnosticar (SEV-2).
- [Datos desactualizados](datos-desactualizados.md): liquidaciones atrasadas, pausa automática y alerta (SEV-2).

## Runbooks pendientes

Previstos con la épica de riesgo y ejecución (PQ-7) y la de monitoreo (PQ-8):

- Arrancar y detener el proceso live (con capital real; ver [go/no-go](../compliance/go-no-go-capital-real.md)).
