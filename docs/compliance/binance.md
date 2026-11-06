# Binance: acceso desde Bolivia, comisiones y entornos de prueba

- **Ticket:** PQ-17
- **Estado:** parcial. La parte pública está verificada al 2026-10-23. La parte de la cuenta
  (KYC, productos habilitados y comisiones reales) la completa el titular desde su sesión.

!!! warning "Nunca en este documento"
    Capturas con nombre, documento, UID, saldo o claves. Solo se anota lo que dice la interfaz,
    por ejemplo *"Futuros USDⓈ-M: habilitado"*.

## 1. ¿Bolivia está restringida?

| Fuente | Qué dice | Calidad |
|---|---|---|
| [Binance: List of Prohibited Countries](https://www.binance.com/en/legal/list-of-prohibited-countries) | La página se renderiza con JavaScript y **no se pudo leer** automáticamente (2026-10-16 y 2026-10-23) | Primaria, no leída |
| [Resumen de Kevin Wu](https://kevin-wu.org/en/exchange-restricted-countries-en/) (revisado 2026-10-12) | La lista de Binance (actualizada 2026-01-05) incluye EE. UU., Canadá, Países Bajos, Cuba, Corea del Norte, Irán, Crimea, Donetsk y Luhansk. **Bolivia no aparece** | Secundaria |
| [Datawallet](https://www.datawallet.com/de/krypto/binance-geschützte-länder) (2026) | Restricciones en la UE desde el 2026-07-01 por MiCA y en territorios sancionados | Secundaria |
| RD BCB 082/2024 | Operar con activos virtuales es legal en Bolivia desde el 2024-06-25 (ver [nota de regulación](../investigacion/notas/acceso_regulacion_bolivia.md)) | Primaria (vía prensa) |

**Conclusión provisional:** no hay indicios de geobloqueo para Bolivia. La confirmación definitiva
es la sección 3: que la cuenta de un residente boliviano tenga los productos habilitados.

## 2. Comisiones del nivel VIP 0 (Regular)

Con menos de 1.000 USD de capital, la cuenta estará siempre en VIP 0.

| Producto | Maker | Taker | Descuento con BNB | Fuente |
|---|---|---|---|---|
| Spot | 0,100 % | 0,100 % | 25 % (≈ 0,075 %) | [Binance, fee schedule](https://www.binance.com/en/fee/schedule) (oficial, leída 2026-10-23) |
| Futuros USDⓈ-M | 0,020 % | 0,050 % | 10 % | Tasas: [Traders Union](https://tradersunion.com/brokers/crypto/view/binance/futures-fees/), [CryptoPotato](https://cryptopotato.com/binance-fees/) (secundarias). Descuento: [Binance, artículo de soporte](https://www.binance.com/es/support/articles/360033544231) (oficial) |

- La tabla oficial de futuros ([binance.com/en/fee/futureFee](https://www.binance.com/en/fee/futureFee))
  se renderiza con JavaScript y no muestra las tasas sin iniciar sesión.
- Una fuente secundaria da 0,04 % taker en futuros. Se toma **0,05 %**, el valor más conservador.
- El descuento de futuros solo se aplica si hay BNB **dentro de la cuenta de futuros USDⓈ-M**. Si
  el saldo no alcanza, la comisión se cobra en USDT sin descuento.

**Para el modelo de costes** del pre-registro del carry (PQ-18):
se usan las tasas sin descuento de BNB hasta que la sección 3 confirme las reales.

## 3. Verificación desde la cuenta (pendiente: titular)

Completar con la fecha de consulta. Si algo difiere de la sección 2, manda la cuenta.

| Comprobación | Dónde se ve | Resultado | Fecha |
|---|---|---|---|
| Nivel de KYC | Perfil → Verificación | _pendiente_ | |
| Spot habilitado | Trade → Spot | _pendiente_ | |
| Futuros USDⓈ-M habilitados (¿cuestionario o test?) | Derivados → Futuros USDⓈ-M | _pendiente_ | |
| Margin habilitado | Trade → Margin | _pendiente_ | |
| Comisión spot maker / taker real | Perfil → Panel → Nivel VIP / comisiones | _pendiente_ | |
| Comisión USDⓈ-M maker / taker real | Futuros → Comisiones | _pendiente_ | |
| Claves de Demo Trading creadas **sin permiso de retiro** | Demo Trading → Gestión de API | _pendiente_ | |

**Si los futuros USDⓈ-M no están habilitados:** crear un ticket para replantear la Estrategia 1
(otro exchange de la [nota de regulación](../investigacion/notas/acceso_regulacion_bolivia.md):
Bybit, OKX o Bitget no restringen Bolivia según fuentes secundarias).

## 4. Entornos de prueba

Binance migró sus testnets a **Demo Trading**: las claves se crean desde la cuenta principal, en el
modo demo, y no sirven en producción.

| Entorno | REST | WebSocket | Fuente |
|---|---|---|---|
| Spot, Demo Mode | `https://demo-api.binance.com/api` | `wss://demo-stream.binance.com/ws` (streams), `wss://demo-ws-api.binance.com/ws-api/v3` (API) | [Binance Spot API, Demo Mode](https://developers.binance.com/docs/binance-spot-api-docs/demo-mode/general-info) |
| Futuros USDⓈ-M, Demo | `https://demo-fapi.binance.com` | `wss://demo-fstream.binance.com` | [Binance USDⓈ-M, General Info](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info) |
| Futuros USDⓈ-M, producción | `https://fapi.binance.com` | — | ídem |

Reglas para las claves ([SECURITY.md](https://github.com/PrometheusQuant/prometheus-platform/blob/develop/SECURITY.md)):

1. Permisos: lectura y trading. **Nunca retiro.**
2. Lista blanca de IP en cuanto haya un servidor fijo.
3. Solo en el `.env` local (`PQ_BINANCE_API_KEY`, `PQ_BINANCE_API_SECRET`, `PQ_BINANCE_TESTNET=true`).
   La configuración rechaza el entorno `paper` si `PQ_BINANCE_TESTNET` no es `true` (PQ-15).
