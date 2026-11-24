# Mutation testing del riesgo y la validación

PQ-99. La cobertura dice qué líneas se ejecutan, no si los tests **notarían** un error en ellas.
`mutmut` introduce errores pequeños (un `<` por `<=`, un `True` por `False`, un argumento
borrado) y vuelve a correr los tests. Si todos siguen en verde, ese **mutante sobrevive**: hay un
error posible que nadie detectaría.

## Alcance

Solo el código que protege el dinero o el protocolo:

| Módulo | Por qué |
|---|---|
| `portfolio_risk/risk.py` | Límites antes de cada orden y monitor que decide cuándo parar |
| `portfolio_risk/kill_switch.py` | Detener la operación y no rearmarse solo |
| `portfolio_risk/counterparty.py` | Reducir o detener ante señales de insolvencia del exchange |
| `portfolio_risk/budget.py` | Topes de capital por exchange (CVaR) |
| `research/validation.py` | Deflated Sharpe, CPCV y PBO: los gates de la fase 4 |
| `data_platform/gold.py`, solo `validate` | Esquema, claves, integridad y holdout cerrado del modelo gold |

Cuentan solo las **pruebas del propio módulo**:

- `tests/unit/portfolio_risk/`;
- `test_validation.py`;
- `test_gold.py`.

Las del runner (`tests/unit/api/`) también ejercitan el kill switch, pero multiplican el tiempo
por unas 20 veces. Además, un módulo de seguridad debe defenderse con sus propios tests.

## Cómo se ejecuta

```bash
make mutation        # ~10 min en la laptop (8 núcleos); deja mutmut-informe.md
uv run mutmut show <nombre-del-mutante>   # el cambio exacto de un sobreviviente
uv run mutmut browse                      # navegador interactivo de resultados
```

En la CI corre **cada lunes** (`.github/workflows/mutacion.yml`) y no en cada PR, por el tiempo.
El informe queda en el resumen del run y como artefacto durante 90 días.

## Cómo se cuenta

`scripts/mutmut_informe.py` clasifica cada sobreviviente:

- **log:** solo cambia una llamada de log, incluidos sus argumentos en varias líneas. Los mensajes
  de log no son comportamiento.
- **texto:** solo cambia el texto del mensaje de una excepción.
- **comportamiento:** todo lo demás.

**Score ajustado** = detectados / (evaluados − sobrevivientes de log o texto). Los detectados son
los mutantes `killed`, `timeout` y `segfault`. Los mutantes `no tests` cuentan como no detectados.
El informe lista cada descontado, para que una revisión pueda comprobar que la heurística no
esconde nada.

### Mutantes equivalentes conocidos

Algunos mutantes no cambian el comportamiento observable y no se pueden matar. Se aceptan como
sobrevivientes:

- **`False` → `None`** en una bandera que solo se usa como booleano: por ejemplo,
  `self._observed = None` o `state.get("journaled", None)`. Los dos valores son falsos.
- **`dict.get(k, default)` sin default** cuando el valor por defecto es `None` o falso y el uso es
  booleano.

## Umbral (gate)

**El gate falla si el score ajustado baja de 78 % (`MUTATION_UMBRAL` en el `Makefile`).** Es la primera medición, del
2026-11-22 (78,5 %), redondeada hacia abajo. Funciona como un trinquete:

- se **sube** cada vez que una tanda de tests mata más mutantes;
- **no se baja** sin una justificación escrita en el PR que lo cambie, porque bajar el listón es un
  hallazgo de la revisión (ver `code-review-and-quality`).

## Primera medición (2026-11-22)

Salida de `make mutation` (1415 mutantes evaluados, unos 10 minutos):

| Módulo | Detectados | Sobreviven | Sin tests locales | De comportamiento |
|---|---|---|---|---|
| `portfolio_risk/risk.py` | 277 | 47 | 0 | 47 |
| `portfolio_risk/kill_switch.py` | 230 | 67 | 0 | 31 |
| `portfolio_risk/counterparty.py` | 57 | 16 | 0 | 12 |
| `portfolio_risk/budget.py` | 230 | 52 | 98 | 41 |
| `research/validation.py` | 224 | 64 | 0 | 61 |
| `gold.validate` | 50 | 3 | 0 | 2 |

- **Score bruto:** 75,5 %.
- **Score ajustado:** 78,5 %, con 55 sobrevivientes de log o texto descontados.
- **Antes de las pruebas nuevas de este PR:** el score ajustado era del 73,5 %.

Los 98 mutantes sin tests locales de `budget.py` son de `cvar_contributions` y `bootstrap_bands`.
Solo los prueban el dashboard y la CLI.

Las pruebas de gold necesitaron 10 s fijos de margen (`timeout_constant`). Sin ese margen, 43
mutantes de `gold.validate` salían por *timeout*, que cuenta como detectado, aunque solo
cambiaban un mensaje: el test tardaba más de lo estimado con 8 procesos en paralelo. Con el margen,
50 se detectan de verdad y 3 sobreviven.

### Qué encontró

- **El riesgo comprobaba la regla, pero no la decisión.** Las pruebas verificaban qué regla
  saltaba. Sobrevivían los mutantes que aprobaban una orden con equity no positiva, y los que no
  disparaban el kill switch con equity ≤ 0 o sin equity de inicio del día. Tampoco se probaba
  ningún límite justo en el borde (pérdida diaria exacta, apalancamiento 1,0x y 1,5x exactos).
  Lo cubre `test_risk_contrato.py`.
- **El kill switch no fijaba el contenido de la bandera ni del diario.** Faltaba comprobar:
  - que una bandera manual registra su motivo, su vía y su hora;
  - que el aviso «activo» sale una vez por activación;
  - el rearme con autor.

  Lo cubre `test_kill_switch_contrato.py`.
- **Un defecto real:** al marcar la bandera como registrada, `_mark_journaled` la reescribía con
  permisos 644 en vez de los 600 con que nace. Corregido en el mismo PR.

### Pendiente

Los sobrevivientes de comportamiento que quedan están en el último informe del job semanal,
agrupados por función. Los grupos más grandes, en orden de prioridad:

1. `budget.optimize_budget`;
2. `validation.performance`;
3. `counterparty.assess`.

Su seguimiento está en [PQ-121](https://prometheusquant.atlassian.net/browse/PQ-121).
