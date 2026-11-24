# Datos desactualizados (SEV-2)

## Cuándo aplica

- **Alerta en Telegram** `paper_data_stale` (ERROR): la liquidación de funding que tocaba no
  apareció en los 30 minutos siguientes a su hora.
- El heartbeat y `/estado` muestran «liquidación de las AAAA-MM-DD HH:MM UTC atrasada».
- Para los precios: `market_stream_fallback` repetido, si el websocket se queda congelado.

## Qué hace el sistema solo (PQ-98)

- **Liquidaciones:** en cada ciclo, el runner compara la última liquidación conocida con la
  siguiente esperada (su hora más el intervalo del símbolo, 8 h en H2). Pasado
  `funding_max_delay` (30 min):
  - **ese símbolo deja de decidir:** no procesa liquidaciones ni toma decisiones nuevas hasta que
    llegue el dato. Las posiciones y el estado deseado vigentes se siguen reconciliando;
  - alerta **una sola vez** por atraso (`paper_data_stale`, ERROR) y deja el heartbeat en
    `ok: false`, así que el vigilante también avisa;
  - al llegar el dato lo procesa con normalidad y registra `paper_data_recovered`.
- **Precios:** un precio del websocket con más de 15 s no se usa; se pide a REST
  ([desconexión](desconexion-exchange.md)).
- **Lakehouse (research):** los checks de silver y del orquestador marcan los huecos; nada del
  research opera dinero.

## Pasos

1. **¿El dato existe en el exchange?** Mira la última liquidación publicada:

   ```bash
   curl -s "https://fapi.binance.com/fapi/v1/fundingRate?symbol=SOLUSDT&limit=1"
   ```

   - **Si `fundingTime` es la hora esperada**, el dato existe y no nos llega: es un problema
     nuestro (red, proceso). Sigue el runbook de [desconexión](desconexion-exchange.md).
   - **Si es la anterior**, el exchange se atrasó. No hay nada que hacer de nuestro lado: el runner
     espera y lo procesa cuando aparezca.
2. **Si el atraso supera las 4 h** (el MTPD del [BIA](analisis-de-impacto.md)) con posición
   abierta, evalúa cerrarla a mano o con el kill-switch: se está operando sin la información que
   la regla necesita.
3. **Si el exchange cambió el intervalo de funding del símbolo** (por ejemplo de 8 h a 4 h), el
   runner lo toma de la última liquidación y se ajusta solo. Regístralo en los
   [errores conocidos](errores-conocidos.md) si causó una alerta falsa.

## Cómo verificar

`/estado` vuelve a mostrar el runner sano, y en el diario aparece el `FundingSettled` de la
liquidación atrasada.

## A quién avisar

Al equipo por Telegram si el atraso supera la hora. Las alertas ya les llegan a los dos.

## Simulacros

| Fecha | Tipo | Resultado |
|---|---|---|
| 2026-11-22 | Prueba automática (`test_a_late_settlement_alerts_once_and_pauses_new_decisions`) con el runner y el bróker simulado reales | 31 min después de la hora esperada: ciclo no sano con «atrasada», una sola alerta ERROR en dos ciclos, sin decisiones nuevas. Al publicarse la liquidación: se procesa y se registra la recuperación. **Pendiente:** observarlo con el runner en Demo (PQ-52) |
