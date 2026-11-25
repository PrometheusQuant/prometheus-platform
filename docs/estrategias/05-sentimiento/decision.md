# Overlay de sentimiento sobre el momentum: decisión (PQ-128)

**Fecha:** 2026-11-25. **Decisión: S1 y S2 se descartan tal como fueron pre-registrados.**

| Hipótesis | Desarrollo ([evaluación](evaluacion.md)) | Holdout | Decisión |
|---|---|---|---|
| S1, sobre X1-L28 | Pasa G2, G4 y G5; **no pasa G1 (DSR 0,08) ni G3 (t 0,89)** | No se abre | **Descartada** |
| S2, sobre X2-L28 | Pasa G2, G4 y G5; **no pasa G1 (DSR 0,14) ni G3 (t 1,25)** | No se abre | **Descartada** |

## Consecuencias

- **No va a paper trading.** El filtro mejora a su base, pero el resultado no se distingue del azar
  con la exigencia del protocolo.
- **El holdout del momentum sigue sin usarse.** No se abre para ver si el overlay «habría
  funcionado»: sería un ensayo nuevo sobre los mismos datos.
- **Lo que se aprende:**
  - el miedo extremo del Fear & Greed marca semanas malas para el momentum en cripto, como dice la
    literatura (Antoniou et al., 2013; Daniel y Moskowitz, 2016);
  - para que eso sea una estrategia hace falta más evidencia que 3,4 años: más historia, otro
    universo o la misma señal en el holdout de otra estrategia, siempre con pre-registro nuevo y
    pagando su N.
- **La ingesta del índice se queda.** `pq sentimiento descargar` guarda una copia por descarga, así
  que la serie será point-in-time por construcción. Sirve para cualquier hipótesis futura.
- **N:** la familia `tendencia` pasa a N = 20 (12 de la tendencia, 6 del momentum y 2 de este
  overlay).
