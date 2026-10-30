# Polymarket: elegibilidad desde Bolivia y costes

- **Ticket:** PQ-26 · **Fecha de consulta:** 2026-10-30
- **Estado:** verificado con fuentes primarias (documentación oficial y endpoint de geobloqueo)

## 1. ¿Bolivia está restringida?

**No.** Bolivia (`BO`) no aparece en ninguna de las tres listas de la
[documentación oficial de geobloqueo](https://docs.polymarket.com/developers/CLOB/geoblock):

| Lista oficial | Ejemplos | ¿Bolivia? |
|---|---|---|
| Bloqueo total (ni abrir ni cerrar) | Irán, Siria, Cuba, Corea del Norte, Crimea, Donetsk, Luhansk | No |
| Solo cierre, web y API | EE. UU., Reino Unido, Francia, Alemania, Brasil, **Argentina**, Venezuela, Nicaragua… | No |
| Solo cierre, solo web | Irlanda, Japón, Países Bajos, Corea del Sur… | No |

**Prueba directa.** El endpoint oficial `GET https://polymarket.com/api/geoblock`, consultado desde
la máquina de desarrollo (IP boliviana), respondió el 2026-10-30:

```json
{"blocked": false, "country": "BO", "region": "C"}
```

**Atención regional:** Argentina y Brasil, los vecinos, están en *solo cierre*. Argentina ordenó un
bloqueo nacional en 2026 ([The Block](https://www.theblock.co/post/393877/argentina-orders-nationwide-block-of-polymarket-as-scrutiny-of-prediction-markets-grows-report)).
La regulación de los mercados de predicción se está endureciendo en la región, así que esto hay
que volver a verificarlo antes de operar (riesgo regulatorio, ver el PESTEL).

**Vacío legal en Bolivia:** la RD BCB 082/2024 habilitó la compraventa de criptoactivos, pero no hay
una norma boliviana específica sobre mercados de predicción. Una guía de terceros señala ese vacío
([startpolymarket](https://startpolymarket.com/countries/bolivia/), secundaria). No es asesoría legal.

## 2. Costes

Fuente: [Polymarket, Fees](https://docs.polymarket.com/polymarket-learn/trading/fees) (oficial, consultada el 2026-10-30).

| Concepto | Coste |
|---|---|
| Orden *maker* (añade liquidez) | **0** (los makers nunca pagan) |
| Orden *taker* | `fee = C × feeRate × p × (1 − p)`; feeRate: cripto 0,07, deportes 0,05, finanzas/política/tecnología 0,04, geopolítica 0 |
| Depósitos y retiros | 0 en Polymarket (los intermediarios pueden cobrar) |
| Programa de reembolsos a makers | Se reparte entre el 15 % y el 25 % de las comisiones taker, según la categoría |

**Implicación para la Estrategia 3 (provisión de liquidez):** operar como *maker* no paga comisión y
además recibe reembolsos. Eso apoya el diseño de ADR-0005: proveer liquidez en lugar de tomarla.
Como la comisión taker es máxima en p = 0,5 y tiende a 0 en los extremos, el sesgo favorito-longshot
(precios cerca de 0 o de 1) también se puede explotar con poco coste.

## 3. Pendiente

- Probar la API CLOB con una wallet de prueba y un monto mínimo cuando empiece la épica PQ-11.
- La tributación de las ganancias se trata junto a la de Binance (PQ-27).
