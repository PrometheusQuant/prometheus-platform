# Auditoría de las fuentes de Binance Data Vision

- **Ticket:** PQ-19 (spike, time-box de 2 días)
- **Fecha de la auditoría:** 2026-10-23 (datos publicados hasta 2026-09-30; `metrics` hasta 2026-10-22)
- **Reproducible con:** `uv run python scripts/audit_data_vision.py --out auditoria.json`
- **Universo candidato:** BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT

## Resumen

Data Vision sirve como fuente histórica de la Estrategia 1 (carry) y de la 2 (tendencia). Se
descargaron y verificaron **2.903 archivos** (de 11.979 publicados para el universo, 150 MB
comprimidos) y **todos los checksums SHA-256 coinciden**. Se leyeron **≈1,1 millones de filas**,
muy por encima del mínimo de 5.000 registros del capítulo 1.5.

Encontramos cinco problemas de calidad reales. Ninguno impide usar la fuente, pero todos deben
tratarse en la capa silver (PQ-21):

1. **Spot cambió de milisegundos a microsegundos** en enero de 2025.
2. **Los CSV de futuros tienen cabecera solo desde enero de 2022.**
3. **El intervalo de funding no es fijo:** SOLUSDT pasó a 4 h y luego a 2 h en noviembre de 2022.
4. **`metrics` de BTCUSDT trae cada fila duplicada** entre 2020-09 y 2021-05.
5. **Hay huecos**: caídas del exchange en spot (2017–2019) y días ausentes en algunos archivos
   de futuros.

## Tabla de fuentes

Archivos, tamaño y filas suman los cinco símbolos; el rango es el de BTCUSDT. Un hueco es un
intervalo mayor que el paso esperado.

| Fuente | Ruta en Data Vision | Rango (BTCUSDT) | Granularidad | Archivos | Tamaño | Filas leídas | Problemas detectados | Decisión |
|---|---|---|---|---|---|---|---|---|
| Velas spot 1h | `data/spot/monthly/klines/<S>/1h/` | 2017-08-17 → 2026-09-30 | 1 h, mensual | 502 | 19,4 MB | 364.991 | µs desde 2025-01; 28 huecos en BTC (máx. 33 h, 2018-02-08), todos en 2017–2019 | **GO** |
| Velas spot 1d | `data/spot/monthly/klines/<S>/1d/` | 2017-08-17 → 2026-09-30 | 1 d, mensual | 502 | 1,0 MB | 15.229 | µs desde 2025-01 | **GO** |
| Velas USDⓈ-M 1h | `data/futures/um/monthly/klines/<S>/1h/` | 2020-01-01 → 2026-09-30 | 1 h, mensual | 396 | 14,1 MB | 288.289 | Cabecera solo desde 2022-01; SOL y XRP sin datos 2022-02-26 → 03-01 y 2022-04-01 → 04-03 | **GO** |
| Velas USDⓈ-M 1d | `data/futures/um/monthly/klines/<S>/1d/` | 2020-01-01 → 2026-09-30 | 1 d, mensual | 396 | 0,8 MB | 12.013 | Igual que 1h | **GO** |
| Funding rate | `data/futures/um/monthly/fundingRate/<S>/` | 2020-01-01 → 2026-09-30 | Por liquidación, mensual | 396 | 0,4 MB | 36.143 | Intervalo variable (SOL: 8 h → 4 h → 2 h → 8 h); `calc_time` con jitter de milisegundos; solo archivos mensuales | **GO** |
| Premium index 1h | `data/futures/um/monthly/premiumIndexKlines/<S>/1h/` | 2020-01-01 → 2026-09-30 | 1 h, mensual | 396 | 6,4 MB | 287.612 | 5–6 huecos por símbolo (máx. 97 h, 2021-07-24 → 07-28) | **GO con reservas** |
| Metrics (OI, ratios) | `data/futures/um/daily/metrics/<S>/` | 2020-09-01 → 2026-10-22 | 5 min, diario | 9.391 | 108,2 MB | 93.311 (muestra) | Duplicados en BTC hasta 2021-05; el resto del universo empieza en 2021-12; ~2.000 archivos por símbolo | **GO condicional** |

`metrics` se auditó con una muestra: el día 1 de cada mes más el último día publicado (315
archivos). Las demás fuentes se auditaron completas.

## Hallazgos en detalle

### 1. Unidad de los timestamps en spot

Desde el archivo `2025-01`, las velas spot usan **microsegundos** (16 dígitos) en `open_time` y
`close_time`. Antes usaban milisegundos (13 dígitos). Los futuros siguen en milisegundos.

```text
BTCUSDT-1h-2025-01.csv → 1735689600000000,93576.00000000,...   (µs)
BTCUSDT-1h-2021-12.csv → 1638316800000,56978.06,...            (ms)
```

**Tratamiento:** normalizar a UTC en silver según el número de dígitos, nunca según la fecha del
archivo. Un join entre spot y perp sin normalizar desalinea todo 2025–2026.

