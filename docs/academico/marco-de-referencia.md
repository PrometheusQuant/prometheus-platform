# Capítulo 2 · Marco de referencia

- **Ticket:** PQ-28 · **Fecha:** 2026-10-30
- **Contenido:** 2.1 estado del arte (APA 7), 2.2 PESTEL aplicado y 2.3 marco normativo, institucional y ético
- **Convención:** lo que no se pudo confirmar con una fuente primaria se marca como *no verificado*. No es asesoría legal ni tributaria.

## 2.1 Marco conceptual y estado del arte

### Conceptos

| Concepto | Definición operativa en este proyecto |
|---|---|
| Perpetuo (*perpetual future*) | Futuro sin vencimiento. Su precio se ancla al spot con pagos periódicos de **funding** entre largos y cortos |
| Funding rate | Tasa que pagan los largos a los cortos (o al revés) cada 8 h (a veces cada 4 h o 2 h). En Binance, la base es 0,01 % por liquidación |
| Carry (cash-and-carry) | Comprar spot y vender el perpetuo por el mismo nocional: se cobra el funding sin exposición al precio |
| Point-in-time | Cada dato se usa solo desde el momento en que pudo conocerse (`knowledge_time`); evita el sesgo de anticipación |
| Sobreajuste del backtest | Encontrar por azar una configuración que funciona en el pasado por haber probado muchas |

### Cómo se ha abordado el problema en la literatura

| Línea | Qué aporta | Cómo se usa aquí |
|---|---|---|
| **Carry cripto** | Schmeling, Schrimpf y Todorov (2023): el carry de futuros cripto supera el 10 % anual y se explica por la demanda minorista de apalancamiento y la escasez de capital de arbitraje; un carry alto predice caídas | Mecanismo económico de la Estrategia 1 y advertencia de riesgo de cola |
| **Perpetuos** | He, Manela, Ross y von Wachter (2024): con datos horarios de Binance, la desviación del perpetuo respecto a su valor teórico genera Sharpe de 1,6 a 2,6 con costes minoristas, y la mayor parte del retorno viene del *timing* | Motiva la entrada por umbral (H1 y H2) |
| **ML en precios de activos** | Gu, Kelly y Xiu (2020): los árboles y las redes superan a los modelos lineales para predecir retornos; las ganancias vienen de las interacciones no lineales | Elección de Random Forest y Gradient Boosting en el modelo del funding (cap. 5) |
| **Momentum de series temporales** | Moskowitz, Ooi y Pedersen (2012): el retorno pasado de 12 meses predice el futuro en 58 mercados | Base de la Estrategia 2 (tendencia) |
| **Riesgo y retorno cripto** | Liu y Tsyvinski (2021): los retornos cripto responden a factores propios (momentum, atención), no a los de acciones | Justifica tratar cripto como clase de activo propia |
| **Protocolo anti-sobreajuste** | Arnott, Harvey y Markowitz (2019): hipótesis ex ante y registro de todo lo probado. Harvey, Liu y Zhu (2016): con muchas pruebas se exige t > 3 | Pre-registro, enmiendas y gate G3 |
| **Validación** | López de Prado (2018): CV purgada con embargo y CPCV. Bailey, Borwein, López de Prado y Zhu (2017): probabilidad de sobreajuste (PBO). Bailey y López de Prado (2014): Deflated Sharpe | Gates G1 y G2 (`research/validation.py`) |
| **Comparación de pronósticos** | Diebold y Mariano (1995): test de igualdad de precisión predictiva | Modelo vs. persistencia (cap. 5) |
| **Proceso de ML** | Studer et al. (2021): CRISP-ML(Q) añade aseguramiento de calidad por fase a CRISP-DM | Proceso maestro (ADR-0004) |

**Brecha que cubre este proyecto.** La literatura documenta el carry y los controles anti-sobreajuste
por separado. No encontramos una implementación abierta que los una para un minorista con menos de
1.000 USD, con costes VIP 0 reales, pre-registro fechado en git y un holdout de un solo uso.

### Referencias (APA 7)

