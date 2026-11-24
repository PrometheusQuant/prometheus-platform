# Datos de Polymarket: ingesta y silver

- **Ticket:** PQ-92 · **Base:** [spike PQ-78](../investigacion/2026-11-24-spike-datos-polymarket.md)
  y [pre-registro PQ-87](../estrategias/04-polymarket/pre-registro.md)
- **Código:**
    - `adapters/polymarket.py`: cliente de las API públicas;
    - `data_platform/polymarket.py`: bronze y silver;
    - `api/polymarket_cli.py`: los comandos `pq polymarket`.

## Cómo se ingiere

```bash
pq polymarket mercados --desde 2023-01 --hasta 2026-10   # catálogo de mercados cerrados (≥ 1.000 USD)
pq polymarket silver                                      # silver de mercados
pq polymarket precios --hilos 8                           # serie diaria de cada resultado
pq polymarket silver                                      # ahora también los precios
pq polymarket operaciones --hilos 8                       # operaciones (Data API v2)
```

- **Sin claves:** todo sale de endpoints públicos.
- **Idempotente.** Un mes ya guardado se salta.
    - `mercados` vuelve a descargar los últimos 3 meses, porque sus mercados pueden cerrarse
      después (`--refrescar-desde` lo cambia).
    - `precios` y `operaciones` solo repiten un mes con `--forzar`.
- **Un mes con algún fallo no se escribe:** queda como «FALLÓ» y se reintenta en la próxima
  ejecución. El comando sale con código 1.
- **Las operaciones tienen prisa.** La Data API solo cubre unos tres años móviles (spike §3): lo que
  no se guarda ahora se pierde. `--max-paginas` (50 por defecto, de 1.000 operaciones) acota los
  mercados muy líquidos.
- **Ritmo medido el 2026-11-24**, con los precios de marzo de 2024 (826 resultados): 6 min 15 s en
  serie y 1 min 19 s con 8 hilos, con el mismo bronze. Esos 8 hilos quedan lejos del límite
  documentado de 1.000 peticiones cada 10 s.

## Dónde queda

```text
bronze/source=polymarket/dataset=markets/year=YYYY/month=MM/markets.parquet
bronze/source=polymarket/dataset=prices/fidelity=1440/year=YYYY/month=MM/prices.parquet
bronze/source=polymarket/dataset=trades/year=YYYY/month=MM/trades.parquet
silver/polymarket/markets.parquet
silver/polymarket/prices_1440.parquet
silver/_quality/polymarket-markets.json, polymarket-prices_1440.json
```

**Bronze** se particiona por el mes del `endDate` del mercado. Guarda todo como texto, con el JSON
crudo de cada registro, la URL exacta pedida (`request`) y el instante de la descarga
(`fetched_at`).

## Reglas del silver

| Regla | De dónde sale |
|---|---|
| Cada precio lleva `knowledge_time` = su instante | Point-in-time (AGENTS.md) |
| La resolución se conoce en `closedTime` (`resolution_known_at`). `resolution_asof(markets, t)` oculta los pagos antes de ese instante. `closedTime` es el fin de la resolución de UMA: en 45 mercados de marzo de 2024 que traen `umaEndDate`, los dos coinciden al segundo | Criterio de PQ-92 |
| El pago es el `outcomePrices` publicado, sin redondear (0,5 y los decimales del AMM incluidos) | Pre-registro §4 |
| `["0", "0"]`, sin `outcomePrices` o sin `closedTime` → `excluded_reason` | Pre-registro §3.4 y spike §4 |
| Un 0,5 que lleva ≥ 24 h sin moverse es relleno: `is_placeholder` y `price` nulo (queda `raw_price`) | Pre-registro §4 |
| Deportes = etiqueta `Sports` o `feeType` que empieza por `sports` | Pre-registro §3.3 |
| Un mercado descargado varias veces se queda con la descarga más reciente | Refrescos de `mercados` |
| `prices_asof(prices, t)` da el último precio válido de cada resultado conocido en `t` | Point-in-time |

Los checks que **detienen** la construcción son: pagos y precios fuera de [0, 1], mercados sin
`condition_id` y duplicados en conflicto (el mismo token e instante con dos precios). El resto se
**informa** en `_quality`:

- binarios, utilizables y excluidos por motivo;
- deportes;
- si hay al menos 5.000 mercados;
- rellenos, puntos posteriores a `closedTime` y tokens sin historial;
- puntos diarios a más de 1 minuto de las 00:00.

## Prueba con datos reales (2026-11-24)

Marzo de 2024, en un lakehouse temporal:

| Tabla | Resultado |
|---|---|
| Mercados | 413, todos binarios y utilizables; 19 de deportes |
| Precios diarios | 22.328 puntos de 820 resultados; 6 resultados del catálogo sin historial |
| Rellenos (0,5 sin moverse ≥ 24 h) | 524 puntos |
| Puntos posteriores a `closedTime` | 6 |
| Puntos a más de 1 min de las 00:00 UTC | 0: los puntos diarios llegan a las 00:00:02 o 00:00:03 |

Se cumplen los dos criterios de volumen de PQ-92: el universo desde 2023 tiene al menos 59.562
mercados (spike §1), y un solo mes da 22.328 precios.

## Problemas conocidos de los datos

- **Etiquetas de deportes con ruido.** Pasa en los dos sentidos:
    - «Musk vs. Zuck» lleva `Sports`;
    - una apuesta sobre un partido de la NCAA solo lleva `All`.

  Son las etiquetas de hoy, no las de la fecha de entrada (pre-registro §9).
- **Qué es `p`.** No se sabe si es el último precio negociado o el punto medio del libro (spike §2).
- **Comisiones históricas.** Falta verificar las unidades de `takerBaseFee`/`makerBaseFee` y desde
  cuándo está activo `feesEnabled`. El pre-registro permite una enmienda con las comisiones
  verificadas **antes** del primer backtest.
- **Coincidencia del punto diario con el precio por minuto.** Se comprobó en 14 puntos (pre-registro
  §4). La comprobación sobre todo el silver necesita la serie por minuto y queda para PQ-93.
