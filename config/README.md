# config/: configuración versionada (no secreta)

Parámetros que cambian el comportamiento del sistema y que **deben quedar en el historial de git**,
porque un backtest o una decisión de trading solo es reproducible si se sabe con qué configuración corrió.

```text
config/
├── environments/   # valores por entorno: dev.toml, paper.toml, live.toml
├── universes/      # universos de instrumentos por estrategia (p. ej. carry.toml)
├── risk/           # límites de riesgo: tamaño máximo, drawdown diario, kill-switch
└── strategies/     # parámetros de cada estrategia, enlazados al ticket PQ que los aprobó
```

## Reglas

- **Nunca secretos.** Claves de API, tokens y contraseñas van en `.env` (ignorado por git) o en el
  gestor de secretos del servidor. Ver [SECURITY.md](../SECURITY.md).
- La configuración se carga y valida con `pydantic-settings` (`prometheus_platform.ops`); un valor
  inválido impide arrancar el proceso.
- Cambiar un límite de riesgo o un parámetro de estrategia en `live` requiere PR y ticket.
- Las variables de entorno con prefijo `PQ_` tienen prioridad sobre estos archivos.
