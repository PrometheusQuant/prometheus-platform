# Estrategia 4 · Polymarket: decisión (PQ-93)

**Fecha:** 2026-11-25. **Decisión: se descarta la estrategia de Polymarket tal como fue
pre-registrada.**

| Hipótesis | Desarrollo ([evaluación](evaluacion.md)) | Holdout | Decisión |
|---|---|---|---|
| P1, favorito fuera de deportes (B80) | −0,59 % por apuesta, t −2,07; solo pasa G2 | No se abre | **Descartada** |
| P2, favorito en deportes (control) | −0,20 % por apuesta, t −0,43; no pasa ningún gate | No se abre | **Descartada** |

## Consecuencias

- **No va a paper trading.** No hay ninguna configuración que pase los gates.
- **El holdout de Polymarket (julio de 2025 a junio de 2026) queda sin usar.**
- **Lo que se aprende:**
  - el sesgo favorito-longshot que documenta la literatura de apuestas no sobrevive a la comisión
    taker y al diferencial de un minorista en Polymarket;
  - incluso sin comisión, el edge es cero (t 0,18);
  - la cuarta estrategia del proyecto se descarta por el mismo protocolo que las otras tres.
- **Los datos se quedan.** El catálogo completo hasta 2026-10 y los precios diarios del universo de
  evaluación quedan en el lakehouse. Una hipótesis nueva (por ejemplo, como maker, si algún día hay
  libro de órdenes histórico) necesitaría su propio pre-registro y su propio N.
- **N:** 6 ensayos en la familia `polymarket`.
