# Glosario

## Mercado y trading

| Término | Definición |
|---|---|
| **Perpetuo** | Futuro sin vencimiento. Su precio se ancla al spot con pagos periódicos de funding |
| **Funding rate** | Pago entre largos y cortos de un perpetuo, cada 8 h (a veces 4 h o 2 h). En Binance, la base es 0,01 % por liquidación (10,95 % anual) |
| **Liquidación de funding** | Momento en que se cobra o se paga el funding |
| **Carry (cash-and-carry)** | Comprar spot y vender el perpetuo por el mismo nocional: se cobra el funding sin exposición al precio |
| **Basis** | Diferencia relativa entre el precio del perpetuo y el del spot |
| **Nocional** | Valor de mercado de una posición |
| **Apalancamiento 1x** | El nocional de cada pata es igual al capital que la respalda: no hay deuda |
| **Maker / taker** | Orden que añade liquidez (espera en el libro) o que la consume (se ejecuta al instante). El taker paga más comisión |
| **VIP 0** | Nivel de comisiones de Binance para cuentas pequeñas |
| **Stablecoin** | Criptomoneda que sigue al dólar (USDT, USDC). Su rendimiento por préstamo (~4 %) es nuestro *hurdle* |
| **Quiebra del exchange** | Riesgo de contraparte: perder lo depositado si el exchange cae (como FTX en 2022) |

## Datos

| Término | Definición |
|---|---|
| **Bronze, silver, gold** | Capas del lakehouse: crudo tal cual, validado y tipado, y features listas para modelar |
| **Point-in-time** | Usar cada dato solo desde el momento en que se pudo conocer |
| **`event_time` / `knowledge_time`** | Cuándo ocurrió un dato y cuándo se pudo conocer. Una vela de 1 h se conoce al cerrar |
| **Join as-of** | Unir a cada fila el último dato ya conocido en ese instante |
| **Idempotencia** | Ejecutar un proceso dos veces deja el mismo resultado (la ingesta no duplica) |
| **Checksum (SHA-256)** | Huella de un archivo; si no coincide con la publicada, el archivo se rechaza |
| **Data contract** | Esquema declarativo (pandera) que los datos deben cumplir entre capas |

## Investigación y validación

| Término | Definición |
|---|---|
| **Pre-registro** | Escribir hipótesis, reglas, ensayos y fechas antes de mirar resultados |
| **Holdout** | Tramo de datos reservado que se mira una sola vez, al final |
| **Ensayo (N)** | Cada configuración probada. Se cuentan todas en el registro de experimentos |
| **Sharpe** | Retorno medio entre volatilidad. Un carry cubierto lo infla porque su riesgo es de cola |
| **CAGR** | Rentabilidad anual compuesta |
| **CPCV** | Validación cruzada combinatoria purgada: prueba en muchas combinaciones de tramos sin fuga de información |
| **PBO** | Probabilidad de que la mejor configuración sea suerte |
| **Deflated Sharpe** | Sharpe corregido por el número de ensayos, la asimetría y la curtosis |
| **Walk-forward** | Entrenar con el pasado y probar con el futuro, avanzando en el tiempo |
| **AUC** | Capacidad de un clasificador de ordenar bien los casos (1 es perfecto, 0,5 es azar) |
| **Diebold-Mariano** | Prueba de si un pronóstico es significativamente más preciso que otro |

## Simulación

| Término | Definición |
|---|---|
| **Régimen** | Estado del funding: negativo (< 0), base (0–20 %) o alto (≥ 20 %) |
| **Cadena de Markov** | Modelo donde la probabilidad del estado siguiente depende solo del actual |
| **Semi-Markov** | Variante donde la duración de cada estado sigue su propia distribución, no una geométrica |
| **Block bootstrap** | Remuestrear bloques contiguos de la historia para conservar su dependencia temporal |
| **KS / χ²** | Pruebas de bondad de ajuste de una distribución a los datos |
| **VaR / CVaR 95 %** | Pérdida que solo se supera en el 5 % de los casos / pérdida media en ese 5 % |
| **Probabilidad de quiebra de equilibrio** | Riesgo anual de quiebra del exchange con el que el carry rinde igual que la stablecoin |

## Operación y gestión

| Término | Definición |
|---|---|
| **ADR** | Registro de una decisión de arquitectura y su porqué |
| **Error conocido (KEDB)** | Problema analizado, con su workaround mientras no hay solución definitiva (ITIL 4) |
| **MTPD / RTO** | Tiempo máximo tolerable de interrupción / objetivo de tiempo de recuperación (ISO 22301) |
| **Kill-switch** | Mecanismo que cancela órdenes y cierra posiciones ante un fallo |
| **PDCA** | Ciclo planificar, hacer, verificar, actuar |
