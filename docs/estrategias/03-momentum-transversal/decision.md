# Estrategia 3 · Momentum transversal: decisión (PQ-114)

**Fecha:** 2026-11-25. **Decisión: se descarta el momentum transversal tal como fue pre-registrado.**

| Hipótesis | Desarrollo ([evaluación](evaluacion.md)) | Holdout | Decisión |
|---|---|---|---|
| X1, largo/corto en perpetuos | No pasa G1, G3 ni G4 (Sharpe 0,24, CAGR 2,9 %, t 0,45) | No se abre | **Descartada** |
| X2, solo largo | No pasa G1 a G4 (CAGR −14,0 %, caída −93 %) | No se abre | **Descartada** |

## Consecuencias

- **No va a paper trading.** No hay ninguna configuración que pase los gates.
- **El holdout del momentum queda sin usar.** No se puede abrir para «ver qué habría pasado»:
  sería un ensayo nuevo sobre los mismos datos.
- **El overlay de sentimiento sigue pre-registrado** ([05-sentimiento](../05-sentimiento/pre-registro.md)).
  Su §8 dice que se evalúa aunque la base no pase, pero tendría que pasar sus gates por sí solo.
  Con una base de t = 0,45, quedarse fuera algunas semanas difícilmente llega a t > 3. Antes de
  gastar 2 ensayos en él, conviene decidir si merece la ingesta del índice: esa decisión es del
  titular, y no se toma aquí.
- **Lo que se aprende:**
  - el momentum de corto plazo en altcoins se revierte (L = 7 y 14 pierden en la CPCV);
  - rotar una cartera de 10 altcoins cada semana cuesta más de la mitad de lo que gana;
  - ir largo en altcoins en perpetuo paga un funding que, en 2021, se llevó el 68 % del capital.
- **N:** los 6 ensayos quedan en el registro y suman a la familia `tendencia`, que pasa a N = 18.
  Cualquier variante futura de momentum (otro universo, otra frecuencia) es una hipótesis nueva,
  con su propio pre-registro, y paga ese N.
