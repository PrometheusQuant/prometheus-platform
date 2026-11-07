# Registro de ensayos compartido (N)

El Deflated Sharpe corrige el Sharpe por el **número de ensayos** N. Si un ensayo no se cuenta, el
gate G1 queda inflado. Con dos carriles en dos máquinas, un MLflow local no basta: un backtest de
Boris no sumaría a la N de David. Por eso N vive en el repositorio (PQ-112).

## Dónde y cómo

- **Un archivo por carril:** `docs/estrategias/ensayos/david.jsonl` y `boris.jsonl`. Cada carril
  solo agrega líneas a su archivo, así dos PR en paralelo nunca chocan. **N es la suma de todos.**
- **Automático:** cada `pq research *` escribe sus filas antes de mostrar resultados. Si no puede
  escribirlas, el comando falla.
- **Carril:** `PQ_RESEARCH_LANE` en el `.env` (`david` por defecto, `boris` en la máquina de
  Boris). El autor sale de `git config user.name`, o de `PQ_RESEARCH_AUTHOR`.
- **Append-only:** las filas no se editan ni se borran, tampoco las de una ejecución «mala».
- **En el PR:** las filas nuevas van en el mismo PR que los resultados. Un PR con resultados nuevos
  sin sus filas no se fusiona (`AGENTS.md`).

## Qué guarda cada fila

| Campo | Contenido |
|---|---|
| `fecha` | Instante UTC de la ejecución |
| `autor`, `carril` | Quién la ejecutó y en qué carril |
| `familia` | `carry`, `modelo-funding`, `descriptivo`, … N se cuenta **por familia** |
| `hipotesis`, `nombre`, `params` | Hipótesis (H1, H2…) y configuración |
| `metricas` | Las del ensayo: entre ellas, el Sharpe diario que usa V[SR] |
| `commit` | Código con el que se ejecutó; `-sucio` si había cambios sin commitear |
| `cuenta_en_n` | `false` solo en ejecuciones descriptivas (EDA, estadística, finanzas, simulación) |
| `comando` | El comando exacto |

## Cómo se usa N

- `pq research carry` toma N de la familia `carry` de **todos** los carriles. La fórmula no cambia
  (pre-registro §5): N = max(ensayos registrados, 18) + 2 de la prueba de humo (enmienda 2).
  Solo cambió la fuente.
- `pq research registro resumen` imprime N por familia y la N global.
- `pq research registro importar-mlflow` lleva al registro el historial de un MLflow local, sin
  duplicar: cada fila guarda el `run_id`. `pq research registro verificar` comprueba que no
  falte ningún ensayo de MLflow.

## Historial importado

El 2026-11-07 se importó el MLflow local de David, con 63 ensayos de 2026-10-30. Salida de
`pq research registro resumen`:

```text
carry: N = 18
modelo-funding: N = 45
total: N = 63
```

`pq research registro verificar` respondió «registro y MLflow cuadran». Con 18 ensayos de carry,
la N del Deflated Sharpe sigue siendo 20, la misma que en la evaluación.

## Ensayos fuera de `pq research`

Si Boris o David investigan con un notebook o un script propio, cada ejecución agrega su fila a
mano con el mismo formato, en el archivo de su carril. Lo más simple es usar `TrialLedger` de
`adapters/trial_ledger.py` en lugar de escribir el JSON.
