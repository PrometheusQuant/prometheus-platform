# Plan: ejecución real en Binance Demo

- **Ticket:** PQ-52.
- **Spec:** [spec.md](spec.md).

## Diseño

```text
PaperRunner ──► Broker (puerto)
                 ├─ SimulatedBroker ─┐
                 └─ ExchangeBroker ──┴─► LedgerBroker (efectivo, posiciones, marcas, funding)
                        │
                        └─► ExecutionPort (puerto) ─► CcxtExecution ─► ccxt.binance (demo)
```

1. **`domain`:** `ExchangeFill` (cantidad neta, precio medio, comisión en USDT) y
   `ExecutionPort`.
2. **`adapters/simulated_broker.py`:** se extrae `LedgerBroker` con `_reference` y `_apply_fill`.
   El simulado solo calcula precio y comisión, sin cambiar el comportamiento ni el estado en
   disco.
3. **`adapters/ccxt_execution.py`:**
   - guarda de endpoints de prueba;
   - mapa de símbolos (`SOLUSDT-PERP` → `SOL/USDT:USDT`);
   - redondeo y mínimos;
   - reloj con margen;
   - `clientOrderId` determinista de 36 caracteres como máximo;
   - búsqueda antes de reenviar;
   - espera del fill (futuros responden `NEW`);
   - comisiones sumadas de las operaciones.
4. **`adapters/exchange_broker.py`:** `submit` con el fill real, `cancel_all` en el exchange y
   `reconcile`.
5. **`api/paper/compose.py` y CLI:** `--broker simulado|binance-demo`, `paper_dir(...)` por bróker,
   reconciliación al arrancar y CCXT importado de forma diferida.

## Pruebas

- **Doble en memoria de CCXT:**
  - comisión en el activo comprado;
  - espera del fill;
  - truncado y mínimos;
  - respuesta perdida sin duplicar, y reenvío si la orden no llegó;
  - secretos fuera de los errores;
  - resincronización del reloj;
  - posiciones y funding.
- **Doble del puerto:** el libro con fills reales, el reinicio, la reconciliación y la cancelación.
- **Composición:** carpetas por bróker, simulado por defecto, claves obligatorias y aviso de
  reconciliación.
- **Integración** (`-m demo`): ida y vuelta de 0,1 SOL en spot y en USDⓈ-M.
