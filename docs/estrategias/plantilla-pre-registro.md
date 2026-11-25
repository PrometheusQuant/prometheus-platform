# Plantilla de pre-registro

Se copia a `docs/estrategias/<nn>-<nombre>/pre-registro.md` y se rellena **antes de mirar ningún
resultado de la estrategia**: ni backtests ni retornos condicionados a la señal. Mirar la cobertura
de los datos (fechas y huecos) sí está permitido, y se declara en el §11.

Las secciones siguen los pre-registros ya ejecutados ([carry](01-carry/pre-registro.md),
[tendencia](02-tendencia/pre-registro.md), [momentum](03-momentum-transversal/pre-registro.md) y
[Polymarket](04-polymarket/pre-registro.md)). Desde PQ-122, el §8 usa el **método de validación
para pre-registros nuevos**, que corrige limitaciones encontradas en la revisión adversarial de la
tendencia.

---

```markdown
# Pre-registro: <nombre de la estrategia>

- **Ticket:** PQ-<n> · **Carril:** <David o Boris> · **Agente que lo redacta:** <agente>
- **Fecha:** <AAAA-MM-DD>, antes de cualquier backtest.

## 1. Hipótesis
Hipótesis principal (y secundarias, si las hay) y la hipótesis nula, en una frase cada una.

## 2. Mecanismo económico
Por qué debería funcionar (con fuentes) y **por qué podría fallar**.

## 3. Universo y datos
Regla del universo fijada antes de verlo; fuentes; `knowledge_time` de cada dato; qué se hace con
los huecos (sin imputar) y con los deslistados.

## 4. Reglas de la estrategia
Señal, decisión, ejecución (latencia, precio), tamaño, funding o comisiones de cada pata.

## 5. Ensayos pre-declarados
Tabla de parámetros y cuántas configuraciones son. **Familia de N** y por qué.

## 6. Modelo de costes
Escenario principal (gates) y sensibilidades (solo se informan).

## 7. Periodos
Desarrollo y holdout, con sus fechas. El holdout se abre una sola vez y solo si pasa los gates.

## 8. Evaluación
Métrica principal, benchmarks, validación, gates y lo que siempre se informa (ver abajo).

## 9. Riesgos no modelados
## 10. Enmiendas
Antes del primer backtest una enmienda no suma a N; después, todo cambio es un ensayo nuevo.
## 11. Declaración de exposición previa
Qué resultados de otras estrategias y qué datos ya se vieron, y qué **no**.
```

---

## §8 · Método de validación para pre-registros nuevos (PQ-122)

Todas las funciones están en `research/validation.py` y tienen tests en
`tests/unit/research/test_validation_method.py`.

| Qué | Cómo, desde PQ-122 | Función |
|---|---|---|
| **Selección en la CPCV** | En cada partición se elige la configuración con el **entrenamiento** y se mide en su **prueba**. Se informa la mediana del Sharpe fuera de muestra de la elegida y la parte de particiones en que perdió. Antes se elegía con el Sharpe medio de prueba, que con 6 grupos y 2 de prueba equivale a elegir con toda la muestra | `cpcv_select_out_of_sample` |
| **N del Deflated Sharpe** | El gate usa el N de la familia, y **además se informa** el DSR con el N global del registro | `deflated_sharpe_family_and_global` |
| **t de la media** | Se informa el t con error estándar de **Newey-West**, además de `SR · √n`. El gate G3 dice cuál de los dos usa | `newey_west_t` |
| **Rotación anual** | Como **fracción del capital de cada día**, no como nocional sobre el capital inicial | `annual_turnover` |
| **Efectivo ocioso** (sensibilidad al 4 %) | Con `1 − peso medio invertido`, no con `1 − tiempo invertido` | `idle_cash_returns` |
| **«Mejor que el benchmark»** | Se prueba la diferencia de Sharpe con **Jobson-Korkie con la corrección de Memmel**, una cola. El gate fija el nivel (por ejemplo, p < 0,05) | `sharpe_difference_test` |

**Gates de la fase 4** (los mismos de siempre, salvo que el pre-registro justifique otros):
Deflated Sharpe > 0,95 con el N de la familia; PBO < 0,5; t > 3; y la condición económica frente
al benchmark y al 4 %.

**Siempre se informan:** el drawdown máximo, el peor mes, la rotación, la descomposición del
resultado (precio, funding, costes), la correlación diaria con las demás estrategias y el N global.

Estas reglas **no se aplican** a los pre-registros ya ejecutados (carry, tendencia, momentum,
Polymarket y sentimiento): cambiarles el método después de ver los resultados sería ajustarlo a
los datos.
