# Spike de sentimiento: ¿hay un dato histórico, gratuito y point-in-time?

- **Ticket:** PQ-103 (spike y pre-registro) · **Carril:** Boris · **Agente:** Claude B
- **Fecha de la consulta:** 2026-11-24, contra la API pública en vivo y la Wayback Machine
- **Reproducible con:** `uv run python scripts/spike_sentimiento.py --out spike-sentimiento.json`
- **Pre-registro que sale de aquí:** [`docs/estrategias/05-sentimiento/pre-registro.md`](../estrategias/05-sentimiento/pre-registro.md)

## Decisión

| Pregunta | Decisión | Por qué, en una línea |
|---|---|---|
| ¿El **Crypto Fear & Greed Index** sirve como dato? | **GO** | Gratis, diario desde 2018-02-01, sin revisiones en 67 copias archivadas y publicado a las 00:00 UTC |
| ¿Clasificar **texto** (noticias o redes) con CryptoBERT? | **NO-GO** | No hay una fuente de texto histórica, gratuita y point-in-time, y CryptoBERT se entrenó con posts de 2021-11 a 2022-06, dentro del periodo que se evaluaría |
| ¿Un overlay de sentimiento **sobre el carry**, como proponía el ticket? | **NO-GO** | El carry H2 ya se descartó en la prueba final (PQ-50) y su holdout está gastado. Probar una variante del carry ahora sería buscar una regla que lo rescate a posteriori |
| ¿Sobre qué se pre-registra, entonces? | **Momentum transversal** | Tiene el pre-registro hecho y **todavía ningún resultado**. Además, la literatura liga sus caídas a los episodios de pánico |

## 1. Crypto Fear & Greed Index (alternative.me)

**Qué es.** Un índice diario de 0 a 100 de todo el mercado cripto. Se calcula con la volatilidad, el
momentum y el volumen, las redes sociales, la dominancia de BTC y Google Trends. Su propia
clasificación, medida en la historia completa: miedo extremo hasta 25, miedo de 26 a 46, neutral de
47 a 54, codicia de 55 a 75 y codicia extrema desde 76. Hay 752 días de miedo extremo (23 %) y
282 de codicia extrema (9 %).