- Arnott, R., Harvey, C. R., & Markowitz, H. (2019). A backtesting protocol in the era of machine learning. *The Journal of Financial Data Science, 1*(1), 64–74. https://doi.org/10.3905/jfds.2019.1.064
- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2017). The probability of backtest overfitting. *Journal of Computational Finance, 20*(4), 39–69. https://doi.org/10.21314/JCF.2016.322
- Bailey, D. H., & López de Prado, M. (2014). The deflated Sharpe ratio: Correcting for selection bias, backtest overfitting, and non-normality. *The Journal of Portfolio Management, 40*(5), 94–107. https://doi.org/10.3905/jpm.2014.40.5.094
- Diebold, F. X., & Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics, 13*(3), 253–263. https://doi.org/10.1080/07350015.1995.10524599
- Gu, S., Kelly, B., & Xiu, D. (2020). Empirical asset pricing via machine learning. *The Review of Financial Studies, 33*(5), 2223–2273. https://doi.org/10.1093/rfs/hhaa009
- Harvey, C. R., Liu, Y., & Zhu, H. (2016). … and the cross-section of expected returns. *The Review of Financial Studies, 29*(1), 5–68. https://doi.org/10.1093/rfs/hhv059
- He, S., Manela, A., Ross, O., & von Wachter, V. (2024). *Fundamentals of perpetual futures* (arXiv:2212.06888). arXiv. https://arxiv.org/abs/2212.06888
- Liu, Y., & Tsyvinski, A. (2021). Risks and returns of cryptocurrency. *The Review of Financial Studies, 34*(6), 2689–2727. https://doi.org/10.1093/rfs/hhaa113
- López de Prado, M. (2018). *Advances in financial machine learning*. Wiley. ISBN 978-1-119-48208-6
- Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H. (2012). Time series momentum. *Journal of Financial Economics, 104*(2), 228–250. https://doi.org/10.1016/j.jfineco.2011.11.003
- Schmeling, M., Schrimpf, A., & Todorov, K. (2023). *Crypto carry* (BIS Working Papers No. 1087). Bank for International Settlements. https://www.bis.org/publ/work1087.pdf
- Studer, S., Bui, T. B., Drescher, C., Hanuschkin, A., Winkler, L., Peters, S., & Müller, K.-R. (2021). Towards CRISP-ML(Q): A machine learning process model with quality assurance methodology. *Machine Learning and Knowledge Extraction, 3*(2), 392–413. https://doi.org/10.3390/make3020020

Los DOI se verificaron el 2026-10-30 (resuelven en doi.org).

## 2.2 Marco contextual (PESTEL aplicado)

Aplicado al caso concreto: **un quant minorista en Bolivia que opera con algoritmos en exchanges
extranjeros con menos de 1.000 USD.**

