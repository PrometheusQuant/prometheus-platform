# Especificación: ejecución real en Binance Demo detrás de un puerto

- **Ticket:** PQ-52.
- **Rama:** `feature/PQ-52-binance-demo`.
- **Fecha:** 2026-11-24.
- **Estado:** aprobada.
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008).
- **Entrada:**
  - la historia PQ-52;
  - la decisión del spike PQ-51 ([ADR-0014](../../docs/adr/0014-ccxt-detras-de-los-puertos-para-ejecutar.md):
    CCXT detrás de los puertos propios);
  - las claves Demo del titular (PQ-17).

## Escenarios

### Historia 1: el carry opera con órdenes reales y dinero ficticio (P1)

1. **Dado** `pq paper run --broker binance-demo`, **cuando** el carry decide entrar, salir o
   rebalancear, **entonces**:
   - cada pata va a Binance Demo como orden de mercado (spot o USDⓈ-M);
   - el libro registra el precio medio, la cantidad neta y la comisión **reales**;
   - el slippage es la diferencia con la valoración del ciclo.
2. **Dado** un corte de red al enviar, **cuando** se reintenta, **entonces** primero se busca la
   orden por su `clientOrderId` y solo se reenvía si el exchange no la tiene (idempotencia).
3. **Dada** una cantidad que, redondeada al `stepSize`, queda por debajo de la cantidad o el
   nocional mínimos, **entonces** la orden se rechaza antes de enviarla (`OrderTooSmallError`).

### Historia 2: el paper simulado no se toca (P1)

1. **Dado** el runner simulado 24/7 en `data/paper/`, **cuando** arranca el de Binance Demo,
   **entonces** usa `data/paper-binance-demo/`, con su propio diario, estado, bloqueo y
   kill-switch (`pq paper kill --broker binance-demo`).

### Historia 3: nunca producción, nunca secretos en los logs (P1)

1. **Dado** `PQ_ENVIRONMENT=live`, **entonces** el runner no arranca (validación existente).
2. **Dado** el adaptador de Binance, **entonces** todas las URLs de la API apuntan a `demo-`; si
   alguna no, no arranca.
3. **Dado** un error del exchange, **entonces** el mensaje sale sin las claves (`redact_text` más
   el borrado de las claves literales).

### Historia 4: el libro cuadra con el exchange (P2)

1. **Dado** el arranque del runner Demo, **entonces** compara el libro con el exchange en los
   instrumentos operados y avisa (`paper_reconcile_gaps`) si no cuadran. La decisión es humana.

## Requisitos

- **RF-1:** puerto `ExecutionPort` en `domain/ports.py` con saldo, precio, orden de mercado,
  cancelación, posiciones y funding cobrado.
- **RF-2:** adaptador `CcxtExecution` en `adapters/`; ninguna otra capa importa CCXT.
- **RF-3:** el bróker de exchange reutiliza la contabilidad del simulado (`LedgerBroker`), con el
  mismo formato de estado.
- **RF-4:** reloj sincronizado cada 10 minutos con un margen de 1 s (el reloj de WSL va atrasado).
- **RNF-1:** pruebas contra dobles en memoria y una prueba de integración marcada `demo`, que
  solo corre con claves y `PQ_DEMO_INTEGRATION=1`.

## Fuera de alcance

- Calibrar costes con los fills reales: PQ-95.
- Bybit testnet: PQ-100 (mismo adaptador, otra instancia de CCXT).
- Usar el funding registrado por el exchange en el libro. El libro lo calcula con la tasa
  publicada, como el simulado; `funding_income` permite contrastarlo.