| Criterio | Medido el 2026-11-24 |
|---|---|
| **Cobertura** | 3.215 días, del **2018-02-01** al 2026-11-24. Cubre entero el periodo de evaluación del momentum (2021-02-01 → 2024-06-30) y su holdout |
| **Huecos** | 2: 4 días tras el 2018-04-13 y 2 días tras el 2024-10-25. Este último cae en el holdout |
| **Frecuencia** | Un valor por día, sellado a las **00:00 UTC** |
| **Revisiones** | **Ninguna.** Las 67 copias de `api.alternative.me/fng/` guardadas por la Wayback Machine (de 2019-03-30 a 2026-11-05) coinciden, valor a valor, con la historia que da la API hoy |
| **Cuándo se conoce** | El valor del día D ya aparece a las **00:14 UTC** de D (la copia más temprana: 0,23 h). Ninguna copia, tomada a cualquier hora, mostró el día anterior. Se publica justo después de medianoche |
| **Sesgo de supervivencia** | No aplica: es un índice de todo el mercado, sin universo de monedas |
| **Licencia** | Uso libre, también comercial, **con la atribución junto al dato** donde se muestre ([alternative.me](https://alternative.me/crypto/fear-and-greed-index/)) |
| **Coste** | Gratis, sin clave |

**Límites que hay que tener presentes:**

- **Parte del índice es precio.** La volatilidad y el momentum del mercado entran en su cálculo.
  Un overlay con el índice no es «sentimiento puro»: una parte es una señal de precio con otro
  nombre. Por eso el pre-registro lo compara contra su propia base, no contra el vacío.
- **La metodología cambió con el tiempo.** Por ejemplo, las encuestas están en pausa. Eso no es una
  revisión de valores pasados (lo publicado se mantiene), pero el índice de 2018 y el de 2026 no se
  calculan exactamente igual.
- **Las 67 copias son una muestra**, de una por mes como mucho. Que ninguna difiera no prueba que
  nunca haya habido una revisión, pero sí que no es algo habitual. La ingesta debería guardar una
  copia propia cada día para que, de aquí en adelante, la serie sea point-in-time por construcción.

## 2. Texto y CryptoBERT: no

**El modelo.** [CryptoBERT](https://huggingface.co/ElKulako/cryptobert), con licencia MIT, es
`bertweet-base` reentrenado con unos 3,2 millones de posts cripto. Su clasificador (alcista, neutral
o bajista) se ajustó con 2 millones de posts de StockTwits **recogidos de noviembre de 2021 a junio
de 2022**. Ese periodo está dentro de la ventana de evaluación del momentum (2021-02 → 2024-06): el
modelo habría visto el lenguaje de esos meses. Sería look-ahead en el propio clasificador, no solo
en los datos.

**Las fuentes de texto.** Ninguna cumple a la vez «histórica», «gratuita» y «point-in-time»:

| Fuente | Qué hay | Por qué no sirve |
|---|---|---|
| CryptoPanic API | Noticias con votos | El plan gratuito no documenta cuánta historia da. Los datasets armados con ella solo traen unas 200 noticias por filtro. Los votos son los de hoy, no los del día de la noticia |
| Datasets publicados (Mendeley, Hugging Face, Kaggle) | De 135.000 a 188.000 noticias de 2017 a 2025 | Los armó un tercero: no se sabe qué se perdió (noticias borradas, medios caídos) ni cuándo se recogió cada una. Licencias heterogéneas |
| GDELT GKG 2.0 | Tono de noticias de todo el mundo desde el 2015-02-19, cada 15 minutos, en BigQuery | Es point-in-time y gratuito, pero no es de cripto: habría que filtrar por palabras clave, y el tono de GDELT es un léxico general, el mismo problema que FinBERT |
| Reddit (Pushshift, Arctic Shift) | Volcados de todos los subreddits | Pushshift dejó de ser público. Los sucesores son comunitarios y con términos por verificar. Además, los votos y los borrados no son point-in-time |
| X (Twitter) | La red con más conversación cripto | La API de búsqueda histórica es de pago |
| Santiment | Volumen social y sentimiento por moneda | El plan gratuito da un año de historia y retrasa los últimos 30 días ([Santiment Academy](https://academy.santiment.net/sanapi/historical-and-realtime-data-restrictions/)) |

Si algún día se quiere sentimiento de texto, el único camino honesto es **guardar el texto desde
hoy** y esperar a tener historia propia, o pagar una fuente con fecha de captura. Eso queda fuera
del sprint.

## 3. Por qué no sobre el carry y sí sobre el momentum

El ticket proponía «no entrar al carry con sentimiento extremo». Cuando se escribió, el holdout del
carry seguía cerrado. Ya no: **H2 pasó en desarrollo y falló en la prueba final** (0,22 % anual,
PQ-50). Probar ahora una variante del carry con un filtro nuevo sería buscar, después de ver el
resultado, la regla que lo habría salvado. El holdout no se puede volver a usar.

El **momentum transversal** (PQ-114) tiene pre-registro y aún no tiene ningún resultado: el registro
de ensayos solo trae filas descriptivas del universo. Y tiene un mecanismo que lo liga al
sentimiento:

- las ganancias del momentum se concentran en los periodos optimistas y desaparecen en los
  pesimistas (Antoniou, Doukas y Subrahmanyam, 2013);
- los «crashes» del momentum llegan en los estados de pánico que siguen a una caída del mercado,
  cuando los perdedores rebotan más que los ganadores (Daniel y Moskowitz, 2016).

El pre-registro prueba si quedarse fuera en las semanas de miedo extremo mejora el momentum. Se
escribe antes de que exista ningún backtest del momentum.

## 4. Qué falta para evaluarlo

1. **Ingesta** del índice en bronze y silver, con `knowledge_time` y la atribución. Incluye la copia
   diaria propia. Ticket nuevo, en el carril de Boris.
2. **El backtest del momentum** (PQ-114, Claude A). El overlay se aplica sobre su motor, sin tocar
   sus reglas.
3. **La evaluación del overlay**, después de la del momentum, con el N de la familia `tendencia` de
   ese momento.

## Fuentes

- alternative.me, [Crypto Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/)
  y su API `api.alternative.me/fng/`, consultadas el 2026-11-24.
- Wayback Machine, copias de `api.alternative.me/fng/` (índice CDX), consultadas el 2026-11-24.
- [CryptoBERT](https://huggingface.co/ElKulako/cryptobert), ficha del modelo en Hugging Face.
- [GDELT Project](https://gdeltproject.org/data.html), datos y BigQuery.
- [Santiment Academy](https://academy.santiment.net/sanapi/historical-and-realtime-data-restrictions/),
  restricciones del plan gratuito.
- [CryptoPanic](https://cryptopanic.com/developers/api/about), planes de la API.
- Antoniou, C., Doukas, J. A. y Subrahmanyam, A. (2013). Cognitive Dissonance, Sentiment, and
  Momentum. *Journal of Financial and Quantitative Analysis*, 48(1), 245-275.
- Daniel, K. y Moskowitz, T. J. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2),
  221-247.
