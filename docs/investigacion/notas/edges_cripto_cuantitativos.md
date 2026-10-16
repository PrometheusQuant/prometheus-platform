# Edges cuantitativos sistemáticos en cripto para un trader individual no-HFT (< 1.000 USD), 2026

> Notas de investigación (octubre de 2026). Convención: **[primaria/peer-review]**, **[working paper]**, **[secundaria/practitioner]**. Las cifras que no pude contrastar con la fuente original llevan "(no verificado)". Presupuesto de búsqueda limitado (~16 llamadas): varias tablas de papers solo se leyeron vía abstract y se indica.

---

## 1. Carry de funding rate y cash-and-carry / basis en perpetuos

### Takeaway
Es el edge con mejor respaldo académico y un mecanismo económico claro: demanda minorista de exposición larga apalancada más capital de arbitraje limitado. Un paper de arXiv (He, Manela, Ross, von Wachter) reporta Sharpe ≈1,8 en BTC con costes "retail" en Binance para 2020-03/2024. Pero las desviaciones se reducen ≈11 %/año, y desde 2024-2025 el funding "normal" se ancla cerca de 0,01 %/8h (≈11 % anual bruto), con compresiones fuertes tras desapalancamientos (octubre de 2025). Con < 1.000 USD es viable, pero los retornos absolutos son pequeños y el riesgo de contraparte del exchange es dominante.

