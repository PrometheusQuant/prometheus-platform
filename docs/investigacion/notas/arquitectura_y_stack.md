# Arquitectura de software y stack tecnológico para una plataforma de trading algorítmico multiestrategia (1-2 devs, cripto/Binance, octubre 2026)

> Notas de investigación. Fecha de corte: 16-oct-2026. Algunas referencias canónicas (Fowler, Shopify, LMAX) se citan por su URL oficial conocida; no se volvieron a descargar en esta sesión. Las estimaciones de RAM son **inferencias propias** (marcadas como tales), no mediciones publicadas.

## 1. Estilo arquitectónico: monolito modular vs microservicios, hexagonal, event-driven, CQRS

### Takeaway
Para 1-2 desarrolladores, lo indicado es un **monolito modular** con **arquitectura hexagonal (puertos y adaptadores)**: un núcleo de estrategia/riesgo sin dependencias de exchange, y adaptadores para Binance, almacenamiento y notificaciones. Encima va un **bus de eventos en proceso** con un **journal append-only** (inspirado en LMAX y en event sourcing ligero) para auditar todo. Los microservicios no se justifican antes de la etapa 3.

### Cited Findings
- Fowler, "MonolithFirst": casi todos los sistemas de microservicios exitosos empezaron como monolito que luego se dividió; empezar directamente con microservicios suele acabar en problemas porque los límites correctos solo se descubren con el tiempo — [martinfowler.com/bliki/MonolithFirst.html](https://martinfowler.com/bliki/MonolithFirst.html)
- Fowler, "MicroservicePremium": los microservicios tienen un "premium" de complejidad operativa que solo compensa en sistemas grandes o complejos — [martinfowler.com/bliki/MicroservicePremium.html](https://martinfowler.com/bliki/MicroservicePremium.html)
- Shopify mantuvo su núcleo como monolito Rails y lo convirtió en "monolito modular" con límites de componentes explícitos (herramienta Packwerk), en vez de migrar a microservicios — [Shopify Engineering: Deconstructing the Monolith](https://shopify.engineering/deconstructing-monolith-designing-software-maximizes-developer-productivity)
- LMAX: lógica de negocio en un solo hilo, en memoria, alimentada por eventos de entrada que se registran en un journal antes de procesarse, lo que permite reconstruir el estado reproduciendo el journal (event sourcing) — [Fowler, The LMAX Architecture](https://martinfowler.com/articles/lmax.html)
- Event sourcing: todo cambio de estado se guarda como secuencia de eventos; da auditoría completa y permite reconstruir estados pasados — [martinfowler.com/eaaDev/EventSourcing.html](https://martinfowler.com/eaaDev/EventSourcing.html)
- CQRS: separar el modelo de escritura del de lectura; Fowler advierte que en la mayoría de los sistemas añade complejidad arriesgada y que conviene usarlo solo en partes concretas — [martinfowler.com/bliki/CQRS.html](https://martinfowler.com/bliki/CQRS.html)
- Arquitectura hexagonal (Alistair Cockburn): la aplicación se comunica con el exterior mediante puertos, y los adaptadores son intercambiables (por ejemplo, simulador vs exchange real) — [alistair.cockburn.us/hexagonal-architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- NautilusTrader aplica este mismo patrón: la arquitectura está dirigida por eventos y es determinista, y el mismo código de estrategia corre en backtest y en live (paridad research/live) — [gittrend.io: nautilus_trader](https://gittrend.io/repo/nautechsystems/nautilus_trader)

### Inferences
- **Módulos (paquetes Python) recomendados**, con dependencias solo hacia el dominio:
  1. `domain/`: entidades y value objects (Instrument, Order, Fill, Position, Signal, TargetPortfolio) y eventos de dominio. Sin I/O.
  2. `strategies/`: carry de funding, trend, señales ML y sentimiento. Cada una implementa el puerto `Strategy` (ver abajo) y emite `Signal`/`TargetWeight`.
  3. `portfolio_risk/`: asignación entre estrategias, límites (exposición, drawdown, kill-switch) y sizing.
  4. `execution/`: OMS y máquina de estados de órdenes. Depende del puerto `ExchangeGateway`.
  5. `adapters/`: Binance (CCXT o Nautilus), simulador o paper, almacenamiento (Parquet/DuckDB/Postgres) y notificaciones (Telegram).
  6. `data_platform/`: ingesta, medallion y features (pipelines de Dagster).
  7. `research/`: notebooks, backtests y registro de experimentos.
  8. `app/` o `api/`: dashboard y lectura (lado "query").
  9. `ops/`: config, logging, métricas y secretos.
- **SOLID aplicado**:
  - SRP: separar el cálculo de la señal de la ejecución.
  - OCP: añadir una estrategia nueva sin tocar el OMS.
  - LSP: `PaperGateway` y `BinanceGateway` son intercambiables.
  - ISP: puertos pequeños (`MarketDataFeed`, `OrderGateway`, `AccountState`).
  - DIP: el núcleo depende de abstracciones (`typing.Protocol`), no de CCXT.
- Hacer cumplir los límites con **import-linter** (contratos de capas), el equivalente Python de Packwerk. Es inferencia propia; no se verificó la herramienta en esta sesión.
- **Event sourcing ligero**: un journal append-only de eventos (`order_submitted`, `fill`, `signal`, `risk_breach`) en Postgres o en Parquet particionado por día. Es suficiente para la auditoría y para el replay. CQRS solo para las vistas de lectura (dashboard/BI), alimentadas desde el journal.

### Gaps
- No se encontró un caso publicado de un equipo de trading cripto pequeño que documente su monolito modular. La recomendación se extrapola de Fowler, Shopify y LMAX.

## 2. Motor de trading: adoptar (NautilusTrader / Freqtrade / Hummingbot / LEAN / Jesse) vs construir sobre CCXT; librerías de backtesting

### Takeaway
La recomendación es **adoptar NautilusTrader** (LGPL-3.0, muy activo, adaptador Binance nativo en Rust y paridad backtest/live) como motor de ejecución y backtest event-driven, y usar **vectorbt (OSS) / Polars** para la investigación vectorizada rápida. La alternativa "build" sobre **CCXT (MIT, websockets Pro ahora gratis)** solo tiene sentido si el objetivo académico es mostrar diseño propio. En ese caso conviene un núcleo propio mínimo con adaptador CCXT, sin intentar replicar un motor completo. Ojo: Nautilus está en plena **transición a v2 (RC)**, lo que eleva el riesgo de cambios rotos.

### Cited Findings
- **NautilusTrader**:
  - v1.231.0 (2-ago-2026) es la última 1.x sobre el núcleo Cython legado; el runtime v2 en Rust/PyO3 está en "release candidate". v2.0.0rc3 salió el 20-ago-2026 y v2.0.0rc4 el 2-sep-2026 — [newreleases v1.231.0](https://newreleases.io/project/github/nautechsystems/nautilus_trader/release/v1.231.0); [v2.0.0rc4](https://newreleases.io/project/github/nautechsystems/nautilus_trader/release/v2.0.0rc4)
  - El adaptador Binance es un crate Rust (`nautilus-binance`) expuesto a Python. Cubre Spot (incl. Binance US), futuros USDT-M (perpetuos y delivery) y COIN-M, con claves Ed25519 (recomendada) y HMAC — [docs Nautilus Binance](https://nautilustrader.io/docs/latest/integrations/binance)
  - Licencia LGPL-3.0-or-later (PyPI). Entre ~22.5k y ~25.9k estrellas según la fuente: Star History, a 15-jun-2026, da ~23.5k — [Star History](https://www.star-history.com/nautechsystems/nautilus_trader); [gittrend](https://gittrend.io/repo/nautechsystems/nautilus_trader); [OpenSourceAlternatives](https://www.opensourcealternatives.to/item/nautilus-trader)
  - Integraciones adicionales (Bybit, OKX y otras) listadas en la página de integraciones — [nautilustrader.io/docs/latest/integrations](https://nautilustrader.io/docs/latest/integrations)
- **CCXT**: la documentación oficial actual dice que CCXT Pro (WebSockets) viene incluido gratis en el paquete `ccxt` bajo licencia MIT, sin tier de pago. Una página de terceros (Shakudo) aún lo llama "versión de pago", lo que probablemente está desactualizado — [CCXT Pro manual](https://docs.ccxt.com/docs/pro-manual); [CCXT vs Cryptofeed](https://docs.ccxt.com/docs/comparisons/ccxt-vs-cryptofeed); en contra: [Shakudo](https://docs.shakudo.io/shakudo-platform-features/Web3%20API/ccxt)
- **Hummingbot**: Apache-2.0 (repo oficial) — [github.com/hummingbot/hummingbot](https://github.com/hummingbot/hummingbot)
- **Freqtrade (GPL-3.0) y Jesse (MIT)**: sus licencias solo las reporta un artículo de terceros, no verificadas contra el LICENSE. Las cifras de estrellas en esas fuentes son inconsistentes — [CoinCodeCap](https://coincodecap.com/open-source-trading-bots-on-github)
- **vectorbt (OSS)**: Apache-2.0 **con Commons Clause**, que prohíbe vender productos o servicios que sean esencialmente el software. vectorbt PRO es propietario y de pago — [vectorbt.dev/terms](https://vectorbt.dev/terms); [vectorbt.pro licencia](https://vectorbt.pro/terms/software-license/)
- **backtesting.py**: AGPL-3.0 (agpl3Only según Nix), ~8.5k estrellas — [depscope](https://depscope.dev/pkg/pypi/backtesting); [ossinsight](https://ossinsight.io/analyze/kernc/backtesting.py)
- **LEAN (QuantConnect)**: licencia Apache-2.0, motor en C# con API Python. No se re-verificó en esta sesión; ver el [repo QuantConnect/Lean](https://github.com/QuantConnect/Lean).

### Tabla comparativa (licencias verificadas donde se indica)
| Opción | Licencia | Lenguaje núcleo | Binance | Backtest = live | Encaje 1-2 devs |
|---|---|---|---|---|---|
| NautilusTrader | LGPL-3.0 (verificado) | Rust + Python | Spot, USDT-M, COIN-M nativo | Sí (event-driven) | Alto, con curva de aprendizaje alta y v2 en RC |
| Freqtrade | GPL-3.0 (fuente secundaria) | Python | Sí (vía CCXT) | Parcial | Bueno para bots simples; poco flexible para multiestrategia/portfolio |
| Hummingbot | Apache-2.0 (verificado) | Python/Cython | Sí | Orientado a market making | Bajo para trend, carry o ML |
| LEAN | Apache-2.0 (no re-verificado) | C# | Sí (Binance vía LEAN) | Sí | Medio: stack .NET y Docker pesado |
| Jesse | MIT (fuente secundaria) | Python | Sí | Sí | Medio; comunidad pequeña |
| CCXT + núcleo propio | MIT (verificado; Pro gratis) | Python | ~100 exchanges | Lo que construyas | Máximo control y máximo esfuerzo |
| vectorbt OSS | Apache-2.0 + Commons Clause | Python/Numba | n/a (research) | No | Excelente para barridos de parámetros |
| backtesting.py | AGPL-3.0 | Python | n/a | No | Simple, pero la AGPL contamina si se distribuye o sirve |

### Inferences
- **Recomendación híbrida**:
  - Research vectorizado con Polars/DuckDB y vectorbt OSS. Para un capstone no comercial la Commons Clause no afecta, pero conviene documentarlo.
  - Validación final y ejecución paper/live en NautilusTrader (sandbox/testnet de Binance).
  - Las estrategias se escriben contra puertos propios para poder portarlas.
- Fijar la versión de Nautilus. Elegir 1.231 (estable, pero legado) o v2 RC según la fecha de inicio. Si v2 llega a GA a finales de 2026, conviene empezar directamente en v2 para no migrar.
- Para demostrar ingeniería de software, construir el núcleo de dominio, el riesgo y el journal propios aunque la ejecución sea Nautilus o CCXT.

### Gaps
- No se verificó si NautilusTrader v2.0 ya alcanzó GA después del 2-sep-2026.
- No se verificaron los LICENSE de Freqtrade, Jesse ni LEAN directamente, ni la actividad de commits de 2026 de Freqtrade, Jesse y Hummingbot.

## 3. Almacenamiento: lakehouse Parquet + DuckDB (Delta/Iceberg/DuckLake), medallion, PostgreSQL/TimescaleDB, QuestDB, ClickHouse; point-in-time

### Takeaway
En la etapa 0, un **lakehouse local con Parquet + DuckDB y DuckLake 1.0** (catálogo en SQLite o Postgres) en capas bronze/silver/gold cuesta 0 USD y casi no ocupa RAM en reposo. **PostgreSQL** sirve para el estado transaccional (órdenes, journal, registro de experimentos). **TimescaleDB** solo hace falta si se quieren hypertables o continuous aggregates; su edición Community (TSL) es gratuita para uso propio, no para venderla como DBaaS. **ClickHouse o QuestDB** no se justifican con la RAM disponible.

### Cited Findings
- **DuckLake 1.0**: anunciado el 13-abr-2026. La especificación y la extensión de DuckDB se declaran listas para producción, con compatibilidad hacia atrás garantizada. Los metadatos van en una base SQL (no en ficheros en object storage). DuckDB 1.5.2 añadió soporte para el formato v1.0. La FAQ esperaba la v1.1 en septiembre de 2026 (no confirmado) — [DuckDB blog: DuckLake 1.0](https://duckdb.org/2026/04/13/ducklake-10.html); [DuckLake FAQ](https://ducklake.select/faq)
- **TimescaleDB**: existe una edición Apache-2 y una Community bajo TSL. Funciones recientes como Hypercore/columnstore (desde 2.18) y continuous aggregates solo están en Community. La TSL prohíbe ofrecerla como DBaaS, pero permite usar todas las funciones gratis en uso propio. `SHOW timescaledb.license;` indica la edición activa — [Tiger Data: editions](https://www.tigerdata.com/docs/about/latest/timescaledb-editions); [Tiger Data licenses](https://www.tigerdata.com/legal/licenses)
- **Medallion**: bronze = crudo, silver = limpio y conformado, gold = agregados de negocio o features. Patrón popularizado por Databricks — [Databricks: medallion architecture](https://www.databricks.com/glossary/medallion-architecture)

### Tabla comparativa
| Motor | Licencia | Rol | RAM en reposo (inferencia) | Comentario |
|---|---|---|---|---|
| Parquet + DuckDB (+DuckLake) | MIT | Lakehouse analítico | ~0 (in-process); consultas acotadas con `memory_limit` | Ideal para 5.7 GB; con time travel y snapshots |
| Delta Lake / Iceberg | Apache-2.0 | Formatos de tabla abiertos | n/a | Más ecosistema (Spark/Trino), pero más pesados de operar solo |
| PostgreSQL 16/17 | PostgreSQL | OLTP: órdenes, journal, MLflow, Dagster | ~100–300 MB con config pequeña | Imprescindible de todos modos |
| TimescaleDB Community | TSL | Series temporales en Postgres | Igual que Postgres | Gratis salvo DBaaS |
| QuestDB | Apache-2.0 | TSDB de ingesta rápida | JVM, ~0.5–1 GB+ | Sobra para barras de 1 minuto |
| ClickHouse | Apache-2.0 | OLAP columnar | ~1 GB+ recomendado | Excesivo en etapa 0-1 |

### Inferences
- **Point-in-time (PIT)**: guardar en cada registro `event_time` (cuándo ocurrió) y `ingest_time`/`knowledge_time` (cuándo se supo). Las features gold se construyen con joins "as-of" (`ASOF JOIN` de DuckDB, `join_asof` de Polars) sobre `knowledge_time` para evitar look-ahead. Los snapshots de DuckLake dan reproducibilidad del dataset por versión.
- Particionar el bronze por `exchange/símbolo/fecha` y usar Hive partitioning.
- Volumen estimado: 1 minuto × 200 símbolos × 5 años ≈ 525 millones de filas. En Parquet con ZSTD son unas decenas de GB, manejables con DuckDB en el portátil.

### Gaps
- No se obtuvieron mediciones publicadas de RAM de QuestDB ni de ClickHouse en configuración mínima; las cifras de la tabla son estimaciones propias.
- No se confirmó el lanzamiento de DuckLake v1.1.

## 4. Mensajería/streaming: Kafka (KRaft) vs Redpanda vs NATS JetStream vs Redis Streams

### Takeaway
En la etapa 1 **no hace falta un broker externo**: el monolito usa un bus en proceso (asyncio y, si se adopta Nautilus, su MessageBus) más el journal en disco o Postgres. Si después se quiere desacoplar procesos (ingesta y trading en contenedores separados), **NATS JetStream** o **Redis Streams** son lo más ligero. Kafka y Redpanda quedan como opciones de portfolio o demo, no de necesidad.

### Cited Findings
- NATS es un solo binario de ~10–15 MB, y JetStream (persistencia) va integrado en el mismo servidor, sin sistema de coordinación aparte — [AutoMQ: Kafka vs NATS](https://www.automq.com/blog/apache-kafka-vs-nats-differences-amp-comparison); [PkgPulse 2026](https://www.pkgpulse.com/guides/redpanda-vs-nats-vs-apache-kafka-event-streaming-2026)
- Kafka 4.x en modo KRaft sigue en la JVM. En un benchmark de 2026, Kafka 4.2.0 corrió con un heap por defecto de 2 GB en una VM de 4 vCPU y 8 GB — [ComputingForGeeks: Kafka vs Redpanda](https://computingforgeeks.com/kafka-vs-redpanda-benchmarks/)
- Redpanda: C++ sin JVM, binario único y diseño thread-per-core. Las fuentes no dan una cifra clara de memoria — [Conduktor: Redpanda vs Kafka](https://conduktor.io/glossary/redpanda-vs-kafka)
- Ninguna fuente ofrece una comparación de memoria controlada entre las tres opciones — [RisingWave](https://risingwave.com/blog/nats-kafka-or-redpanda-which-real-time-data-solution-is-best/)

### Tabla
| Broker | Licencia | RAM aprox. | Coste operativo | ¿Etapa? |
|---|---|---|---|---|
| Ninguno (bus en proceso + journal) | n/a | 0 | Nulo | 0 y 1 |
| Redis Streams | Ver nota (Redis 8 añadió AGPL; Valkey es BSD) | ~50–100 MB | Bajo; además sirve de cache | 1–2 |
| NATS JetStream | Apache-2.0 | ~20–100 MB (inferencia) | Muy bajo | 2 |
| Redpanda | BSL / Community | ~1 GB+ recomendado (inferencia) | Medio | Demo opcional en 3 |
| Kafka KRaft | Apache-2.0 | ≥1–2 GB de heap | Alto | No recomendado |

### Inferences
- A frecuencias de minuto a diario el throughput es trivial (de decenas a miles de mensajes por minuto), así que un broker solo aporta desacoplamiento y valor de demo.
- Con 5.7 GB de RAM en WSL, Kafka (2 GB de heap) es inviable junto con el resto del stack.

### Gaps
- No se verificó en esta sesión la licencia actual de Redis 8 ni de Valkey; la nota de la tabla sale de conocimiento previo y conviene confirmarla.
- No hay benchmarks de RAM publicados y comparables.

## 5. Orquestación: Dagster vs Prefect vs Airflow

### Takeaway
**Dagster** encaja mejor por su modelo de **software-defined assets**: bronze, silver, gold, features y modelos son assets con lineage, particiones por fecha y checks, lo que encaja directamente con medallion y PIT y luce en el capstone. **Prefect** es más ligero y simple. **Airflow** es el más pesado (scheduler, webserver, workers y metadata DB) y se descarta para 5.7 GB.

### Cited Findings
- Un usuario que migró de Airflow a Dagster reporta que Dagster usaba claramente menos recursos y que la memoria de Airflow era un problema. Es una anécdota sin medición — [Dagster community](https://discuss.dagster.io/t/12355921/hey-all-i-ll-soon-have-to-do-an-objective-comparison-between)
- Airflow separa scheduler, webserver y workers. Dagster separa el daemon (schedules/sensors) del código de usuario. Prefect puede correr flows como proceso local — [RisingWave: Airflow vs Dagster vs Prefect](https://risingwave.com/blog/airflow-vs-dagster-vs-prefect-a-detailed-comparison/); [DZone](https://dzone.com/articles/airflow-vs-dagster-vs-prefect-which-scheduler-fits)
- Modelo de assets de Dagster (software-defined assets, particiones, asset checks) — [docs.dagster.io: Assets](https://docs.dagster.io/guides/build/assets)

### Inferences
- En el portátil, `dagster dev` (webserver + daemon) con SQLite o Postgres probablemente ronda los 300–600 MB. Es una estimación propia; conviene medirla con `ps`/`docker stats`.
- El trading live **no** debe orquestarse con Dagster: es un proceso de larga duración (systemd o contenedor con `restart: always`). Dagster cubre ingesta batch, features, reentrenamiento y reportes.

### Gaps
- No existen benchmarks publicados de memoria de los tres en una VM pequeña.

## 6. MLOps: MLflow, DVC, Optuna, Evidently, feature store; registro de trials para el Deflated Sharpe

### Takeaway
**MLflow** (tracking y model registry, con backend en Postgres y artefactos en disco) más **Optuna** (con storage en el mismo Postgres) cubren experimentos e hiperparámetros, y permiten **contar todos los trials** (N) que exige el Deflated Sharpe Ratio. **Evidently** sirve para drift de features y predicciones. **No hace falta un feature store** (Feast) en esta escala: las tablas gold PIT en DuckLake hacen ese papel. **DVC** es opcional, porque DuckLake ya versiona datos con snapshots.

### Cited Findings
- Deflated Sharpe Ratio (Bailey & López de Prado, 2014): corrige el Sharpe por el número de pruebas independientes, la no normalidad y la longitud de la muestra. Exige registrar cuántas configuraciones se probaron — [SSRN 2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- Optuna persiste los estudios y todos los trials en un storage RDB (SQLite/PostgreSQL/MySQL) — [Optuna docs: RDB storage](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/001_rdb.html)
- MLflow Tracking admite un backend store SQL (PostgreSQL) y un artifact store separado; Model Registry requiere backend de base de datos — [MLflow docs: backend stores](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/)

### Inferences
- Convención: cada backtest o configuración evaluada, también los descartados, se registra como run de MLflow con tag `strategy_family`. N para el DSR = número de runs por familia, o mejor, clusters de trials correlacionados (López de Prado).
- Evidently como job semanal en Dagster que genera un reporte HTML de drift. Telegram alerta si se supera un umbral.
- La GPU 940MX (Maxwell, 4 GB) es poco útil para el ML moderno: LightGBM y XGBoost en CPU bastan para señales tabulares.

### Gaps
- No se verificaron en esta sesión las versiones de 2026 ni el consumo de RAM del servidor MLflow (estimación propia: 200–400 MB).

## 7. Entorno Python y calidad: uv vs pixi vs micromamba; R; ruff, mypy/pyright, pytest, hypothesis, pandera vs Great Expectations, pre-commit, commitizen, SemVer

### Takeaway
**uv** es el gestor principal. TA-Lib ya publica **wheels binarios con la librería C incluida desde la 0.6.5**, así que conda deja de ser necesario por TA-Lib. **pixi** solo compensa si se integra **R** (rugarch, PerformanceAnalytics) en el mismo entorno reproducible. Una alternativa: R en su propio contenedor `rocker/r-ver` con `renv`. Para validar datos, **pandera** es más ligero que Great Expectations.

### Cited Findings
- uv solo lee PyPI (más Git/URL/path). Pixi lee conda-forge y PyPI, genera `pixi.lock` multiplataforma que cubre ambos y encaja en proyectos mixtos Python+R o con librerías nativas — [pydevtools: pixi vs uv](https://pydevtools.com/handbook/explanation/when-should-i-choose-pixi-over-uv/); [uv vs pixi vs conda](https://pydevtools.com/handbook/explanation/uv-vs-pixi-vs-conda-for-scientific-python/)
- TA-Lib Python: desde la 0.6.5 hay wheels que incluyen la librería C para Linux (x86_64, arm64), macOS y Windows, para Python 3.9–3.13 (y 3.14). La rama 0.6.x soporta numpy 2 — [PyPI ta-lib](https://pypi.org/project/ta-lib); [GitHub TA-Lib/ta-lib-python](https://github.com/TA-Lib/ta-lib-python)

### Tabla de herramientas de calidad (recomendación)
| Área | Elección | Alternativa | Motivo |
|---|---|---|---|
| Lint y formato | ruff | black + flake8 | Una sola herramienta muy rápida |
| Tipos | mypy (strict en `domain/`) o pyright | — | Puertos con `Protocol` tipados |
| Tests | pytest + hypothesis | — | Propiedades: PnL, invariantes de posición, redondeo de tick/lot |
| Validación de datos | pandera (soporta Polars) | Great Expectations | GX es pesado; pandera va inline en los assets de Dagster |
| Hooks | pre-commit | — | ruff, mypy, detect-secrets/gitleaks |
| Commits y versiones | Conventional Commits + commitizen (o python-semantic-release) | — | Changelog y SemVer automáticos |

### Inferences
- R: usarlo para validación econométrica (GARCH con rugarch, tablas de PerformanceAnalytics) como "segunda opinión" vía scripts Rscript dentro de un asset de Dagster. Evitar rpy2 en el camino crítico.
- Si se usa R dentro del mismo entorno, pixi con conda-forge (r-base, r-rugarch). Si no, uv + Docker rocker.

### Gaps
- No se verificó la disponibilidad actual en conda-forge de r-rugarch ni de r-performanceanalytics.
- Las herramientas de calidad no se re-verificaron una a una (versiones de 2026); son estándar de facto según conocimiento previo.

## 8. CI/CD en GitHub Actions, protección de ramas, Dependabot, CodeQL, secretos

### Takeaway
Conviene un **repositorio público** (o con el núcleo público y la config privada): en el plan Free, **rulesets y protección de ramas solo aplican a repos públicos**, y los minutos de Actions son ilimitados en runners estándar para repos públicos. Las claves de API nunca van al repo: GitHub Secrets para CI y **sops+age** (o `.env` fuera de git) para el servidor.

### Cited Findings
- Rulesets disponibles en repos públicos con GitHub Free y Free for organizations; en repos privados requieren Pro, Team o Enterprise — [GitHub Docs: available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- Existe una petición comunitaria abierta para hacer gratis la protección básica en repos privados, sin cambio confirmado — [GitHub community #174419](https://github.com/orgs/community/discussions/174419)
- Actions es gratuito en runners estándar para repos públicos; los privados tienen cuota de minutos — [GitHub Docs: billing for Actions](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)
- CodeQL (code scanning) es gratuito para repos públicos — [GitHub Docs: code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning)

### Inferences
- Pipeline:
  - PR: ruff, mypy, pytest (con hypothesis) y un backtest de humo con datos fixture.
  - Main: build de la imagen Docker (multi-arch amd64/arm64 si se va a Oracle ARM o Hetzner CAX), push a GHCR y deploy por SSH o `docker compose pull`.
  - Además: Dependabot (pip/uv, docker, actions), CodeQL semanal y gitleaks en pre-commit y CI.
- En Binance, claves API **sin permiso de retiro** y con restricción de IP.
- Si el repo debe ser privado, se puede usar GitHub Pro gratis vía Student Pack (inferencia; no verificado en esta sesión).

### Gaps
- No se re-verificaron en esta sesión los precios y cuotas de Actions de 2026 para repos privados.

## 9. Observabilidad: Prometheus + Grafana, Loki, logging estructurado, alertas a Telegram

### Takeaway
El stack es **structlog con logs JSON**, **Prometheus** (métricas de PnL, latencia de órdenes, lag de datos y heartbeats) y **Grafana**, con Alertmanager o alertas de Grafana enviadas a Telegram. **Loki** solo se añade en la etapa 2 por RAM. En la etapa 0 basta con logs JSON a fichero y un bot de Telegram directo desde la app.

### Cited Findings
- Grafana Alerting incluye un punto de contacto nativo para Telegram — [Grafana docs: Telegram contact point](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-telegram/)
- Alertmanager admite `telegram_configs` como receptor nativo — [Prometheus Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)

### Inferences
- RAM estimada (propia): Prometheus ~100–200 MB con pocas series, Grafana ~100–150 MB, Loki monolítico ~150–300 MB y Promtail/Alloy ~50 MB.
- Métricas clave: `strategy_pnl`, `position_notional`, `order_reject_total`, `ws_reconnect_total`, `data_staleness_seconds`, `funding_rate_next` y `kill_switch_state`.

### Gaps
- No se midió la RAM real de cada componente; las cifras son orientativas.

## 10. Despliegue: Oracle Always Free, Hetzner 2026, Student Pack, latencia a Binance

### Takeaway
- **Etapa 0**: portátil WSL2 más **Oracle Cloud Always Free ARM** (4 OCPU y 24 GB, si hay capacidad) para paper trading 24/7. Riesgo: reclamación de instancias inactivas y falta de capacidad.
- **Etapa 1 (~20 USD)**: **Hetzner CAX/CX**. Ojo: Hetzner subió precios dos veces en 2026 (abril y junio). La alternativa es una VPS en Tokio si la latencia importa.
- La latencia a Binance es secundaria para horizontes de minuto a diario.

### Cited Findings
- **Oracle Always Free**:
  - 3,000 OCPU-hora y 18,000 GB-hora al mes en VM.Standard.A1.Flex, equivalentes a 4 OCPU y 24 GB — [Oracle Docs: Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
  - Una guía de 2026 afirma un recorte a 2 OCPU/12 GB, no confirmado por Oracle y en conflicto con la página oficial — [braindetox 2026](https://braindetox.kr/en/posts/oracle_always_free_tier_reduced_2026.html); [space-node](https://space-node.net/blog/oracle-cloud-free-vps-guide-2026)
  - Reclamación por inactividad: en 7 días, CPU p95 <15 %, red <15 % y memoria <15 % (A1). El dato viene de un foro que cita la documentación de Oracle — [Lemmy (cita docs Oracle)](https://lemmy.dbzer0.com/post/94766/203513)
  - Hay errores "Out of Capacity" en algunas regiones — [cloudtoolstack](https://cloudtoolstack.com/blog/oracle-cloud-free-tier-guide)
- **Hetzner 2026**:
  - Subida del 1-abr-2026 de ~30–37 %, también para clientes existentes. CX22 y CAX11 pasaron de 3.29 € a 4.49 €, y el plan más barato pasó a ser CX23 a 3.99 €.
  - Segunda subida el 15-jun-2026, solo para pedidos nuevos o rescalados: CX23 de 3.99 € a 5.49 € y CAX11 de 4.49 € a 5.99 € (DE/FI). CPX y CCX subieron hasta +176 %. Las cifras vienen de fuentes secundarias que discrepan; hay que verificarlas en la página oficial — [agentdeals](https://agentdeals.dev/hetzner-pricing-2026); [wz-it](https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/); [Northflank](https://northflank.com/blog/hetzner-cloud-server-price-increases); [Hetzner docs What's New](https://docs.hetzner.cloud/whats-new)
- **GitHub Student Pack**: 100 USD de Azure sin tarjeta (18+). El crédito de 200 USD de DigitalOcean habría terminado el 31-jul-2026 según una fuente de sept-2026, sin confirmar en la página oficial — [education.github.com/pack](https://education.github.com/pack); [Capital & Compute](https://capitalandcompute.net/blog/github-student-developer-pack-2026/)
- **Latencia a Binance**:
  - Que Binance esté en AWS ap-northeast-1 (Tokio) lo afirman vendedores de VPS. Uno reporta 1–2 ms desde Japón — [EDIS](https://edisglobal.com/blog/crypto-trading-vps)
  - Un test independiente encontró Osaka más rápido, con Seúl y Tokio muy cerca — [Substack: análisis de Binance por región](https://viktoriatsybko.substack.com/p/an-analysis-of-binance-exchange-across)
  - Una caída de AWS en apne1 afectó a Binance (evidencia de alojamiento en Tokio en ese momento) — [DCD](https://datacenterdynamics.com/en/news/network-issue-at-aws-data-center-brings-down-crypto-exchanges)
  - Otra IP de api.binance.com resuelve a us-east-1 — [Valebyte](https://www.valebyte.com/es/blog/vps-for-binance-setting-up-a-trading-bot-with-minimal-latency/)

### Tabla de opciones
| Opción | Coste/mes | Recursos | Pros | Contras |
|---|---|---|---|---|
| Portátil WSL2 | 0 | 8 hilos, 5.7 GB | Desarrollo y research | No es 24/7 |
| Oracle Always Free A1 | 0 | 4 OCPU / 24 GB ARM (documentado) | Mucha RAM gratis | Reclamación por inactividad, capacidad, riesgo de cambios; imágenes deben ser arm64 |
| Hetzner CAX11 (ARM) | ~6 € (post-junio, nuevo pedido) | 2 vCPU / 4 GB | Fiable, barato | Europa: ~200+ ms a Tokio (inferencia) |
| Hetzner CAX21/CX33 | ~10–15 € (estimado) | 4 vCPU / 8 GB | Cabe el stack completo | Igual |
| VPS Tokio (Vultr, AWS Lightsail, etc.) | ~5–20 USD | 1–2 GB | Latencia baja a Binance | Menos RAM por dólar |
| Azure for Students | 100 USD de crédito | Variable | Gratis un tiempo | Crédito finito |

### Inferences
- Con horizontes de minuto a diario, 100–250 ms de latencia son irrelevantes frente al slippage y las comisiones. No conviene pagar por Tokio hasta que la ejecución lo requiera.
- Para que Oracle no reclame la instancia, el proceso live, Dagster y Prometheus generan carga real. No conviene depender de "cargas falsas".

### Gaps
- No se verificó la página oficial de ajuste de precios de Hetzner ni el precio exacto de CAX21 en oct-2026.
- No se midió la latencia real desde cada proveedor.

## 11. BI/visualización: Power BI vs Superset vs Metabase vs Grafana vs Streamlit/Dash

### Takeaway
Cada herramienta cumple un papel: **Power BI Desktop** (gratis, obligatorio por el curso) para el informe analítico de rendimiento sobre las tablas gold exportadas a Parquet/CSV o leídas desde Postgres; **Grafana** para la operación en tiempo real; y **Streamlit** como app demo interactiva (explorador de backtests y estado de estrategias). **Superset y Metabase son redundantes** y pesados en RAM para este contexto.

### Cited Findings
- Power BI Desktop es gratuito y se conecta a PostgreSQL, Parquet y CSV. Publicar o compartir en el servicio requiere licencia Pro o Fabric (Windows) — [Microsoft Learn: Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-what-is-desktop)
- Streamlit es open source (Apache-2.0) y despliega gratis apps públicas en Streamlit Community Cloud — [streamlit.io/cloud](https://streamlit.io/cloud)

### Inferences
- Power BI Desktop corre en Windows y no en WSL; se conecta al Postgres de WSL vía localhost o lee Parquet del filesystem compartido.
- RAM estimada (propia): Streamlit ~150–300 MB, Superset ~1 GB+ (con Redis y workers) y Metabase (JVM) ~1 GB.

### Gaps
- No se verificaron en esta sesión los requisitos de RAM oficiales de Superset ni de Metabase.

## 12. Stack recomendado por etapa y presupuesto de RAM

### Takeaway
Hay tres etapas incrementales con el mismo código y el mismo `docker compose` por perfiles:
- **0 USD**: portátil más Oracle Free, sin broker, con DuckDB/DuckLake y Postgres.
- **~20 USD**: VPS Hetzner ARM o x86 de 4–8 GB, con Grafana, Prometheus y MLflow.
- **~100 USD**: separar research y live en dos nodos, con Loki, NATS y backups offsite.

### Cited Findings
- Base de precios y recursos: ver las secciones 3, 4, 5 y 10 — [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm); [Hetzner 2026 (secundaria)](https://agentdeals.dev/hetzner-pricing-2026); [DuckLake 1.0](https://duckdb.org/2026/04/13/ducklake-10.html)

### Inferences
**Etapa 0, 0 USD/mes (portátil WSL2 5.7 GB más Oracle A1 opcional)**

| Componente | Elección | RAM estimada |
|---|---|---|
| Lenguaje y entorno | Python 3.12 + uv (pixi si se usa R) | — |
| Motor | NautilusTrader (backtest + paper en testnet) o núcleo propio + CCXT | 300–800 MB |
| Datos | Parquet + DuckDB + DuckLake (catálogo en Postgres) | 0 en reposo; consultas con `memory_limit=2GB` |
| OLTP, journal y metadatos | PostgreSQL (contenedor) | 150–300 MB |
| Orquestación | Dagster (`dagster dev`) | 300–600 MB |
| ML | MLflow (local) + Optuna (storage Postgres) + LightGBM | 200–400 MB (servidor MLflow) |
| Observabilidad | structlog JSON + bot de Telegram | ~0 |
| BI | Power BI Desktop (Windows) + Streamlit | 150–300 MB |
| CI/CD | GitHub Actions, repo público, Dependabot, CodeQL | — |
| **Total WSL** | | **~1.5–2.5 GB más la carga de research** (cabe en 5.7 GB) |

Se recomienda `.wslconfig` con `memory=5.7GB` y swap de 4–8 GB, y no levantar todo a la vez: perfiles de compose `research`, `pipeline` y `live`.

**Etapa 1, ~20 USD/mes (Hetzner CAX21/CX33, ~8 GB, o Oracle A1 si sigue disponible, más backups baratos)**

| Componente | Cambio |
|---|---|
| Servidor 24/7 | Proceso live (paper y luego capital pequeño) + Postgres + Dagster + MLflow |
| Observabilidad | + Prometheus + Grafana (+ alertas a Telegram) |
| Backups | `pg_dump` + Parquet a object storage (Hetzner Storage Box / Backblaze B2) |
| Secretos | sops+age en el repo de infra; claves de Binance sin retiro y con whitelist de IP |
| **RAM servidor** | Live 0.5–1 GB + Postgres 0.3 GB + Dagster 0.5 GB + MLflow 0.3 GB + Prometheus/Grafana 0.3 GB ≈ **2–2.5 GB** (holgado en 8 GB) |

**Etapa 2, ~100 USD/mes**
- Dos nodos. **Nodo live** pequeño, cerca de Binance (Tokio/Osaka), con solo el motor, el journal y los métricos. **Nodo de research/datos** en Hetzner de 16–32 GB con Dagster, DuckDB, MLflow, Grafana, Loki y Evidently.
- **NATS JetStream** entre nodos (señales y eventos), con el journal replicado.
- Opcional: TimescaleDB (Community) para continuous aggregates de métricas de trading. GPU en la nube puntual (spot o crédito Azure) solo si los modelos de sentimiento lo requieren.
- RAM total estimada: nodo live ~1.5 GB y nodo de research ~6–10 GB en uso típico.

### Gaps
- Los presupuestos de RAM son estimaciones propias sin benchmark. Hay que validarlos con `docker stats` en la etapa 0.
- Los precios exactos de Hetzner (post-junio-2026) y de las VPS en Tokio no se verificaron en fuentes oficiales.
