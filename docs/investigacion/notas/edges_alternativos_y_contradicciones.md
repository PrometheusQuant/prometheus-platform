# Edges alternativos (no puramente cuantitativos) y resolución de contradicciones — estado a oct-2026

Contexto: quant solo (+1 compañero) en Bolivia, capital < 1.000 USD, plataforma multiestrategia de largo plazo + capstone de ciencia de datos. Notas en español. Lo que no pude confirmar con una fuente leída en esta sesión va marcado "(no verificado)".

---

## A1. ¿El sentimiento de noticias/redes (NLP) predice retornos cripto después de costos?

### Takeaway
Hay evidencia de que el sentimiento tiene *algo* de poder predictivo (sobre todo para volatilidad y altcoins). Pero no encontré ningún estudio robusto, revisado por pares, que muestre un edge de trading con sentimiento cripto **neto de costos** y fuera de muestra. FinBERT es un modelo de noticias financieras genéricas (Reuters 2008-2010), no de cripto. CryptoBERT es la alternativa específica del dominio.

### Cited Findings
- FinBERT (Araci, 2019) se pre-entrenó de forma adicional sobre TRC2-financial, un subconjunto de noticias de Reuters de 2008-2010 (46.143 documentos, ~400K oraciones filtradas por palabras clave financieras). El clasificador de sentimiento se ajustó sobre Financial PhraseBank: 4.845 oraciones de noticias financieras de LexisNexis, anotadas por 16 personas — [arXiv 1908.10063](https://arxiv.org/pdf/1908.10063); [ar5iv](https://ar5iv.labs.arxiv.org/html/1908.10063)
- CryptoBERT (ElKulako) parte de `vinai/bertweet-base` y sigue entrenándose sobre ~3,2M posts cripto: StockTwits 1,875M (nov-2021 a jun-2022), Telegram 664K, Reddit 172K y Twitter 496K (may-2018). El clasificador (Bearish/Neutral/Bullish) se ajustó sobre 2M posts etiquetados de StockTwits. Longitud máxima: 128 tokens — [Hugging Face model card](https://huggingface.co/ElKulako/cryptobert)
- Nasekin & Chen (Digital Finance, 2020): con 1,22M mensajes de StockTwits sobre 425 criptos, los índices de sentimiento son informativos para predecir retornos y volatilidad del índice cripto en regresiones fuera de muestra. El resumen no menciona costos de transacción — [eprints.gla.ac.uk](https://eprints.gla.ac.uk/214034)
- Steinert & Herff (PLOS ONE, 2018): la actividad y el sentimiento en Twitter predicen retornos de altcoins, pero es un análisis in-sample sobre solo 45 días de datos — [PMC6279012](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6279012/)
- Ider (tesis de maestría, Humboldt): ajusta un clasificador BERT sobre noticias, tweets y Reddit para pronosticar retornos diarios y simula trading. No confirmé si modela costos — [arXiv 2204.05781](https://arxiv.org/abs/2204.05781v1)
- La búsqueda no encontró ningún estudio que combine sentimiento de Twitter, prueba fuera de muestra, costos de transacción y CryptoBERT (resultado de búsqueda; ausencia de evidencia, no evidencia de ausencia).

### Inferences
- Usar FinBERT "tal cual" con texto cripto ("WAGMI", "rekt", "pump", emojis) es un desajuste de dominio. Hay que preferir CryptoBERT o un LLM con prompt, y validar contra etiquetas cripto propias.
- Look-ahead por timestamps: los agregadores (CryptoPanic, RSS, Kaggle) suelen dar la hora de publicación o de *ingesta*, en distintas zonas horarias, y a veces la editan después. Regla segura: alinear con la hora de **disponibilidad** (cuándo lo vio tu sistema), en UTC, y operar en la barra *siguiente*. Lo mismo aplica a los datasets de tweets con fechas reconstruidas (inferencia; no verificado con un paper específico).
- CryptoBERT está sesgado hacia StockTwits 2021-2022 (mercado alcista y luego bajista). Puede haber deriva de vocabulario en 2026.
- Para el capstone, el sentimiento sirve mejor como **feature de régimen/volatilidad** que como señal direccional autónoma.

### Gaps
- Límites actuales del plan gratuito de la API de CryptoPanic: no encontré la página oficial con cifras. Revisar https://cryptopanic.com/developers/api/ (no verificado).
- GDELT 2.0 (actualizaciones cada 15 min desde ~2015, gratis vía BigQuery/CSV) es conocimiento previo, no verificado en esta sesión. Su cobertura de noticias cripto de nicho es pobre (no verificado).
- Datasets de Kaggle con tweets/noticias cripto: no revisé licencias ni calidad de timestamps.
- No encontré evidencia sobre LLMs (GPT/Claude) como etiquetadores de sentimiento cripto neto de costos que resista un año fuera de muestra.

---

## A2. Event-driven: listados en exchanges, desbloqueos de tokens, macro (CPI/FOMC)

### Takeaway
El "efecto listado" está documentado (retornos anormales positivos de corto plazo, mayores en Coinbase que en Binance, con señales de trading informado *antes* del anuncio). Pero es muy heterogéneo y, según la industria, se ha repreciado desde 2023. CPI/FOMC elevan sobre todo la **volatilidad** de BTC; el signo del retorno no es consistente entre estudios.

### Cited Findings
- Event study (Blockchain Research Lab, 2019, 22 exchanges): retorno anormal medio de +7,4% el día del listado y +9,2% en la ventana (-3,+3). En (-3,-2) ya aparece un +3,2% significativo, señal de trading informado. Por exchange: Binance +14,7%, Bitfinex +25,5%, Bittrex +23,5%, pero Gate.io -4,5% y Bibox -3,6% — [blockchainresearchlab.org](https://www.blockchainresearchlab.org/de/2019/09/10/market-reaction-to-exchange-listings-of-cryptocurrencies-2/)
- Li, Luo, Wang & Wei (AFT 2025): ambos exchanges muestran retornos positivos de corto plazo tras el listado, significativamente mayores en Coinbase (más regulado) que en Binance. Además, los tokens listados en Binance que recibieron inversión previa de su brazo de venture tienen fundamentales más débiles — [Dagstuhl LIPIcs AFT 2025](https://drops.dagstuhl.de/storage/00lipics/lipics-vol354-aft2025/html/LIPIcs.AFT.2025.11/LIPIcs.AFT.2025.11.html)
- Cifras de la industria que se contradicen: CoinDesk (Yang, 2023) habla de +41% tras listarse en Binance, y Animoca Research (Ouyang, 2024) de una caída media de -49% tras listados en CEX. Ambas citadas de segunda mano — [RockawayX](https://rockawayx.com/insights/bullish-or-bearish-what-really-happens-when-tokens-list-on-a-cex)
- Análisis de 2026: "el efecto listado es real, pero se ha repreciado sistemáticamente" — [The Tie](https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026)
- FOMC: la volatilidad de los activos digitales sube significativamente al publicarse el comunicado (retornos de 5 min, 2018-2022), y el efecto se extiende a la conferencia de prensa — [arXiv 2302.10252](https://arxiv.org/pdf/2302.10252)
- Corbet, McHugh & Meegan (2017, GARCH): las decisiones de tasas del FOMC afectan los retornos de BTC, y los anuncios de QE afectan la volatilidad — [businessperspectives.org](https://businessperspectives.org/journals/author/andrew-meegan)
- Volmex (white paper de industria, 2024): CPI y decisiones de la Fed elevan mucho la volatilidad realizada de BTC y el BVIV, y la IV cae después — [Volmex PDF](https://volmex.finance/Macroeconomic%20Announcements%20Fuel%20Volatility%20An%20In-Depth%20Analysis.pdf)
- Tesis de Lund (2021): sin efecto en retornos de BTC por anuncios de *flexibilización* del FOMC (resultado nulo, trabajo de estudiante) — [lup.lub.lu.se](https://lup.lub.lu.se/student-papers/record/9066201)

### Inferences
- Para retail sin colocation, el retorno del listado se concentra en segundos o minutos tras el anuncio y *antes* (informed trading). Capturarlo exige monitorear anuncios con latencia baja, y el riesgo de comprar en el pico es alto. Es mejor usarlo como estudio de eventos para el capstone que como fuente de ingreso.
- Macro: el edge plausible es de **volatilidad** (p. ej. reducir apalancamiento o ampliar stops alrededor de CPI/FOMC, o estrategias de opciones), no direccional.

### Gaps
- Desbloqueos de tokens (token unlocks): no encontré un paper académico sólido en esta sesión (no verificado). Hay datos de Token Unlocks/Tokenomist, pero no revisé su evidencia.
- Paper revisado por pares con CPI y BTC intradía: no encontrado.

---

## A3. Mercados de predicción (Polymarket, Kalshi)

### Takeaway
Las ineficiencias están bien documentadas: sesgo favorito-longshot (fuerte en Kalshi, matizado en Polymarket) y arbitraje intra- e inter-mercado en Polymarket (~40M USD extraídos). Ser **maker** (proveer liquidez) es estructuralmente mejor que ser taker. Es la fuente de edge "no puramente quant" con mejor respaldo académico reciente, pero el acceso desde Bolivia y las restricciones regulatorias deben verificarse.

### Cited Findings
- Bürgi, Deng & Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market" (UCD WP 2025/19; CESifo 2025/2026; CEPR DP20631): los precios de Kalshi son predictores razonablemente precisos, y más a medida que se acerca el cierre. Hay un sesgo favorito-longshot sistemático: los contratos < 10¢ ganan mucho menos de lo necesario para el break-even y dejan grandes pérdidas medias, mientras que contratos de precio alto en algunos rangos dejan pequeñas ganancias. El sesgo es mucho más fuerte para takers que para makers — [CESifo](https://www.ifo.de/en/cesifo/publications/2025/working-paper/makers-and-takers-economics-kalshi-prediction-market); [CEPR DP20631](https://cepr.org/publications/dp20631)
- Según el resumen de CEPR/VoxEU, los takers pierden ~32% de media y los makers ~10%. Estas cifras no las verifiqué contra las tablas del paper — [CEPR VoxEU](https://cepr.org/voxeu/columns/economics-kalshi-prediction-market)
- Cardozo & Rivero-Wildemauwe (2026), "The Favorite-Longshot Bias in Prediction Markets: Evidence from Polymarket" (588M trades, 2,48M cuentas). Con ponderación igual por contrato, los longshots pierden 6,3¢ por dólar; agrupando contratos relacionados por evento padre, ganan 4,1¢. El sesgo está ausente en Deportes. O sea, el resultado depende de la agregación — [arXiv 2609.12878](https://arxiv.org/pdf/2609.12878)
- Saguillo, Ghafouri, Kiffer & Suarez-Tangil (2025), "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets": distinguen Market Rebalancing Arbitrage (dentro de un mercado: YES+NO≠1, o la suma de outcomes ≠ 1) y Combinatorial Arbitrage (entre mercados lógicamente relacionados). Estiman ~40M USD de ganancia realizada extraída en Polymarket — [arXiv 2508.03474](https://arxiv.org/abs/2508.03474)
- Existe una base de datos académica "Polymarket-v1" (2026), con la que los tokens de baja probabilidad muestran retornos realizados negativos — [arXiv 2606.04217](https://arxiv.org/pdf/2606.04217)
- NautilusTrader tiene un adaptador nativo `polymarket` en `crates/adapters/polymarket` (verificado en el árbol del repo, rama develop, oct-2026). Esto permite reutilizar el mismo motor de la plataforma — [GitHub nautilus_trader](https://github.com/nautechsystems/nautilus_trader)

### Inferences
- Estrategias candidatas con < 1.000 USD: (1) vender longshots / comprar favoritos de forma sistemática, siendo maker y fuera de deportes; (2) monitor de arbitraje de rebalanceo (suma de outcomes ≠ 1) en Polymarket; (3) market making pasivo en mercados de baja liquidez. Las tres escalan bien hacia abajo en capital, porque los contratos van de 0 a 1 USD.
- Riesgos: el arbitraje "fácil" ya está muy competido (los 40M USD sugieren bots). Hay riesgo de resolución (disputas UMA en Polymarket) y el capital queda inmovilizado hasta la resolución.

### Gaps
- Accesibilidad desde Bolivia: Kalshi es un DCM regulado por la CFTC, en principio para residentes de EE. UU., y la elegibilidad de no residentes no está verificada. La geobloqueo de Polymarket para su exchange internacional en 2026 y el KYC: no verificado en esta sesión.
- Estructura de comisiones vigente de Kalshi/Polymarket a oct-2026: no verificada.
- Límites de rate de las APIs (Polymarket CLOB API, Kalshi API): no verificados.

---

## A4. Enfoques semi-sistemáticos: DCA, rebalanceo, buy-the-dip, grid, martingala, copy trading

### Takeaway
DCA **no** tiene mayor valor esperado que lump sum: este último gana ~2/3 de las veces. DCA reduce arrepentimiento y riesgo de timing, y es una herramienta de gestión de riesgo, no un edge. El "bonus de rebalanceo" en cripto tiene sobre todo respaldo de la industria; en teoría existe para activos volátiles y poco correlacionados, pero las criptos están muy correlacionadas entre sí. Grid trading es, en esencia, vender volatilidad (gana en rango, pierde en tendencia). La martingala tiene valor esperado ≤ 0 y riesgo de ruina.

### Cited Findings
- Vanguard: lump sum superó a DCA ~2/3 de las veces, en ventanas rodantes de 10 años entre 1926 y 2011 en EE. UU., Reino Unido y Australia, con DCA de 6 a 36 meses. Una versión posterior con MSCI World 1976-2022 da un 68% a 1 año. DCA perdió valor con menos frecuencia en ventanas rodantes de 12 meses en EE. UU. (17,6% frente a 22,4%) — [SmartAsset resumiendo Vanguard](https://smartasset.com/investing/lump-sum-investing-research); [Rob Berger](https://robberger.com/lump-sum-investing-vs-dollar-cost-averaging)
- Bitwise (industria): añadir BTC a un portafolio tradicional rebalanceado mejoró el retorno ajustado por riesgo en la mayoría de los periodos de 1 año entre jul-2010 y mar-2020, en parte por "volatility harvesting". Es un estudio de un emisor de producto cripto, criticado por cherry-picking — [Bitwise PDF](https://www.lopp.net/pdf/Bitwise-The-Case-For-Bitcoin-In-An-Institutional-Portfolio.pdf)
- Un índice académico de 5 criptoactivos + oro con Equal Risk Contribution generalizado usa el rebalanceo periódico para explotar baja correlación, pero advierte que la alta volatilidad y la alta correlación intra-clase de las criptos (sin stablecoins) limitan la diversificación — [IDEAS/RePEc](https://ideas.repec.org/h/spr/prbchp/978-3-030-37110-4_15.html)
- Hilbert Capital (promocional): ejemplo de rebalanceo BTC/cash que termina en 225 USD frente a 200 USD de buy-and-hold tras una caída y su recuperación — [HedgeNordic](https://hedgenordic.com/2022/10/harvesting-the-crypto-vol)

### Inferences
- El rebalanceo entre **activos poco correlacionados** (p. ej. BTC frente a stablecoin/T-bills tokenizados, u oro) es donde el "bonus" tiene sentido. Entre altcoins correlacionadas casi no aporta. Además, el bonus depende de reversión a la media: en tendencias fuertes, rebalancear *cuesta* retorno frente a buy-and-hold (inferencia teórica estándar, no verificada aquí).
- Grid trading es equivalente a una posición corta en volatilidad o gamma. Genera pequeñas ganancias frecuentes y una pérdida grande cuando el precio sale del rango. Es transferencia de riesgo, no edge, salvo que haya un régimen de rango identificable (inferencia).
- Martingala: con capital finito, la probabilidad de ruina tiende a 1 en el largo plazo y el valor esperado neto de comisiones es negativo. No debe implementarse (inferencia teórica estándar).
- Copy trading: hay sesgo de supervivencia en los rankings de traders y sus incentivos no están alineados con los del seguidor. Sin fuente leída en esta sesión.
- Clasificación del valor esperado: **EV positivo plausible**: rebalanceo entre activos descorrelacionados (pequeño) y provisión de liquidez en mercados de predicción. **Neutral / gestión de riesgo**: DCA, buy-the-dip sistemático. **Transferencia de riesgo**: grid. **EV negativo**: martingala, copy trading sin due diligence.

### Gaps
- No encontré un estudio revisado por pares que mida el bonus de rebalanceo *específico de cripto* neto de costos.
- Buy-the-dip sistemático en cripto: sin evidencia académica encontrada.
- Copy trading (Binance/Bybit/eToro): no encontré estudios sobre el desempeño neto de los seguidores.

---

## A5. Machine learning para predecir retornos cripto (LightGBM/XGBoost/LSTM/transformers, triple barrera, meta-labeling)

### Takeaway
La evidencia es mixta y está sesgada por publicación. Algunos papers reportan Sharpe fuera de muestra > 3 neto de costos. Otros encuentran que el paseo aleatorio es un benchmark "muy fuerte" para retornos diarios. Lo único que consistentemente ayuda es **filtrar operaciones por un umbral consciente de costos**. No encontré una comparación directa LightGBM vs LSTM neta de costos.

### Cited Findings
- Bysik & Ślepaczuk (Univ. de Varsovia, 2026): XGBoost, LSTM e iTransformer sobre retornos horarios de BTC-USDT con walk-forward de 27 folds. Un filtro consciente de costos (operar solo si el pronóstico supera un umbral basado en costos) redujo la rotación y restauró la rentabilidad en algunas configuraciones — [emergentmind 2606.00060](https://www.emergentmind.com/papers/2606.00060); [chatpaper](https://chatpaper.com/chatpaper/paper/289469)
- Journal of Finance and Data Science (2022): portafolios long-short con ensembles LSTM/GRU dan un Sharpe fuera de muestra ~3,2 tras costos, frente a 1,33 de buy-and-hold. Es un resultado optimista; hay que revisar el universo y los supuestos de costos/slippage — [DOAJ](https://doaj.org/article/cfc09801314441198e3e1c92a3914e54)
- Tesis VŠE Praga: los retornos diarios cripto son difíciles de predecir y el paseo aleatorio sigue siendo un benchmark muy fuerte. Algunas estrategias long/short superan a buy-and-hold en Sharpe, sobre todo en altcoins — [VSKP](https://vskp.vse.cz/english/99320)
- arXiv 2504.18206: LightGBM tiene el menor MAE en una tabla pero la peor precisión direccional en otras (pronóstico de niveles, tablas inconsistentes) — [arXiv 2504.18206](https://arxiv.org/pdf/2504.18206)

### Inferences
- Por qué falla el ML: baja relación señal/ruido, no estacionariedad (cambios de régimen), overfitting por pruebas múltiples, costos y slippage que se comen edges de pocos puntos básicos, y fuga de información (normalizaciones o labels con datos futuros, y CV no purgada).
- Triple barrera y meta-labeling (López de Prado, *Advances in Financial Machine Learning*, 2018): son herramientas de *diseño de etiquetas y sizing*, no edges en sí. El uso recomendado aquí es meta-labeling sobre una señal primaria con fundamento (p. ej. momentum de series de tiempo) para decidir si operar y cuánto. No verifiqué en esta sesión evidencia empírica independiente fuera de muestra en cripto (no verificado; referencia candidata: Joubert 2022, "Meta-Labeling: Theory and Framework", J. Financial Data Science, no verificado).
- Usar CV purgada con embargo y la Deflated Sharpe Ratio para reportar resultados en el capstone (práctica estándar de López de Prado / Bailey; no verificado en esta sesión).

### Gaps
- No encontré una comparación revisada por pares LightGBM vs LSTM vs transformer en retornos cripto netos de costos con el mismo protocolo.
- Evidencia empírica independiente del meta-labeling en cripto: no verificada.

---

## B. Fact-check de afirmaciones de documentos internos previos

### Takeaway
La mayoría de las afirmaciones son ciertas, con matices importantes. (1) El PDT está "eliminado/reemplazado" con fecha efectiva 4-jun-2026, pero los brokers tienen hasta oct-2027 para implementarlo. (2) Lo de Alpaca "solo paper para extranjeros" es **FALSO**: Alpaca acepta cuentas live de no residentes en muchos países (Bolivia sin confirmar). (3) Lo de cointegración "fuerte" entre CEX es **PARCIAL/engañoso**. (4) Backtrader sigue en GPL-3.0 y sin mantenimiento real desde 2023.

### Cited Findings

**1. "vectorbt open-source es Apache 2.0 con Commons Clause; VectorBT PRO es comercial." → VERDADERO**
- `LICENSE.md` del repo: "Software: vectorbt / License: Apache 2.0 with Commons Clause / Licensor: Oleg Polakow". La Commons Clause prohíbe "vender" el software, incluido hosting o consultoría cuyo valor derive sustancialmente de él. GitHub lo marca como `NOASSERTION`. Repo activo: último release v1.1.2 del 2026-10-09, y ahora incluye un directorio `rust/` — [GitHub polakowo/vectorbt LICENSE.md](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md) (verificado con la API de GitHub, 16-oct-2026)
- VectorBT PRO como producto comercial de pago (suscripción/patrocinio): conocimiento previo, no re-verificado en esta sesión (no verificado).
- Implicación: no se puede ofrecer la plataforma como un SaaS de pago construido sobre vectorbt sin violar la Commons Clause. Para uso propio o académico no hay problema.

**2. "NautilusTrader es LGPL-3.0, núcleo en Rust, mismo código para backtest y live; adaptadores Binance spot/futures, Bybit, OKX." → VERDADERO (y además más amplio)**
- Licencia LGPL-3.0 según la API de GitHub. Lenguajes del repo: ~78,7 MB de Rust frente a ~4,0 MB de Python. Activo (push 2026-10-16) — [GitHub nautilus_trader](https://github.com/nautechsystems/nautilus_trader)
- Adaptadores en `crates/adapters/`: architect_ax, betfair, binance, blockchain, bybit, coinapi, coinbase, databento, deribit, derive, dydx, hyperliquid, interactive_brokers, kraken, lighter, okx, **polymarket**, sandbox, tardis (árbol de la rama develop, oct-2026) — [GitHub](https://github.com/nautechsystems/nautilus_trader/tree/develop/crates/adapters)
- "Mismo código para backtest y live" es la propuesta de diseño documentada del proyecto. No releí la documentación en esta sesión, pero es consistente con su arquitectura (no verificado textualmente). La cobertura exacta de Binance spot + USDⓈ-M/COIN-M dentro del adaptador binance no la revisé archivo por archivo (no verificado).

**3. "Backtrader es GPL-3.0 y sin mantenimiento." → VERDADERO**
- Licencia GPL-3.0 (API de GitHub). Último commit en `mementum/backtrader`: 2023-04-19; último push: 2024-08-19. No está archivado, pero no tiene desarrollo activo — [GitHub mementum/backtrader](https://github.com/mementum/backtrader)

**4. "La regla PDT de FINRA (25k USD) fue eliminada/enmendada con aprobación de la SEC el 2026-04-14, efectiva el 2026-06-04." → VERDADERO (con matiz)**
- La SEC aprobó el 14-abr-2026 la enmienda de FINRA a la Regla 4210, que elimina el mínimo de 25.000 USD y la etiqueta "pattern day trader" y los reemplaza con un marco de margen intradía. FINRA publicó el Regulatory Notice 26-10 (20-abr-2026) con fecha efectiva 4-jun-2026 — [QuantInsti](https://www.quantinsti.com/articles/finra-pdt-rule-removal-2026/); [TradeZero](https://tradezero.com/en-us/blog/the-sec-has-approved-a-rule-change-to-remove-the-current-pattern-day-trader-pdt-framework); [Schwab](https://advisorservices.schwab.com/story/introduction-to-pattern-day-trader-rules)
- Matiz: según fuentes secundarias, los brokers tienen un phase-in de hasta 18 meses (hasta ~20-oct-2027) para implementarlo, así que un broker concreto podría seguir aplicando lógica PDT un tiempo. Schwab dijo que dejaría de contar day trades desde el 8-jun. No leí la orden SEC 34-105226 ni el RN 26-10 originales (verificación solo vía brokers).
- Para el usuario en Bolivia esto es poco relevante salvo que opere acciones de EE. UU. con un broker de EE. UU.

**5. "Alpaca restringe el trading live a residentes de EE. UU.; extranjeros solo paper." → FALSO (desactualizado)**
- La página oficial de Alpaca dice que los no residentes pueden abrir cuentas live: "195+ countries" soportados en general, pero "Alpaca does not support every jurisdiction" (Canadá excluido explícitamente), según el país de residencia fiscal. No hay depósito mínimo alto: se puede fondear con 1 USD tras la aprobación — [Alpaca Learn](https://alpaca.markets/learn/live-trading-account-non-us/)
- Históricamente fue un beta solo por invitación, con un mínimo de 30.000 USD por wire internacional, mínimo que luego se levantó. Probablemente de ahí viene la afirmación — [Alpaca blog](https://alpaca.markets/blog/non-us-live-trading-beta/)
- Bolivia: no aparece mencionada. Elegibilidad no verificada; hay que consultar con Alpaca.

**6. "Binance USDⓈ-M base 0,02% maker / 0,05% taker; spot 0,1%." → VERDADERO (con matices)**
- Spot, Regular/VIP0: maker 0,100% y taker 0,100%; con BNB, 0,075% — [Binance fee schedule](https://www.binance.com/en/fee/trading)
- USDⓈ-M, Regular: 0,02% maker y 0,05% taker, confirmado por terceros (Finder) y consistente con el ejemplo del artículo de soporte de Binance (que usa 0,02%/0,05% para un Regular User en COIN-M). La página oficial de futuros no cargó las cifras en esta sesión. El descuento BNB en USDⓈ-M es del 10% — [Finder](https://www.finder.com/binance-futures-fees); [Binance soporte](https://www.binance.com/es/support/articles/360033544231)
- Matiz: las tarifas pueden variar por región o entidad, y la disponibilidad de futuros para residentes en Bolivia no está verificada.

**7. "ArcticDB es BSL 1.1." → VERDADERO**
- Business Source License 1.1 de Man Group. Change License: Apache 2.0, dos años después del release de cada versión. Additional Use Grant: se permite uso en producción, excepto ofrecerlo como "Database Service" a terceros — [ArcticDB LICENSE.txt](https://github.com/man-group/ArcticDB/blob/master/LICENSE.txt)
- Implicación: uso interno o académico sin problema.

**8. "Momentum de series de tiempo en cripto rinde >31% anualizado mientras el cross-sectional tiene drawdowns >55%" → FUENTE ENCONTRADA (VERDADERO respecto a esa fuente; PARCIAL como hecho general)**
- Fuente: Adedeji Daniel Gbadebo (2026), "Momentum Trading in Cryptocurrencies: A Comparative Study of Time-Series and Cross-Sectional Strategies", *Buhalterinės apskaitos teorija ir praktika* (Univ. de Vilnius). Usa 8 criptos principales, ene-2020 a oct-2025. TSMOM: 31,96% anual. Cross-sectional: drawdown máximo de 55,0%. TSMOM es superior en términos ajustados por riesgo — [journals.vu.lt](https://www.journals.vu.lt/BATP/en/article/view/44540)
- Advertencias: solo 8 activos y ~6 años. Solo leí el abstract, sin confirmar si es bruto o neto de costos. Es una revista de contabilidad de bajo impacto.
- Evidencia convergente: Han, Kang & Ryu encuentran TSMOM fuerte y cross-sectional débil con costos y supuestos realistas — [AUT ACFR PDF](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf). Rohrbach, Suremann & Osterrieder (2017) reportan drawdowns de ~-40% para TSMOM y ~-70% para cross-sectional, en cifras brutas — [CXO Advisory](https://www.cxoadvisory.com/momentum-investing/currency-and-cryptocurrency-exchange-rate-momentum-tests)

**9. "Los pares cripto en CEX están fuertemente cointegrados (ETH, LTC, BTC)." → PARCIAL / ENGAÑOSO**
- Keilbar & Zhang (Digital Finance, 2021): los resultados in-sample de stat-arb lucen fuertes, pero fuera de muestra "dan razón para tratar la estrategia con cautela". La no linealidad de corrección de error fue más fuerte en el pico de la burbuja, es decir, depende del régimen — [edoc.hu-berlin.de](https://edoc.hu-berlin.de/18452/27341)
- Gabriel & Kunst (IHS WP 2024): portafolios cointegrados (Johansen) con los mayores retornos anormales in- y out-of-sample; 5 de 6 estrategias son rentables fuera de muestra — [IHS](https://irihs.ihs.ac.at/id/eprint/6927/33/ihs-working-paper-2024-gabriel-kunst-cointegrated-portfolios-volatility-modeling-cryptocurrency.pdf)
- Tsoku & Makatjane (Frontiers, 2026): la cointegración estática no captura dinámicas no estacionarias; proponen cointegración dinámica — [Frontiers PDF](https://public-pages-files-2025.frontiersin.org/journals/applied-mathematics-and-statistics/articles/10.3389/fams.2026.1749337/pdf)
- Conclusión: hay cointegración intermitente y dependiente de la ventana o el régimen, no "fuerte" y estable. Hay que re-estimar en ventanas rodantes y estimar el hedge ratio sin look-ahead.

**10. "FinBERT está entrenado en noticias financieras generales, no en cripto." → VERDADERO**
- Pre-entrenamiento adicional en Reuters TRC2-financial (2008-2010) y fine-tuning en Financial PhraseBank (LexisNexis). No contiene corpus cripto — [arXiv 1908.10063](https://arxiv.org/pdf/1908.10063)
- Alternativa: CryptoBERT (StockTwits/Telegram/Reddit/Twitter cripto) — [Hugging Face](https://huggingface.co/ElKulako/cryptobert)

### Inferences
- Correcciones a propagar a los documentos previos: (a) Alpaca sí ofrece cuentas live a no residentes, aunque falta verificar Bolivia; (b) "fuertemente cointegrados" debe cambiarse por "cointegración inestable, dependiente del régimen"; (c) añadir que NautilusTrader ya trae un adaptador de Polymarket, lo que facilita la estrategia A3 en la misma plataforma; (d) la cifra de TSMOM de 31,96% sale de un paper pequeño (8 activos) y no debe presentarse como consenso.

### Gaps
- No leí los documentos primarios de la SEC (Release 34-105226) ni de FINRA (RN 26-10); la verificación del punto 4 es vía brokers.
- Las tarifas USDⓈ-M no se confirmaron en la página oficial de Binance (solo artículo de soporte + terceros).
- Elegibilidad de Bolivia en Alpaca, Binance Futures, Kalshi y Polymarket: no verificada.
- Comercialidad o precio actual de VectorBT PRO: no verificado en esta sesión.