### Cited Findings
- **Mecanismo (BIS WP 1087, Schmeling, Schrimpf & Todorov, abr-2023) [working paper banco central]:** el carry de futuros cripto (BTC, ETH) "puede llegar a ser muy grande (hasta 60 % anual)", con una media superior al 10 % anual, y es mucho mayor que el carry en acciones, renta fija, divisas o materias primas. Los diferenciales de tipos de interés explican muy poco. El carry lo explican yields de conveniencia ligados a la demanda de inversores pequeños que persiguen tendencia y buscan exposición apalancada, y a la escasez de capital de arbitraje dispuesto a montar cash-and-carry, porque esas posiciones sufren picos de margen y liquidaciones en las caídas — [BIS WP 1087](https://www.bis.org/publ/work1087.pdf); [página BIS](https://www.bis.org/publications/working-paper-1087-crypto-carry)
- **Conflicto menor:** el abstract del PDF habla de "hasta 60 % p.a."; el registro RePEc menciona ">40 %" — [BIS RePEc](https://www.bis.org/RePEc/bis/biswps/work1087.redif). Existe una versión posterior como CEPR DP20719 (2025) — [CEPR](https://cepr.org/publications/dp20719)
- **Riesgo de crash:** un carry alto predice caídas futuras del precio, y un carry creciente coincide con un encarecimiento del seguro contra crash. Es decir, el carry no es "gratis": compensa riesgo de cola — [BIS WP 1087](https://www.bis.org/publ/work1087.pdf)
- **No pude extraer de la página** el periodo muestral, el Sharpe de la estrategia de carry ni los supuestos de costes del BIS WP 1087 (solo leí el abstract y la introducción) — [BIS WP 1087](https://www.bis.org/publ/work1087.pdf)
- **He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures" (arXiv 2212.06888, v6 ago-2024) [working paper]:**
  - Muestra: Binance, frecuencia horaria, 2020-01-08 a 2024-03-11 para BTC y ETH (BNB, DOGE y ADA empiezan algo después) — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - Desviación absoluta media del perpetuo frente al precio de no-arbitraje: ≈57 % anual en BTC, 63 % en ETH y 83-88 % en altcoins (BNB, DOGE, ADA). La media con signo es ≈0 — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - **Sharpe anualizado con costes "High" (retail; spot 6,75 pb, futuros 1,44 pb):** BTC 1,80, ETH 2,55, BNB 4,84, DOGE 3,58, ADA 2,68. Sin costes, BTC 3,53. Exceso de retorno anual (High): BTC 6,38 % (max DD −4,43 %), ETH 9,59 % (DD −3,94 %), DOGE 23,31 % (DD −8,56 %) — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - Restricción solo long spot (sin short spot, que es el caso realista de un minorista): Sharpe BTC 1,62 y ETH 2,23 — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - Descomposición en BTC: retorno en exceso total de 13,70 %, del que 8,64 % viene de la convergencia de precio (timing) y 5,06 % de los pagos de funding — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - **Decaimiento:** |desviación| cae ≈11 % por año, más de 44 % acumulado en la muestra. Sharpe anual de BTC (High): 2,26 (2020), 2,39 (2021), 0,70 (2022), 1,32 (2023); en 2022 la estrategia solo estuvo activa el 9,21 % del tiempo — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
  - Nota de consistencia: los costes "High" del paper (1,44 pb en futuros) son **muy inferiores** a la tarifa taker VIP0 actual de Binance en futuros (≈4-5 pb) — ver la sección de comisiones. Reproducir el Sharpe con tarifa retail real exige operar como maker — [arXiv HTML v5](https://arxiv.org/html/2212.06888v5)
- **Compresión 2024-2026 [secundaria]:** el informe de derivados de BitMEX del 3T 2025 afirma que el ciclo 2024-2025 estableció un "nuevo normal" con funding medio cerca de 0,01 %/8h (≈11 % anualizado), por debajo de ciclos alcistas previos — [BitMEX 2025Q3 derivatives report](https://testnet.bitmex.com/blog/2025q3-derivatives-report) (nota: la URL es el dominio testnet de BitMEX)
  - Nota del investigador: 0,01 %/8h es también el tipo de interés por defecto incorporado en la fórmula de funding de Binance y otros exchanges. Por eso esa "base" refleja en parte el diseño del contrato y no solo la demanda (inferencia; ver Inferences).
- **Ethena / sUSDe [secundaria]:** un análisis atribuye la compresión de spreads tras el crash de octubre de 2025 a la purga de apalancamiento: bajaron los funding rates, los yields DeFi siguieron y se deshicieron estrategias apalancadas con sUSDe — [análisis Ethena](https://san-1510.aid.brainsum.com/news/analysis/ethena-under-pressure-through-market-noise) (fuente de calidad dudosa)
- Una página de Pendle/4pillars destaca la fuerte volatilidad del APY de sUSDe derivada de la volatilidad del funding — [4pillars Boros](https://4pillars.io/en/issues/trade-funding-rates-with-pendle-boros)
- Ethena planea migrar parte del basis trade a perpetuos sobre acciones, con funding de referencia de ≈14 % (Hyperliquid) y ≈17,5 % (Binance) en esos contratos, frente a funding de BTC en "un dígito bajo" — [Coinspot](https://coinspot.io/en/company/ethena-perpetual-equity-contracts-ethena-seeks-new-yield-for-usde-in-perpetual-equity-contracts/) (no verificado)
- Una cifra de "19-22 % anualizado con drawdowns < 2 %" para el arbitraje de funding aparece en un glosario sin fuente — [spark.money](https://www.spark.money/glossary/funding-rate) (no verificado; descartar)
- sUSDe se lista en ≈9-12 % APY a mediados de 2026 — [eco.com](https://eco.com/support/en/articles/12272109-stablecoin-lending-platforms-2026) (secundaria, no verificado)
- Binance liquida el funding cada 8 h, y el histórico completo de funding realizado está disponible vía API — [dccd docs](https://download-crypto-currencies-data.readthedocs.io/en/latest/how-to/derivatives.html)

### Inferences
- **Economía para < 1.000 USD:** delta-neutral con 500 USD en spot y 500 USD de margen en el short perp (1x efectivo) a ≈11 % bruto anual sobre el nocional da ≈55 USD/año sobre 1.000 de capital. Eso es ≈5,5 % sobre el capital total antes de comisiones de entrada y salida (4 patas: 2 × spot 0,1 % + 2 × perp ≈0,05 % ≈ 0,3 % del nocional ≈ 1,5 USD por ciclo). Es positivo, pero comparable al yield de stablecoins en Aave (3-7 %) y con más riesgo operativo. El atractivo real está en el **timing** (entrar solo cuando el funding o el basis anualizado supera un umbral alto, y en altcoins), como hace la estrategia de He et al., donde el 63 % del retorno vino de la convergencia y no del funding.
- **Eficiencia de capital:** con margen cruzado o Portfolio Margin (spot como colateral) se puede elevar el nocional, pero eso aumenta el riesgo de liquidación del short en un squeeze. Con 1x-2x en el short y margen aislado amplio, el riesgo de liquidación ante un +50 % es bajo.
- **Riesgo dominante:** contraparte o exchange (estilo FTX), autodesapalancamiento (ADL), funding negativo prolongado en mercados bajistas y riesgo de depeg del colateral en stablecoins. Las altcoins tienen funding más alto pero riesgo de delisting y squeeze.
- **Datos:** el funding histórico es gratuito (API de Binance y Data Vision), al igual que las klines spot y perp. Es la estrategia más fácil de backtestear con datos gratuitos.
- **Prioridad: 1 (alta).**

### Gaps
- No obtuve el Sharpe ni el periodo exacto del BIS WP 1087 (no se leyó el PDF completo).
- No encontré una medición académica del retorno neto del basis/funding en 2025-2026. La evidencia de compresión es de BitMEX (parte interesada) y de prensa.
- No verifiqué series de funding medio de Binance para 2025-2026 directamente desde los datos.

---

## 2. Momentum de series temporales (trend following) y momentum cross-sectional

### Takeaway
El momentum es un factor documentado en cripto en revista top (Liu, Tsyvinski & Wu, *Journal of Finance* 2022: mercado + tamaño + momentum). El trend following con volatility targeting muestra Sharpe netos > 1 en backtests de practitioners y preprints, pero la evidencia post-2022 es mayoritariamente preprint o practitioner y las lookbacks cortas se las comen las comisiones. Para un minorista es el segundo edge más sólido: horizonte diario o semanal, 1-3 activos líquidos, rebalanceo poco frecuente.

### Cited Findings
- **Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" [peer-review]:** *Journal of Finance* (2022), 77(2), pp. 1133-1177, DOI 10.1111/jofi.13119. Tres factores (mercado, tamaño y momentum) capturan los retornos esperados cross-sectional, y ~10 características forman estrategias long-short significativas, todas explicadas por el modelo de 3 factores — [SSRN](https://papers.ssrn.com/abstract=3379131); [NBER w25882](https://www.nber.org/papers/w25882.pdf); [listado SUFE](https://academicnewsletter.sufe.edu.cn/info/359095)
  - Muestra: monedas con capitalización > 1 M USD, 2014 (109 monedas) a 2018 (1.583), carteras semanales por quintiles — [CXO Advisory](https://cxoadvisory.com/size-effect/cryptocurrency-factor-model) (secundaria)
- Liu & Tsyvinski, "Risks and Returns of Cryptocurrency" (RFS 2021), documentan momentum de series temporales en BTC — sin fuente recuperada en esta sesión (no verificado; ver Gaps).
- **Man AHL, "In Crypto We Trend" (dic-2024) [secundaria, practitioner institucional]:** el ratio riesgo/retorno de una cartera trend en cripto alcanza su máximo con ~10-15 monedas; a partir de ahí los costes y la liquidez superan a la diversificación — [Man Group](https://www.man.com/insights/in-crypto-we-trend)
- **Monash Centre for Financial Studies:** las estrategias trend con lookbacks cortos dan Sharpe alto, pero los costes por rebalanceo frecuente reducen el beneficio — [Monash](https://www.monash.edu/business/mcfs/our-research/all-projects/investment-strategy/trend-following-strategies-for-crypto-investors)
- **"Catching Crypto Trends" (Barbon):** una cartera rotacional top-20 con Sharpe > 1,5 neto de comisiones (no verificado) — [abarbon.com](https://abarbon.com/papers/catching-crypto-trends)
- **AdaptiveTrend (arXiv 2602.11708, 2026) [preprint, un solo autor]:**
  - Sharpe OOS de 2,41 en 2022-2024 (70/30 long-short), con costes de 4 pb taker, slippage y funding — [arXiv 2602.11708](https://arxiv.org/pdf/2602.11708)
  - Su benchmark TSMOM escalado por volatilidad tiene Sharpe 1,83, mientras que el TSMOM simple a 1 y 3 meses cae a ≈0,65 y ≈0,54 — [arXiv 2602.11708](https://arxiv.org/pdf/2602.11708)
  - Cifras autodeclaradas en un backtest (no verificado)
- **Momentum cross-sectional, fragilidad:** no recuperé cifras de drawdown de crashes de momentum cross-sectional en cripto en esta sesión (ver Gaps).

### Inferences
- **Mecanismo:** infrarreacción y extrapolación minorista, flujos de atención, y el mismo motor de demanda minorista "trend-chasing" que identifica el BIS para el carry. Los dos edges comparten raíz y están correlacionados (el carry alto coincide con tendencias alcistas).
- **Decaimiento:** el gap entre TSMOM simple (Sharpe ≈0,5-0,65 en 2022-2024, según AdaptiveTrend) y la versión con volatility targeting (1,83) sugiere que la mayor parte del valor reciente viene del **escalado por volatilidad** y no de la señal pura.
- **Cross-sectional:** requiere shortear altcoins (perps), es más caro, y los factores tamaño/momentum de LTW se estimaron con monedas muy ilíquidas (2014-2018). Es poco transferible a < 1.000 USD con perps de Binance: tamaños mínimos, funding y slippage en altcoins.
- **Capital mínimo:** trend en BTC/ETH spot o perp es viable con 100-1.000 USD (el nocional mínimo de los perps de Binance es bajo). Con 0,1 % por lado en spot y ~20-50 cambios de posición al año, el coste anual es ≈4-10 % del capital. Mejor usar perps con órdenes maker o rebalanceos con banda de no-trade.
- **Datos:** klines diarias y horarias gratuitas en Data Vision desde 2017 para spot (aprox.).
- **Prioridad: 2 (alta).** Es el núcleo direccional más robusto.

### Gaps
- No leí Liu & Tsyvinski (RFS 2021) ni obtuve cifras de Sharpe del TSMOM de BTC.
- No hay evidencia peer-review que encontrara sobre TSMOM cripto neto 2023-2026.
- No encontré estudios de crashes de momentum cross-sectional en cripto con cifras de drawdown.

---

## 3. Mean reversion, pairs trading y cointegración

### Takeaway
La evidencia es débil o negativa: los estudios que encontré (uno en revista y dos tesis) reportan rendimientos netos negativos o por debajo del buy-and-hold tras costes, y la cointegración entre criptos es inestable (cambios de tokenomics, upgrades). Prioridad baja para este contexto.

### Cited Findings
- **Quantitative Finance and Economics (2026), pairs trading con cópulas [peer-review, revista menor]:** las estrategias generaron retornos netos negativos tras costes de transacción. Solo la variante "Alpha Overlay", con exposición direccional, siguió de cerca al buy-and-hold — [AIMS QFE 2026](https://www.aimspress.com/aimspress-data/qfe/2026/2/PDF/QFE-10-02-016.pdf)
- **Tesis de máster (Universidade Católica Portuguesa, 2021):** con Engle-Granger, Johansen y Phillips-Perron sobre el top-10 de criptos, todas las carteras quedaron por debajo del buy-and-hold con y sin costes. Las ventanas de testeo largas funcionaron mejor que las cortas — [UCP](https://ciencia.ucp.pt/en/studentTheses/pairs-trading/)
- **Tesis de la Universidad de Turku (datos 2020-2022):** el método de distancia fue el peor y perdió dinero. No pude ver los resultados de cointegración — [UTUPub](https://www.utupub.fi/handle/11111/24573)
- **[secundaria]:** guías de practitioners señalan que las rupturas estructurales (upgrades de protocolo, cambios de tokenomics) pueden romper permanentemente la cointegración y recomiendan monitorizar p-values en ventana rodante. Un par implica 4 transacciones por ida y vuelta — [claudeskills.info](https://claudeskills.info/skills/agiprolabs/claude-trading-skills/cointegration-analysis/) (fuente de baja calidad)

### Inferences
- **Coste:** con 4 patas a 0,1 % (spot VIP0), el spread tiene que revertir más de ≈0,4 % para cubrir comisiones, o ≈0,2 % con perps maker o taker. Los spreads intradía rara vez dan eso de forma fiable.
- **Kalman:** las hedge ratios con filtro de Kalman reducen el problema de inestabilidad pero no lo eliminan; no encontré evidencia neta publicada (gap).
- **Mean reversion de corto plazo** (reversal a 1 día o intradía en altcoins) podría existir, pero es justamente el horizonte donde dominan las comisiones.
- **Prioridad: 6 (baja).** Solo como diversificador experimental con perps maker.

### Gaps
- No encontré un paper peer-review con pairs trading cripto basado en cointegración más filtro de Kalman, neto de costes y post-2022.
- No hay medición sistemática de la frecuencia de rupturas de cointegración en pares cripto.

---

## 4. Prima de riesgo de volatilidad (VRP) vendiendo opciones (Deribit)

### Takeaway
Existe una VRP grande en BTC: varianza implícita ≈0,72 frente a realizada ≈0,58 anualizadas, VRP ≈0,14 frente a ≈2 % en el S&P 500 (Almeida et al., arXiv 2410.15195). Pero no encontré un backtest neto de una estrategia de venta de opciones en Deribit. Con < 1.000 USD el contrato mínimo (0,1 BTC en Deribit; no verificado en esta sesión) y el riesgo de cola la hacen poco práctica.

### Cited Findings
- **Almeida, Grith, Miftachov & Wang, "Risk Premia in the Bitcoin Market" (arXiv 2410.15195) [working paper]:** con datos de opciones BTC de Deribit, la varianza risk-neutral (BVIX²) es 0,72 y la realizada 0,58 (anualizadas, mensuales). La VRP es 0,14, mucho mayor que la del S&P 500 (~2 %) — [arXiv 2410.15195](https://arxiv.org/html/2410.15195v2)
- **Dependencia del régimen:** VRP más alta en el régimen de baja volatilidad (≈0,17) que en el de alta volatilidad (≈0,12) — [arXiv 2410.15195](https://arxiv.org/html/2410.15195v2); [Harbourfront Quant](https://harbourfrontquant.substack.com/p/return-and-variance-risk-premia-in) (secundaria)
- **Alexander & Imeraj (2020, J. Alternative Investments):** construyen índices de volatilidad implícita de BTC con más de 7 millones de precios de opciones de Deribit (mar-2019 a mar-2020) — [Sussex repository](https://sro.sussex.ac.uk/id/eprint/91094/)
- **Atanasova et al.:** los market makers con posiciones netas largas exigen una prima de iliquidez, lo que afecta a quién captura los retornos de las opciones — [AUT ACFR](https://acfr.aut.ac.nz/__data/assets/pdf_file/0006/969378/950002_Atanasova_Illiquidity-Premium-and-Crypto-Option-Returns.pdf)

### Inferences
- **Mecanismo:** demanda de protección y convexidad (calls apalancadas por minoristas, puts de cobertura) y aversión al riesgo de saltos. Los vendedores cobran por asumir riesgo de cola.
- **Riesgo:** los saltos de BTC (−30-50 % en días) pueden borrar años de prima. Exige hedging delta y sizing pequeño. Con < 1.000 USD es difícil diversificar strikes y vencimientos.
- **Alternativas:** opciones con tamaño mínimo reducido en otros venues, o productos "Dual Investment" de Binance, que son una put/call vendida empaquetada con prima menos transparente (inferencia).
- **Datos:** el histórico tick de opciones de Deribit en general no es gratuito con historia larga (proveedores de pago como Tardis; no verificado). Es un obstáculo para el backtest.
- **Prioridad: 5 (media-baja)** para este capital.

### Gaps
- No encontré un backtest académico neto de costes de venta sistemática de opciones en Deribit, ni sus drawdowns.
- No verifiqué el tamaño mínimo de contrato, las comisiones de Deribit ni sus condiciones de acceso a datos históricos.

---

## 5. Provisión de liquidez en DEX/AMM (Uniswap v3)

### Takeaway
La evidencia es contundente: los LPs pasivos pierden frente a holdear. Loesch et al. encuentran IL de $260,1 M frente a $199,3 M en fees y que el 49,5 % de los LPs tuvo retornos negativos. La teoría LVR (Milionis et al.) explica por qué la selección adversa contra arbitrajistas es un coste estructural. Para un minorista no es un edge: es una venta de opcionalidad mal pagada.

### Cited Findings
- **Loesch, Hindman, Richardson & Welch, "Impermanent Loss in Uniswap v3" (arXiv 2111.09192, 2021):** en pools no estables con TVL > 10 M USD (≈43 % del TVL de v3), el IL superó a las fees en casi todos los pools; el LP medio habría ganado más holdeando — [arXiv 2111.09192](https://arxiv.org/pdf/2111.09192)
  - Cifras agregadas: $260,1 M de IL frente a $199,3 M de fees, con el 49,5 % de los LPs en negativo — [Nasdaq](https://www.nasdaq.com/articles/half-of-uniswap-liquidity-providers-are-losing-money) (secundaria; atribuye el estudio a Bancor, de donde procedían los autores)
  - Los "flash LPs" o JIT, que proveen liquidez durante un solo bloque, son la excepción — [arXiv 2111.09192](https://arxiv.org/pdf/2111.09192)
- **Milionis, Moallemi, Roughgarden & Zhang, "Automated Market Making and Loss-Versus-Rebalancing" (arXiv 2208.06046, v5 may-2024):** derivan una "fórmula Black-Scholes para AMMs". LVR es el coste de selección adversa por precios rancios explotados por arbitrajistas informados, y el modelo replica empíricamente los retornos reales de los LPs — [arXiv 2208.06046](https://arxiv.org/abs/2208.06046v4)

### Inferences
- **Mecanismo de la *pérdida*:** el LP es contraparte de arbitrajistas CEX-DEX más rápidos. El LVR escala con σ², así que en cripto es grande. Sin bloques privados, MEV ni hedging dinámico, un minorista no compite.
- **Costes:** gas, gestión de rangos y rebalanceos. En L2 el gas es bajo, pero el LVR persiste.
- **Prioridad: 8 (descartar)** salvo pools estable-estable, que son de facto un yield pasivo y caen en la categoría 6.

### Gaps
- No tengo datos 2024-2026 sobre la rentabilidad de LPs en Uniswap v4 o con hooks anti-LVR.

---

## 6. Yield pasivo: staking, lending, Binance Earn, stablecoins

### Takeaway
A mediados de 2026 las cifras orientativas son: staking de ETH ≈2,5-3,8 %, lending de USDC en Aave ≈3-7 % y vaults curadas de Morpho/Spark ≈4-8 %. Las fuentes son de vendors y deben tratarse como aproximadas. No es un "edge" sino retorno de referencia (hurdle rate): cualquier estrategia activa debe batirlo ajustado por riesgo.

### Cited Findings
- Staking en solitario de ETH ≈3,1-3,8 % APY incluyendo MEV (requiere 32 ETH); Lido (stETH) ≈2,5-3,0 % tras su comisión del 10 % — [spark.money](https://www.spark.money/tools/crypto-yield-calculator) (secundaria, no verificado)
- **Compresión del staking:** el post de riesgo de Aave de agosto de 2026 indica que la participación en staking de ETH creció un 19 % en lo que va de año, hasta ≈42,4 M ETH (34,7 % de la oferta), lo que diluye la recompensa por staker — [Aave governance](https://governance.aave.com/t/risk-stewards-august-2026-weth-interest-rate-adjustment/25535)
- Supply de USDC en Aave ≈3-6 % / 3,5-7 % según cadena y utilización; Morpho/Spark ≈4-8 %; sUSDe ≈9-12 % con más riesgo — [eco.com](https://eco.com/support/en/articles/12271620-best-defi-lending-platforms-2026); [eco.com stablecoin](https://eco.com/support/en/articles/12272109-stablecoin-lending-platforms-2026) (secundaria, no verificado)

### Inferences
- **Riesgos:** smart contracts, depeg, custodia en CEX (Binance Earn) y regulación. El yield de sUSDe es en esencia el carry del punto 1 empaquetado, con riesgo añadido de protocolo.
- Para < 1.000 USD, la diferencia entre 4 % y 8 % son 40 USD al año. La relevancia es de **benchmark** y de **colateral productivo** (usar stablecoins con yield como margen), no de fuente principal de retorno.
- **Prioridad: 3** como base o hurdle y como gestión del capital ocioso de las otras estrategias.

### Gaps
- No verifiqué las APYs actuales de Binance Earn (Simple Earn de USDT/USDC) en 2026.

---

## 7. Efectos de calendario y estacionalidad

### Takeaway
La evidencia académica es mixta o negativa: Baur et al. encuentran efectos variables en el tiempo pero sin patrones consistentes. Hay hallazgos de practitioners (lunes y viernes fuertes; ventana 21:00-23:00 UTC) sin validación robusta. No encontré estudios sobre retornos alrededor de las horas de liquidación del funding, salvo un preprint de 2026 sobre efectos de cuarto de hora.

### Cited Findings
- **Baur, Cahill, Godfrey & Liu (2017; UWA):** con más de 15 M de observaciones de 7 exchanges, encuentran efectos de hora del día, día de la semana y mes que varían en el tiempo, pero "ningún patrón consistente o persistente" en la muestra — [UWA](https://research-repository.uwa.edu.au/en/publications/bitcoin-time-of-day-day-of-week-and-month-of-year-effects-in-retu/)
- **NYDIG (2021) [practitioner]:** viernes y comienzo de semana mejores; atribuyen la fuerza del lunes a que el fiat no llega a los exchanges en fin de semana. Poco relevante a nivel horario — [NYDIG](https://nydig.com/wp-content/uploads/2021/03/NYDIG-The-Temporalities-of-Bitcoin-Returns.pdf)
- **Quantpedia (datos horarios de Gemini, 2015-2022) [practitioner]:**
  - Ninguna hora es estadísticamente negativa; las peores son las 03:00-04:00 UTC — [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/)
  - Proponen mantener BTC solo de 21:00 a 23:00 UTC, con un retorno anualizado del 33 % (backtest; no verificado) — [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/)
- **"The Quarter-Hour Effect" (arXiv 2607.09426, jul-2026) [preprint]:** con trades de 6 perpetuos de Binance, los retornos en la apertura de cada cuarto de hora son predecibles fuera de muestra, y el order imbalance en esa apertura predice retornos a 4-12 horas — [arXiv 2607.09426](https://arxiv.org/pdf/2607.09426)

### Inferences
- **Mecanismo plausible:** flujos algorítmicos periódicos (TWAP o rebalanceos en horas redondas, liquidaciones del funding, fixings de ETF a las 16:00 ET). Es débil y propenso a data-mining.
- Una estrategia de ventana de 2 h diaria implica ~730 trades al año. Con 0,1 % por lado en spot el coste es ≈73 %/año, lo que destruye el 33 % bruto de Quantpedia. Solo es viable como **filtro de timing** de ejecución de otras estrategias, no como estrategia independiente.
- **Prioridad: 7 (baja)**; útil como overlay de ejecución.

### Gaps
- No hay evidencia sólida sobre retornos alrededor de las liquidaciones de funding (00/08/16 UTC).
- No hay estudios robustos post-ETF (2024-2026) de efectos de fin de semana.

---

## 8. Señales de microestructura / order flow (minutos a horas, sin colocation)

### Takeaway
La evidencia a horizontes de minutos es escasa y mayoritariamente de "predicción", no de rentabilidad neta. El hallazgo más útil para un minorista es que el order imbalance predice a **4-12 horas** (no a minutos) en perps de Binance (preprint de 2026), un horizonte compatible con costes taker si la señal es fuerte.

### Cited Findings
- El order imbalance en las aperturas de cuarto de hora predice retornos a 4-12 h, con efectos mucho más débiles a frecuencias más finas — [arXiv 2607.09426](https://arxiv.org/pdf/2607.09426)
- Rahman & Upadhye (arXiv 2411.08382): un modelo híbrido VAR + red neuronal mejora la predicción del OFI con datos de Binance (precisión de pronóstico, no P&L) — [arXiv 2411.08382](https://arxiv.org/abs/2411.08382v1)
- **[secundaria]:** un paper que aplica el marco de Evans-Lyons a cripto encuentra que el order flow mundial explica el 11 % de los retornos diarios — [tradingstrategy.ai](https://tradingstrategy.ai/docs/learn/order-flow.html) (no verificado)

### Inferences
- A horizontes de 1-5 minutos, el ruido más el spread más 4-10 pb de comisión hacen que la señal casi nunca sea explotable sin rebates de maker ni latencia baja.
- Con datos gratuitos de aggTrades (taker buy/sell) y el `metrics` de Data Vision (OI, ratios long/short, taker volume) se pueden construir features horarias para combinar con trend o carry.
- **Prioridad: 4 (media)** como feature y filtro, no como estrategia autónoma.

### Gaps
- No encontré papers con rentabilidad neta de señales OFI a 1-60 minutos en cripto, ni evidencia de decaimiento.

---

## Anexo A: Comisiones de Binance y fuentes de datos gratuitas

### Takeaway
En spot VIP0 la comisión es de 0,100 % maker y taker (0,075 % pagando con BNB), según la página oficial de Binance. Para USDⓈ-M VIP0, las fuentes secundarias dan 0,02 % maker y 0,05 % taker (hay una fuente que dice 0,04 % taker), con 10 % de descuento pagando con BNB. No pude cargar la tabla oficial de futuros. Los datos de klines, aggTrades y trades de spot, futuros UM y CM son gratuitos en Data Vision; funding, open interest y ratios tienen matices.

### Cited Findings
- **Binance spot, VIP0 (oficial):** 0,100 % maker / 0,100 % taker, 0,075 % / 0,075 % con descuento BNB — [Binance fee schedule](https://www.binance.com/en/fee/schedule)
- **USDⓈ-M VIP0 (secundaria, no verificado en página oficial):** 0,02 % maker / 0,05 % taker — [Finder](https://www.finder.com/cryptocurrency/trading/binance-futures-fees); [TradersUnion](https://tradersunion.com/brokers/crypto/view/binance/futures-fees/)
  - **Conflicto:** un blog de referidos da 0,04 % taker — [blog.udn](https://blog.udn.com/c92b6c76/189284512)
  - El descuento BNB en USDⓈ-M es del 10 % — [Binance support](https://www.binance.com/es/support/articles/360033544231)
  - La página oficial de futuros no mostró la tabla sin sesión iniciada — [Binance futureFee](https://www.binance.com/en/fee/futureFee)
- **Binance Data Vision / binance-public-data:**
  - Datasets: Spot, USD-M y COIN-M, con aggTrades, klines y trades; ficheros diarios y mensuales — [GitHub binance-public-data](https://github.com/binance/binance-public-data)
  - Intervalos de klines de 1 s a 1 mes — [GitHub binance-public-data](https://github.com/binance/binance-public-data)
  - Los timestamps de spot pasan a microsegundos desde el 2025-01-01 — [GitHub binance-public-data](https://github.com/binance/binance-public-data)
  - Hubo correcciones de archivos en 2022-04-21 y 2022-08-08, y cada zip trae su CHECKSUM — [GitHub binance-public-data](https://github.com/binance/binance-public-data)
- **`metrics` de futuros UM:** incluyen sum_open_interest, sum_open_interest_value, ratios long/short y taker volume (ejemplos de ene-2023) — [GitHub issue #211](https://github.com/binance/binance-public-data/issues/211)
  - **Conflicto o duda:** el issue sugiere que la granularidad del OI disponible en el archivo es limitada, mientras que la API de OI solo sirve los últimos 30 días — [dccd docs](https://download-crypto-currencies-data.readthedocs.io/en/latest/how-to/derivatives.html)
  - Recuerdo (no verificado en esta sesión) que el `metrics` diario de Data Vision viene en filas de 5 minutos. Hay que comprobarlo descargando un fichero.
- **Funding de Binance:** liquidación cada 8 h (algunos símbolos tienen intervalos distintos; no verificado), con histórico completo vía API — [dccd docs](https://download-crypto-currencies-data.readthedocs.io/en/latest/how-to/derivatives.html)

### Inferences
- **Coste de ida y vuelta realista para backtests** (VIP0, sin BNB):
  - Spot: 0,20 %
  - Perp taker/taker: 0,10 %
  - Perp maker/maker: 0,04 %
  - Más slippage de 1-5 pb en BTC/ETH y bastante más en altcoins
- Para el carry, con spot taker más perp taker a la entrada y a la salida, el coste ≈0,30 % del nocional se recupera con ≈3 días de funding a 0,03 %/8h, o ≈10 días a 0,01 %/8h.

### Gaps
- No verifiqué la tabla oficial de USDⓈ-M, la disponibilidad o historia de `fundingRate`, `bookTicker` y `bookDepth` en Data Vision, el acceso a datos históricos de Deribit ni los límites de los tiers gratuitos de Coinglass y CryptoQuant. Quedaron fuera por límite de búsquedas.

---

## Anexo B: Ranking de prioridad para < 1.000 USD, no-HFT (inferencia del investigador)

| # | Edge | Evidencia | Decaimiento 2023-26 | Viabilidad < 1k | Datos gratis |
|---|---|---|---|---|---|
| 1 | Carry funding / basis (timing por umbral) | Fuerte (BIS WP, arXiv con Sharpe 1,8 retail) | Sí (−11 %/año en desviaciones; base ≈0,01 %/8h) | Alta (riesgo de exchange) | Sí |
| 2 | Trend TSMOM con vol targeting en BTC/ETH | Fuerte para factor (JF 2022); preprints netos | Señal simple debilitada; vol-target ayuda | Alta | Sí |
| 3 | Yield pasivo (benchmark / colateral) | Descriptiva | Staking comprimiéndose | Alta | n/a |
| 4 | Order flow / OI como feature (horas) | Débil a moderada (preprints) | Desconocido | Media | Parcial |
| 5 | VRP (venta de opciones) | Moderada (VRP ≈0,14) | Desconocido | Baja (mínimos, cola) | No (largo plazo) |
| 6 | Pairs / cointegración | Negativa neta | — | Baja | Sí |
| 7 | Calendario / estacionalidad | Mixta, no robusta | — | Solo como overlay | Sí |
| 8 | LP en Uniswap v3 | Negativa (IL > fees; LVR) | — | Descartar | Sí |
