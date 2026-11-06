# Plan de implementación: riesgo pre-trade y kill-switch

- **Ticket:** PQ-53 · **Fecha:** 2026-11-06 · **Spec:** [spec.md](spec.md)

## Contexto técnico

| | |
|---|---|
| Ubicación | `portfolio_risk/`: capa de aplicación, independiente de `strategies` y `execution` |
| Dinero | `Decimal`, como en el dominio (`OrderGateway` recibe cantidades `Decimal`) |
| Eventos | `KillSwitchTripped` y `KillSwitchReset` nuevos en `domain/events.py`; se reutiliza `RiskLimitBreached` |
| Alertas | `log.critical(...)`: el `AlertForwarder` de PQ-38 lo envía a Telegram sin acoplar el riesgo al canal |
| Persistencia | Archivo bandera `data/paper/KILL_SWITCH` con JSON (motivo, vía, instante). Si existe, está activado |
| Configuración | `PQ_RISK_*` en `ops/settings.py`, con validación al arrancar |

## Estructura

```
src/prometheus_platform/portfolio_risk/
├── risk.py          # RiskLimits, ProposedOrder, Position, PortfolioSnapshot, RiskManager
└── kill_switch.py   # KillSwitch (archivo bandera + eventos + alerta + cancel_all), enforce
src/prometheus_platform/adapters/jsonl_journal.py   # diario append-only persistente (lo usa PQ-54)
tests/unit/portfolio_risk/
docs/runbooks/kill-switch.md
```

## Verificación contra la «constitución»

| Regla | Cumplimiento |
|---|---|
| ADR-0001 (capas) | `portfolio_risk` importa `domain` y `ops`. No importa `strategies` ni `execution` |
| Fallar en voz alta | Límites inválidos: falla el arranque. Equity ≤ 0: kill-switch. Nunca un valor por defecto silencioso |
| Seguridad | El reset exige `--confirm` y queda registrado con autor |
| DoD fase 5 | Kill-switch probado: tests y simulacro en el runbook |

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El desbalance transitorio entre la ejecución de dos patas activa el kill-switch | El monitor recibe la antigüedad del desbalance y solo actúa pasada la gracia configurable |
| Activación falsa por un dato erróneo de equity | Se registra la causa con los valores. El reset manual es deliberado: es preferible parar de más |