### 2. Cabeceras en futuros

Las velas y el premium index de USDⓈ-M tienen fila de cabecera desde `2022-01`. Los archivos
anteriores no tienen cabecera. Los de funding y `metrics` siempre la tienen.

```text
BTCUSDT-1h-2021-12.csv → 1638316800000,56978.06,57715.00,...                (sin cabecera)
BTCUSDT-1h-2022-01.csv → open_time,open,high,low,close,volume,close_time,...  (con cabecera)
```

**Tratamiento:** detectar la cabecera por contenido (primera celda no numérica) y asignar los
nombres canónicos de columna. No se puede asumir un formato fijo por fuente.

### 3. El intervalo de funding no es constante

| Símbolo | Intervalos observados |
|---|---|
| BTC, ETH, BNB, XRP | Siempre 8 h |
| SOL | 8 h → **4 h** (2022-11-09 20:00) → **2 h** (2022-11-10 04:00) → 8 h (2022-11-18 16:00), durante la caída de FTX |

El archivo trae la columna `funding_interval_hours`. Además, `calc_time` lleva milisegundos de
desfase (p. ej. `16:00:00.002`).

**Tratamiento:** anualizar el funding con el `funding_interval_hours` de cada fila, nunca con un
"× 3 × 365" fijo. Redondear `calc_time` a la hora de liquidación y guardar el original. En
periodos de estrés, un carry calculado con 8 h fijas subestima lo que se paga.

Estadísticos descriptivos, solo para caracterizar la fuente: el funding de BTCUSDT fue negativo
en el **14,0 %** de las liquidaciones y el de ETHUSDT en el 13,8 %. Los extremos por liquidación
fueron ±0,30 % en BTC, −0,36 %/+0,38 % en ETH y **−2,0 %** en SOL (noviembre de 2022).

### 4. Filas duplicadas en `metrics`

Cada fila de `BTCUSDT-metrics-*` aparece **dos veces** entre 2020-09-01 y 2021-05-31: 576 filas
para 288 marcas de 5 minutos. Desde 2021-06-01 hay 288 filas únicas por día. ETH, SOL, BNB y XRP
solo tienen `metrics` desde 2021-12-01.

**Tratamiento:** deduplicar por `(symbol, create_time)` en silver, con un check que falle si dos
filas duplicadas tienen valores distintos. Las features que usen el universo completo solo pueden
empezar en 2021-12.

### 5. Huecos

- **Spot, 2017–2019:** 28 huecos en BTCUSDT (127 velas de 1h ausentes; el mayor, de 33 h, el
  2018-02-08). Coinciden con mantenimientos y caídas del exchange de esos años. Son ausencias
  reales de mercado y **no se imputan**.
- **USDⓈ-M, SOL y XRP:** faltan del 2022-02-26 al 2022-02-28 y del 2022-04-01 al 2022-04-02
  (120 velas de 1h por símbolo). BTC y ETH no tienen ese hueco, así que parece un problema del
  archivo mensual y no del mercado. **Pendiente:** contrastar con los archivos diarios y la API
  REST en PQ-21.
- **Premium index:** 5–6 huecos por símbolo, el mayor de 97 h (2021-07-24 → 07-28). Una señal
  de basis calculada con esta fuente tiene que tolerar huecos o calcularse con las velas spot y perp.

### 6. Latencia de publicación

Las velas y el funding se publican en archivos **mensuales**: el 2026-10-23, el último disponible
es `2026-09`. Para operar en vivo (paper o real), el mes en curso tiene que venir de la API REST
(`/fapi/v1/fundingRate`, `/api/v3/klines`) o de los archivos diarios de velas. No hay archivos
diarios de funding.

## Decisiones

| Fuente | Decisión | Condición |
|---|---|---|
| Velas spot (1h, 1d) | **GO** | Normalizar µs/ms; no imputar los huecos de 2017–2019 |
| Velas USDⓈ-M (1h, 1d) | **GO** | Cabecera variable; verificar los días ausentes de SOL y XRP en 2022 |
| Funding rate | **GO** | Usar `funding_interval_hours`; el mes en curso, desde REST |
| Premium index 1h | **GO con reservas** | Solo como señal auxiliar; la base principal se calcula con las velas spot y perp |
| Metrics (OI, ratios) | **GO condicional** | Deduplicar y usar desde 2021-12; el carry v1 no la necesita (overlays, épica PQ-12) |

**Consecuencias para PQ-20 (ingesta bronze):** se ingieren tal cual (texto, sin transformar) las
velas spot y USDⓈ-M y el funding mensual. Las correcciones de este informe se aplican en silver
(PQ-21), con un check por hallazgo.

**Consecuencias para PQ-18 (pre-registro):** el periodo común de spot, perp y funding para BTC y
ETH empieza el **2020-01-01**. SOL empieza en 2020-09, BNB en 2020-02 y XRP en 2020-01-06.
