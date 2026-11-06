# Kill-switch: detener toda la operación

**Cuándo aplica.** Pérdida inesperada, una pata sin cubrir, un comportamiento extraño del bot, datos
desactualizados, un incidente en el exchange, o cualquier duda. **Ante la duda, se activa.** Parar
de más cuesta poco; no parar puede costar el capital.

## Qué hace al activarse

1. Cancela todas las órdenes abiertas en el exchange.
2. Bloquea toda orden que **aumente** la exposición. Las que la **reducen** se siguen permitiendo, y
   el runner cierra las posiciones con ellas.
3. Escribe `KillSwitchTripped` en el diario (`data/paper/diario.jsonl`) con el motivo y la vía.
4. Envía una alerta **CRITICAL** a Telegram ([alertas](alertas.md)).
5. Deja el archivo bandera `data/paper/KILL_SWITCH`. **Sobrevive a un reinicio:** el proceso vuelve
   a arrancar detenido.

Se activa **solo** al superar uno de estos límites:
- pérdida diaria mayor que `PQ_RISK_MAX_DAILY_LOSS`;
- apalancamiento por encima de `PQ_RISK_HARD_LEVERAGE`;
- una pata sin cubrir durante más de `PQ_RISK_IMBALANCE_GRACE_SECONDS`;
- equity no positiva.

!!! warning "La CLI y el archivo no tocan el exchange"
    `pq paper kill` y el archivo bandera solo **marcan** la detención. El runner revisa la bandera en
    **cada ciclo** (`KillSwitch.observe`): cancela las órdenes, cierra posiciones y, si la activación
    no estaba en el diario (archivo creado a mano), la registra y envía la alerta. Si el runner está
    caído, no hay nadie operando, pero tampoco nadie cancelando: revisa las órdenes abiertas en
    Binance.

## Las tres formas de activarlo a mano

| Vía | Comando | Cuándo |
|---|---|---|
| CLI | `uv run pq paper kill --reason "motivo"` | Con acceso al servidor o a la laptop |
| Archivo bandera | `touch data/paper/KILL_SWITCH` | Si la CLI no responde: basta con que exista el archivo. El nombre es **exacto**, sin extensión (algunos editores de Windows agregan `.txt`) |
| Telegram | `/kill` (PQ-72) | Desde el celular, cuando esté disponible |

## Verificar que funcionó

```bash
uv run pq paper status        # debe decir ACTIVADO, con el motivo
```

- No quedan órdenes abiertas: compruébalo en Binance → Órdenes abiertas (Demo Trading).
- Las posiciones se cerraron, o se están cerrando: compruébalo en la pestaña de operación del
  dashboard (PQ-55).
- Llegó la alerta CRITICAL a Telegram.

## Rearmar

Solo se rearma **después** de entender la causa. Si fue un incidente, regístralo según
[incidentes](incidentes.md).

```bash
uv run pq paper kill --reset --confirm --by "nombre"
```

`--confirm` y `--by` son obligatorios: el rearme queda en el diario con el autor (`KillSwitchReset`).

## Simulacro (antes de operar y después de cada cambio en riesgo o ejecución)

El test `tests/unit/portfolio_risk/test_risk_and_kill_switch.py::test_simulacro_del_runbook`
automatiza estos mismos pasos en cada PR:

1. Simular una pérdida del 2,5 % en el día (por encima del límite del 2 %).
2. Comprobar que se activa solo y que cancela las órdenes abiertas.
3. Comprobar que se rechaza una orden que aumenta la exposición.
4. Comprobar que se aceptan las órdenes de cierre de todas las patas.
5. Reiniciar el proceso y comprobar que **sigue activado**.
6. Rearmar a mano con autor, y comprobar el diario: `RiskLimitBreached`, `KillSwitchTripped` y
   `KillSwitchReset`.

**En el servidor**, antes de la feria, se hace también a mano:

- `pq paper kill` con el runner en marcha;
- verificar en Binance Demo que no quedan órdenes;
- rearmar.

Anota la fecha del simulacro en la tabla de abajo.

| Fecha | Dónde | Resultado | Quién |
|---|---|---|---|
| 2026-11-06 | Test automatizado (CI) | OK | Agente (PQ-53) |

## Límites configurables (`.env`)

| Variable | Por defecto | Qué limita |
|---|---|---|
| `PQ_RISK_MAX_NOTIONAL_SYMBOL_USD` | 500 | Nocional por símbolo (suma de las patas) |
| `PQ_RISK_MAX_NOTIONAL_TOTAL_USD` | 1.000 | Nocional bruto total |
| `PQ_RISK_MAX_LEVERAGE` | 1,0 | Apalancamiento: rechaza órdenes nuevas por encima |
| `PQ_RISK_HARD_LEVERAGE` | 1,5 | Apalancamiento que activa el kill-switch |
| `PQ_RISK_MAX_DAILY_LOSS` | 0,02 | Pérdida diaria (2 %) que activa el kill-switch |
| `PQ_RISK_MAX_HEDGE_IMBALANCE` | 0,15 | Desbalance entre las patas spot y perp |
| `PQ_RISK_IMBALANCE_GRACE_SECONDS` | 300 | Tiempo que se tolera el desbalance (p. ej. entre la ejecución de las dos patas) |

Los valores inválidos hacen fallar el arranque. Ningún entorno admite un apalancamiento mayor que 2.
