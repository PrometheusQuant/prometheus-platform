# Sospecha de insolvencia del exchange (PQ-96)

El capítulo 6 muestra que la **quiebra o el congelamiento del exchange** es el riesgo que domina al
carry: con un 2 % anual de probabilidad, el carry rinde menos que una stablecoin. El runner lo vigila
con señales públicas y actúa solo hasta cierto punto. Lo demás es manual y está aquí.

## Qué vigila el runner, cada 5 minutos

| Señal | Fuente pública (sin claves) | Alerta | Crítico |
|---|---|---|---|
| Estado del sistema | Binance `GET /sapi/v1/system/status` | No es «normal» | No escala sola |
| Prima de USDT frente a USDC | Binance `USDCUSDT`: `1 / precio − 1` | ±0,5 % | ±2 % |
| Spread del perpetuo BTCUSDT | Mark de Binance frente a la mediana de Bybit (mark) y OKX (último) | ±0,5 % | ±2 % |

- **Flujos netos y proof-of-reserves:** no hay una fuente pública estable y gratuita sin claves, así
  que no se automatizan. Se revisan a mano en la sección «Qué hacer».
- **Una señal que no responde** no cambia el nivel, pero queda en el log
  (`paper_counterparty_unknown`): «no se sabe» no es «todo bien».
- **Los umbrales son iniciales y conservadores.** En la lectura del 22-nov-2026, USDT estaba a −0,19 %
  frente a USDC y el spread del perpetuo a −0,006 %. Calibrarlos con episodios históricos (el
  descuento de USDT en mayo de 2022, el de FTX en noviembre de 2022) queda **por verificar**. Se
  cambian en `portfolio_risk/counterparty.Thresholds`.

## Qué hace el runner solo

| Nivel | Acción automática |
|---|---|
| Normal | Nada |
| **Alerta** | Alerta ERROR por Telegram (`paper_counterparty_alert`), `RiskLimitBreached` (`contraparte_alerta`) en el diario y **exposición a la mitad**: el carry recorta sus patas si superan en un 10 % el objetivo nuevo, y las otras estrategias dimensionan con la mitad de su presupuesto. El heartbeat muestra `"contraparte": "alerta"` |
| **Crítico** | **Kill-switch**: alerta CRITICAL y cierre de todas las posiciones. Es el único cierre total automático. Se rearma a mano ([runbook del kill-switch](kill-switch.md)) |

Al volver a la normalidad, el runner lo registra (`paper_counterparty_normal`) y deja de reducir.
**No vuelve a agrandar solo** las posiciones recortadas: crecen en la siguiente entrada o rebalanceo.

## Qué hacer a mano

**Con una alerta:**

1. Mira el motivo en Telegram o en el log (`paper_counterparty_alert`, campo `detail`).
2. Comprueba si es real o un fallo de una fuente:
    - el anuncio de Binance (pausas de retiro, mantenimiento): <https://www.binance.com/en/support/announcement>;
    - el precio de USDT en otros exchanges y en agregadores;
    - el proof-of-reserves de Binance y los flujos netos en un panel público.
3. Si la causa es inocua (por ejemplo, un mantenimiento programado), deja que el runner siga a la
   mitad: volverá solo a la normalidad.
4. Si hay dudas, **detén la estrategia** sin cerrar las demás: `uv run pq paper kill --strategy carry-h2
   --reason "sospecha de contraparte"`.

**Con el crítico, o con evidencia de insolvencia (retiros pausados sin explicación, noticias
creíbles):**

1. El kill-switch ya está activado: verifica con `uv run pq paper status` que las posiciones quedaron
   cerradas.
2. En una cuenta real (**no aplica al paper**): retira los fondos que no sean imprescindibles. El
   carry no justifica dejar capital en un exchange con dudas.
3. Deja constancia en el diario del equipo y en Jira: fecha, señales y decisión.
4. **No rearmes** hasta que la situación se aclare y el titular lo decida.

## Lo que este monitor no cubre

- Un congelamiento repentino sin señales previas (como FTX en sus últimas horas): para eso está el
  presupuesto con tope por exchange ([ADR-0012](../adr/0012-presupuesto-de-capital-con-cvar.md)).
- La quiebra de la stablecoin de margen por sí sola: la señal de USDT la delata, pero cerrar en USDT
  no la evita.
