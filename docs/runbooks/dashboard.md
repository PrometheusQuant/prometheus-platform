# Dashboard de investigación

Panel de **solo lectura** con los resultados: calidad de los datos, carry y gates, modelo del
funding y simulación. Decisión en [ADR-0009](../adr/0009-streamlit-y-docker-para-el-dashboard.md).

## Abrirlo

**En local:**

```bash
make dashboard          # http://localhost:8501
```

**Con Docker** (Docker Desktop abierto y con la integración WSL, ver KE-008):

```bash
docker compose up --build    # http://127.0.0.1:8501
docker compose down
```

## Modo feria (PQ-102)

Para la pantalla grande de la feria, abre **<http://localhost:8501/?modo=feria>**:

- **Tipografía grande**, pensada para leerse a 2 o 3 metros. Solo usa fuentes del sistema.
- **La página en vivo se actualiza sola** cada 60 s, al ritmo del runner, sin recargar el resto.
- **Recorrido guiado** en la barra lateral: 7 pasos, uno por sección del pitch (PQ-60). Cada paso
  dice qué página abrir (con un enlace), qué decir y qué señalar. Se avanza con «Siguiente».

| Paso | Sección del pitch | Pestaña |
|---|---|---|
| 1 | El problema | (el título del tablero) |
| 2 | Por qué fallan los minoristas | Datos y calidad (técnico) |
| 3 | Nuestra respuesta | ¿Funciona? Carry y gates |
| 4 | La evidencia | ¿Qué riesgo hay? Simulación |
| 5 | Demo en vivo | ¿Cómo va en vivo? Paper trading |
| 6 | Viabilidad | ¿Y si invierto? Simula tu inversión |
| 7 | Cierre | (vuelve a la página en vivo) |

Los textos se editan en `src/prometheus_platform/api/dashboard/tour.py` (`STEPS`). No llevan cifras:
las cifras las muestra el tablero desde los artefactos.

**Sin internet (plan B de PQ-63).** El tablero solo lee el lakehouse local, así que abre y navega con
la red cortada; lo comprueba una prueba que bloquea los sockets. Sin red, el runner no recibe precios
nuevos y la página en vivo muestra el último ciclo con su antigüedad. La página «¿Qué predice
hoy?» necesita los datos de hoy ingeridos antes de perder la conexión.

## Qué muestra

| Página | Pregunta que responde | Artefacto | Se genera con |
|---|---|---|---|
| ¿Qué pasó? | ¿Los datos son confiables? | `data/silver/_quality/*.json` | `uv run pq silver build --symbol <S>` |
| ¿Funciona? | ¿El carry pasa los gates? | `data/research/carry/H*/` | `uv run pq research carry --hypothesis H2 --figures <dir>` |
| ¿Qué predice? | ¿Se puede anticipar el funding? | `data/research/funding_model/summary.json` | `uv run pq research funding-model --figures <dir>` |
| ¿Qué riesgo hay? | ¿Qué puede salir mal? | `data/research/simulation/summary.json` | `uv run pq research simulate --figures <dir>` |
| ¿Y si invierto? | ¿Qué me pasaría con mi capital? | Silver de H2 (desarrollo): Monte Carlo del cap. 6 con tu capital, horizonte y riesgo de quiebra; θ solo pre-registrado | `uv run pq silver build --symbol <S>` |
| ¿Qué predice hoy? | ¿Habrá funding alto en la próxima liquidación? | Clasificador del cap. 5 entrenado con el desarrollo; predice solo con datos **posteriores** al holdout | `uv run pq ingest --source api ...` + `pq silver build` |
| ¿Cómo va en vivo? | ¿Cómo va el paper trading ahora? | `data/paper/diario.jsonl` y `heartbeat.json`: equity frente a lo esperado según el backtest, funding, costes, posiciones, órdenes, decisiones, heartbeat y kill-switch | `uv run pq paper run` ([runbook](paper-trading.md)) |
| ¿Cómo se reparte? | ¿Cómo se reparte el capital y el riesgo entre estrategias? | Presupuesto recomendado frente al paper, capital y PnL por estrategia y exchange, contribución al CVaR95 (con el presupuesto y con el paper ahora) y el paper frente a las bandas del 5 %, la mediana y el 95 % del backtest de H2 | `uv run pq research budget` y `uv run pq paper run` (PQ-84) |

Si falta un artefacto, la página lo dice y, debajo, en «Para el equipo», muestra el comando que lo
genera.

### Navegación por páginas y rendimiento (PQ-127)

- **Páginas en el menú lateral:** cada pregunta es una página (`st.navigation`), agrupada en
  Resultados, Para ti, En vivo y Técnico. Solo se ejecuta la página visible. Con `st.tabs` se
  calculaban las 9 en cada interacción. En un teléfono, el menú se pliega tras el botón «»».
