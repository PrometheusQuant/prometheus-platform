# Definición de Listo y de Terminado

## Definición de Listo (DoR): cuándo un ticket puede entrar al sprint

- Tiene un objetivo claro y **criterios de aceptación verificables**.
- Tiene estimación en puntos y cabe en un sprint (si no, se divide).
- Sus dependencias están resueltas o identificadas.
- **Si es una estrategia o un modelo:** la hipótesis económica está escrita *antes* de ver
  resultados, junto con la métrica de éxito, el benchmark y la ventana de holdout.
- **Si es un spike:** tiene *time-box* y su entregable es una decisión (go / no-go), no una métrica.

## Definición de Terminado (DoD): cuándo un ticket pasa a Done

- PR fusionado en `develop` con la aprobación del compañero.
- CI en verde: lint, mypy estricto, contratos de arquitectura y tests con cobertura ≥ 80 %.
- Documentación actualizada (docstrings, README o ADR si hubo una decisión de arquitectura).
- Sin secretos ni datos sensibles en el diff.
- **Datos:** validaciones de esquema y de *point-in-time* pasando.
- **Estrategias y modelos:** ensayos registrados (N), costes reales incluidos y los gates de la
  fase CRISP-ML(Q) correspondiente cumplidos o el descarte documentado.

## Gates de calidad por fase CRISP-ML(Q)

| Fase | Gate |
|---|---|
| 1. Negocio y datos | Hipótesis ex ante, benchmark no-ML y holdout definidos |
| 2. Ingeniería de datos | Datos point-in-time (`knowledge_time`), checks de esquema y checksums |
| 3. Ingeniería del modelo | Todos los ensayos registrados; validación purgada con embargo |
| 4. Evaluación | Deflated Sharpe > 0,95; PBO < 0,5; t > 3; Sharpe neto de costes reales |
| 5. Despliegue | Paper trading en testnet, kill-switch probado, runbook |
| 6. Monitoreo | Alertas de drawdown y drift; prohibido retocar sin un nuevo ciclo PDCA |

Los umbrales de la fase 4 son propuestas del equipo, no estándares normativos; se revisan con
evidencia.
