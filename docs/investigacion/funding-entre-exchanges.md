# Funding de Binance frente a Bybit y OKX (PQ-79)

- **Ticket:** PQ-79 (carril de Boris) · **Fecha:** 2026-11-22 · **Tipo:** comparación descriptiva
- **Periodo:** solo el de desarrollo, hasta el 2024-06-30. **No evalúa ninguna estrategia:** eso
  exige su propio pre-registro (H4, PQ-94).
- **Se reproduce con:**

    ```bash
    uv run pq ingest --source bybit funding --symbol <S> --start 2020-01 --end 2024-06
    uv run pq silver build --symbol <S> --exchange bybit
    uv run pq research exchanges      # data/research/exchanges/summary.json
    ```

## Por qué

El capítulo 6 mostró que la quiebra del exchange domina el riesgo del carry. Repartir el capital
entre exchanges es la mitigación natural (H4), y también la alternativa si Binance no habilitara
futuros en Bolivia (PQ-17). Antes de pre-registrar nada, hay que saber si el funding de los otros
exchanges se parece al de Binance.

## Datos

- **Bybit:** historia completa por su API pública (`/v5/market/funding/history`), guardada en bronze
  con su propia fuente (`source=bybit_api`) y en silver con el mismo esquema que Binance
  (`silver/funding/exchange=bybit/`). Empieza cuando Bybit listó cada perpetuo: los meses
  anteriores salen como «no publicados».
- **OKX:** su API pública **solo guarda unos 3 meses** de funding (verificado el 2026-11-22). **No
  cubre el periodo de desarrollo**, así que no entra en la comparación. Una descarga histórica de
  OKX, si existe con licencia compatible, queda **por verificar**.

## Resultado (Binance frente a Bybit, en las liquidaciones comunes)

Tasas anualizadas con el intervalo de cada liquidación.

| Símbolo | Liquidaciones comunes | Desde | Mediana Binance | Mediana Bybit | Media Binance | Media Bybit | Correlación | Bybit paga más |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 4.675 | 2020-03-25 | 10,9 % | 10,9 % | 14,4 % | 16,8 % | 0,66 | 39 % |
| ETHUSDT | 4.046 | 2020-10-21 | 10,9 % | 10,9 % | 16,8 % | 19,3 % | 0,76 | 40 % |
| SOLUSDT | 3.365 | 2021-06-29 | 10,9 % | 10,9 % | -24,9 % | -23,0 % | 0,90 | 42 % |
| BNBUSDT | 3.293 | 2021-06-29 | 0,0 % | 5,5 % | -9,3 % | -6,7 % | 0,78 | 62 % |
| XRPUSDT | 3.433 | 2021-05-13 | 10,9 % | 10,9 % | 9,3 % | 14,0 % | 0,66 | 44 % |

## Lectura

- **La mediana es el dato útil.** En casi todos los símbolos se ancla en el **10,95 %** anual
  (0,01 % cada 8 h), la tasa por defecto del contrato, en los dos exchanges. La media se la llevan
  episodios extremos: SOL en noviembre de 2022 (colapso de FTX) llegó a −2 % cada 2 h en Binance.
- **Se parecen, pero no son iguales:** la correlación de las tasas va de 0,66 a 0,90. Bybit paga más
  que Binance en torno al 40 % de las liquidaciones, salvo en BNB (62 %), donde además su mediana es
  más alta (5,5 % frente a 0,0 %).
- **Para H4:** repartir entre Binance y Bybit no sacrifica nivel de funding en mediana y diversifica
  el riesgo de contraparte. Cuánto aporta neto de costes es justo lo que debe medir su pre-registro.

Las cifras salen de `data/research/exchanges/summary.json`. La ejecución quedó registrada como
descriptiva (no cuenta en N) en `docs/estrategias/ensayos/boris.jsonl`.