| Factor | Habilita | Bloquea o amenaza | Fuente |
|---|---|---|---|
| **Político** | El BCB derogó la prohibición (RD 082/2024). Hay una propuesta presidencial de usar reservas cripto para importaciones (oct-2025), sin ejecución confirmada | Protestas de mayo-junio de 2026 en medio de la crisis económica; el marco puede cambiar rápido | [CriptoNoticias](https://www.criptonoticias.com/comunidad/bolivia-criptomonedas-marco-legal/), [DiarioBitcoin](https://www.diariobitcoin.com/america-latina/rodrigo-paz-presidente-de-bolivia-planea-usar-criptoactivos-para-enfrentar-la-falta-de-dolares/), [Wikipedia](https://en.wikipedia.org/wiki/2026_Bolivian_protests) |
| **Económico** | Volumen de bolivianos en Binance: de 46,5 M USD (1S-2024) a 294 M USD (1S-2025); más de 250.000 bolivianos con activos virtuales. Ante la escasez de dólares, el USDT sirve de "dólar digital" | Con menos de 1.000 USD, el carry rinde decenas de USD al año: el margen sobre una stablecoin es de ~1 punto (evaluación del carry) | [eju.tv / BCB](https://eju.tv/2026/02/blockchain-bcb-reporta-que-transacciones-cripto-se-multiplicaron-por-seis-en-un-ano-paz-propone-usarlo-para-combatir-la-corrupcion/) |
| **Social** | Adopción creciente; vías fiat por P2P de Binance y por fintechs (Meru, Takenos) | Sin educación financiera, el apalancamiento cripto puede causar pérdidas graves: el proyecto se presenta como investigación, no como asesoría | [Info.bo](https://periodico.info.bo/2025/07/07/asfi-regula-el-uso-de-criptomonedas-en-bolivia-asi-afecta-a-usuarios-y-plataformas-como-binance-meru-y-takenos/) |
| **Tecnológico** | Datos históricos gratuitos (Data Vision), APIs con entornos demo, librerías abiertas (NautilusTrader con adaptador de Polymarket) | Hardware modesto (5,7 GB de RAM, GPU de 4 GB): no da para deep learning pesado; dependencia de un solo exchange | [binance-public-data](https://github.com/binance/binance-public-data), [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) |
| **Ecológico** | El cómputo del proyecto es mínimo: backtests en minutos en una laptop y sin minería | Bitcoin usa prueba de trabajo, de alto consumo energético; el proyecto lo opera pero no mina. *No verificado:* no se midió la huella | — |
| **Legal** | Operar cripto es legal (RD 082/2024). Bolivia no está restringida en Binance (fuente secundaria) ni en Polymarket (fuente oficial y endpoint verificado) | Binance no está supervisada por ASFI, así que no hay protección local. No existe régimen tributario cripto específico. Argentina y Brasil restringen Polymarket | [compliance/binance.md](../compliance/binance.md), [compliance/polymarket.md](../compliance/polymarket.md) |

## 2.3 Marco normativo, institucional y ético

### Normativa boliviana sobre activos virtuales

| Norma | Fecha | Qué establece | Efecto en el proyecto |
|---|---|---|---|
| RD BCB 082/2024 | 25-06-2024 | Deroga la prohibición (RD 144/2020) y habilita la compraventa de activos virtuales por canales e IEP autorizados | Operar es legal |
| RA UIF/19/2025 | Abr-2025 | Los proveedores de servicios de activos virtuales (PSAV) pasan a ser sujetos obligados en prevención de legitimación de ganancias ilícitas | Afecta a los PSAV, no al usuario. Mantener trazabilidad de fondos |
| DS 5384 | 07-05-2025 | Crea las Empresas de Tecnología Financiera (incluidos los PSAV), con licencia ASFI | Prestar servicios a terceros exigiría licencia. **El proyecto opera solo capital propio** |
| Circular ASFI 885/2025 | 2025 | Reglamenta las fintech con blockchain; adecuación hasta el 31-12-2025 (una fuente cita "Resolución ASFI 540/2025": **discrepancia**; prórroga *no verificada*) | Igual que el anterior |

Fuentes: [Blockchain Internacional](https://blockchaininternacional.com/evolucion-del-marco-regulatorio-de-los-criptoactivos-en-bolivia/),
[Info.bo](https://periodico.info.bo/2025/07/07/asfi-regula-el-uso-de-criptomonedas-en-bolivia-asi-afecta-a-usuarios-y-plataformas-como-binance-meru-y-takenos/),
[Internet Bolivia](https://internetbolivia.org/economia/activos-virtuales-en-bolivia-un-ano-despues/).

**Implicación de diseño:** el producto es una herramienta para operar **capital propio**. Ofrecerlo
como servicio a terceros (gestionar fondos, señales de pago) lo convertiría en una ETF/PSAV que
necesita licencia ASFI. Esto limita el modelo de negocio del capítulo 8.

### Tributación

- Hay tasas generales: IUE del 25 % sobre utilidades y RC-IVA del 13 % sobre ingresos de personas
  naturales ([AGN 2026](https://agn.org/wp-content/uploads/2026/07/2026CSATaxCards_ES.pdf)).
- **No existe un régimen específico para criptoactivos** ni una resolución del SIN sobre ganancias
  en exchanges extranjeros ([Finantres](https://finantres.com/impuestos-sobre-trading-e-inversiones-en-bolivia/)).
- Que esas ganancias sean renta de fuente extranjera para una persona natural es una inferencia
  *no verificada*. Se consultará a un tributarista (PQ-27) antes de operar con capital real.

### Datos y licencias

| Recurso | Condición | Cumplimiento |
|---|---|---|
| Binance Data Vision | Datos públicos de mercado, gratuitos ([repositorio oficial](https://github.com/binance/binance-public-data)) | Se descargan con checksum; no se redistribuyen (`data/` está fuera de git) |
| Datos personales | El sistema **no procesa datos personales de terceros**. Las claves de API del titular son secretos (`SecretStr`, `.env` fuera de git, sin permiso de retiro) | `SECURITY.md`, PQ-15, gitleaks en CI |
| Librerías | MIT, Apache-2.0, BSD y LGPL-3.0 (NautilusTrader, sin modificar). Se evitan las licencias que impedirían un uso comercial futuro (vectorbt con Commons Clause solo para investigación interna) | ADR-0006 |
| Material con copyright | Libros y papers se citan, no se suben al repositorio | Regla de `docs/arquitectura/estructura-de-directorios.md` |

*No verificado:* el estado de una ley general de protección de datos personales en Bolivia en 2026.
Como el sistema no trata datos de terceros, no condiciona el diseño actual.

### Ética algorítmica

1. **Honestidad estadística.** Cada resultado declara cuántos ensayos hubo (N) y cómo se corrigió
   (Deflated Sharpe). Los errores encontrados se documentan (enmienda 2, informe del cap. 5).
2. **No promesa de rentabilidad.** El README y los documentos advierten que es investigación, no
   asesoría. Los resultados en desarrollo no garantizan nada fuera de muestra.
3. **Riesgo acotado.** Apalancamiento 1x, claves sin retiro, capital real menor a 1.000 USD solo
   después del paper trading, y un kill-switch previsto (épica PQ-7).
4. **Impacto en el mercado.** Con este tamaño, las órdenes no mueven precios ni manipulan mercados.
   El sistema no hace *spoofing* ni *wash trading*, prácticas prohibidas por los términos de los
   exchanges.
