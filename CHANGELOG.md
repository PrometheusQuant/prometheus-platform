## v0.3.1 (2026-11-24)

### Fix

- **test**: la prueba del monitor de drift no depende de la fecha del día PQ-86 (#129)

## v0.3.0 (2026-11-23)

### Feat

- **dashboard**: rediseño de UX: portada «¿cómo va?», tema propio, cifras en español y lenguaje simple PQ-124 (#125)
- **observabilidad**: logs en Loki con Alloy, SLO de heartbeat al 99 % y verificación externa PQ-97 (#124)
- **observabilidad**: métricas del runner con Prometheus y tablero de Grafana PQ-71 (#121)
- **research**: pq research trend-holdout, apertura única del holdout de tendencia PQ-68 (#122)
- **research**: evaluación de la Estrategia 2 (tendencia), ejecución única (PQ-68) (#119)
- **monitor**: monitoreo de drift de datos, modelo y desempeño sin ajustes automáticos PQ-86 (#117)
- **paper**: costes frente al modelo, paridad con el backtest e incidentes en el informe semanal PQ-85 (#115)
- **paper**: informe semanal del paper trading en PDF y por Telegram PQ-85 (#114)
- **paper**: alerta y pausa ante liquidaciones atrasadas, y runbooks de incidentes PQ-98 (#110)
- **compliance**: comisiones de Binance con clave de solo lectura y guía de pasos del titular (PQ-17) (#109)
- **paper**: asistente /pregunta en el bot de Telegram, de solo lectura PQ-90 (#103)
- **paper**: precios por websocket con respaldo REST para el runner PQ-80 (#102)
- **data**: funding de Bybit y OKX en el mismo esquema bronze y silver PQ-79 (#100)
- **risk**: monitor de riesgo de contraparte del exchange con alerta y reducción PQ-96 (#99)
- **dashboard**: gráficos más legibles en la cartera y captura para el informe PQ-84 (#96)
- **report**: página pública de resultados para el jurado en GitHub Pages PQ-89 (#95)
- **dashboard**: pestaña de cartera multiestrategia con PnL, CVaR y bandas del backtest PQ-84 (#92)
- **paper**: respaldos cifrados de data/paper cada hora y simulacro de restauración PQ-73 (#90)
- **risk**: el runner respeta presupuestos y tiene kill-switch por estrategia PQ-83 (#89)
- **paper**: bot de Telegram con /estado, /pnl y /kill desde chats autorizados PQ-72 (#88)
- **risk**: presupuesto de capital entre estrategias con tope de CVaR y por exchange PQ-83 (#87)
- **dashboard**: modo feria con tipografía grande, autorefresco y recorrido guiado PQ-102 (#86)
- **research**: pq research trend: evaluación pre-registrada de la tendencia PQ-68 (#85)
- **execution**: ejecutor genérico de señales: cualquier Strategy opera en paper PQ-116 (#84)
- **deploy**: reintento automático del apply de A1 en Oracle hasta que haya capacidad PQ-56 (#80)
- **research**: motor de backtest de tendencia con volatility targeting PQ-67 (#73)
- **dashboard**: explicabilidad del clasificador del cap. 5 PQ-74 (#71)
- **paper**: monitoreo en vivo, pestaña del dashboard y alertas PQ-55 (#63)
- **strategies**: puerto Strategy con instantáneas point-in-time y prueba de contrato PQ-113 (#65)
- **research**: registro de ensayos compartido y versionado PQ-112 (#64)
- **paper**: runner de paper trading del carry H2 con bróker simulado PQ-54 (#62)
- **PQ-58**: simulador interactivo y predicción del funding de hoy (cap. 7.3) (#58)
- **PQ-53**: gestión de riesgo pre-trade y kill-switch probado (#57)
- **PQ-22**: orquestar el lakehouse con Dagster (assets, checks y schedules) (#56)
- **PQ-65**: ingesta incremental desde la API REST pública de Binance (#54)
- **PQ-49**: costes cotizados, VAN, TIR y capital de equilibrio (cap. 8.3-8.4) (#52)
- **PQ-48**: validación estadística del impacto de la optimización (cap. 7.4) (#50)
- **PQ-46**: capa gold con modelo en estrella para BI (cap. 7.1) (#49)

### Fix

- **compliance**: el descuento BNB es el multiplicador que se paga; verificación de PQ-17 registrada (#116)
- **ci**: fijar cosign-installer a v4.1.3, sin etiqueta mayor v4 PQ-81 (#108)
- **research**: el backtest del carry respeta la frontera del holdout y la latencia de 1 h PQ-66 (#91)
- **ops**: enmascarar secretos dentro de los textos libres de los logs PQ-118 (#82)
- **paper**: el vigilante no alerta «sin heartbeat» mientras el runner arranca PQ-55 (#70)
- **PQ-38**: conftest raíz sin importar el paquete (job e2e) (#47)
- **PQ-38**: hora local en las alertas y tests aislados del .env (#46)

## v0.2.0 (2026-11-06)

### Feat

- **PQ-40**: exportar sesiones de Claude Code a Markdown para NotebookLM (#33)
- **PQ-39**: informe ejecutivo reproducible con Quarto (make report) (#32)
- dashboard de investigación en Streamlit + Docker (PQ-34) (#31)
- **PQ-38**: alertas ERROR/CRITICAL a Telegram (patrón Observer) (#30)
- simulación de Markov y Monte Carlo del carry (cap. 6) PQ-33 (#28)
- **research**: modelo predictivo del funding con walk-forward y GridSearch PQ-32 (#25)
- motor de investigación del carry, validación anti-sobreajuste y evaluación PQ-23 (#24)
- capa silver tipada, validada y point-in-time PQ-21 (#20)
- ingesta bronze de velas y funding desde Binance Data Vision PQ-20 (#14)
- **ops**: configuración tipada por entorno y logging estructurado PQ-15 (#10)

## v0.1.0 (2026-10-16)