- **Simulador en un fragmento** (`st.fragment`): sus controles solo recalculan el simulador.
- **Medir los tiempos:** se levanta el dashboard con `--server.enableAgentApi=true` y se ejecuta
  `uv run python scripts/medir_dashboard.py --url http://127.0.0.1:8501`. El script mide la
  primera carga, una segunda sesión, cada página y tres cambios en el simulador. Los resultados de
  PQ-127 están en `docs/academico/segunda-opinion-ux-dashboard.md`.
- **Modo feria:** `?modo=feria` se recuerda en la sesión, porque la navegación limpia la URL. Cada
  paso del recorrido tiene un enlace a su página.
- **Portada:**
    - una frase con el estado del paper y sus cifras con comparación (`summary.paper_headline`);
    - las estrategias descartadas en gris, porque descartar es el protocolo funcionando;
    - las estrategias en curso (momentum y Polymarket) en tarjetas, hasta que exista su artefacto
      en `research/`.
- **Datos frescos:** la predicción del funding avisa si el último dato tiene más de 16 h, es decir,
  más de dos liquidaciones.

### La página de cartera (PQ-84)

![Pestaña «¿Cómo se reparte? Cartera» con los datos del 21-nov-2026](../academico/img/dashboard-cartera.png)

Captura del 21-nov-2026, con el paper fuera de posición (el carry no ha entrado) y el presupuesto
recomendado al 100 % en efectivo. Las capturas de todas las páginas se regeneran con
`uv run --group e2e python scripts/capture_dashboard.py --url http://127.0.0.1:8501` en
`reports/storytelling/_img/dashboard/`, que no se versiona.

## Accesibilidad y formato (PQ-126)

- **Formato español:** todas las cifras de las tablas salen ya formateadas (`style.pct`,
  `style.usd`, `style.number`). Si se dejaran como números, la tabla de Streamlit las mostraría con
  punto decimal. Un test falla si aparece un número con punto en una tabla.
- **Veredictos:**
    - en las tablas, `✓ pasa` / `✗ no pasa`, que existen en las fuentes normales;
    - en los títulos, iconos Material, que vienen con Streamlit.

  Los emojis (✅ ❌) se veían como un cuadrado en un navegador sin fuente de emojis, que es lo que
  pasa en las capturas generadas en WSL.
- **Textos alternativos:** cada gráfico y cada tabla llevan `alt=`, con la conclusión cuando la
  hay.
- **Contraste:** el azul de marca es `#266ec6`, con 4,96:1 sobre el fondo y 4,54:1 sobre la
  superficie secundaria (WCAG 2.1 AA). El anterior `#2a78d6` daba 4,30:1 y 3,94:1.
- **Limitación conocida:** Streamlit declara la página con `lang="en"` y no permite cambiarlo. Un
  lector de pantalla leerá el español con pronunciación inglesa (WCAG 3.1.1). Hay que revisarlo
  cuando Streamlit lo permita.
- **Estado normal sin recuadros:** el runner en marcha y el kill-switch armado se muestran como
  insignias. Los recuadros de color quedan para los fallos.

## Seguridad del contenedor

- `data/` se monta con `:ro`: el panel no puede modificar el lakehouse.
- Root filesystem en solo lectura, usuario `pq` (uid 10001), sin capacidades (`cap_drop: ALL`).
- Puerto publicado solo en `127.0.0.1`: no queda expuesto a la red.
- La imagen no contiene `.env` ni datos (`.dockerignore`).

## Pruebas en navegador y capturas (PQ-41)

[Playwright](https://playwright.dev/python/) abre el dashboard en un Chromium sin ventana, como lo vería
un usuario. Complementa las pruebas de `AppTest` (que ejecutan el script sin navegador) y comprueba lo
que ellas no ven: que el contenedor sirve la página, que todas las páginas se pueden abrir y que ninguna
muestra un error.

```bash
make e2e            # levanta el contenedor, instala Chromium la primera vez y corre tests/e2e/
make screenshots    # una imagen PNG por página (con `--movil`, a 375 px) en reports/storytelling/_img/dashboard/
```

- Las pruebas aceptan datos reales o un lakehouse vacío: cada página debe mostrar una tabla o el aviso
  con el comando que genera el artefacto.
- En la CI corren en el job *Imagen Docker del dashboard*, contra el contenedor recién construido.
- Las capturas sirven para el informe y la presentación; quedan fuera de git porque se regeneran.
- El grupo de dependencias `e2e` no se instala por defecto: `uv sync --group e2e`.
