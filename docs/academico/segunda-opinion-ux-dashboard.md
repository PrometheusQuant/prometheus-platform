# Segunda opinión de UX del dashboard (PQ-125)

- **Fecha:** 2026-11-24.
- **Versión auditada:** `develop` en `60a1ea4`, que ya incluye la iteración 2 de PQ-124. Se usaron
  los datos reales del lakehouse.
- **Motivo:** el titular pidió una segunda opinión sobre el rediseño de PQ-124, con skills distintas
  de las que usó esa auditoría (`ux-audit`, `design-critique` y `dataviz`, ver
  [auditoría de PQ-124](auditoria-ux-dashboard.md)).
- **Alcance:** solo diagnóstico. No se cambió el código del dashboard, para no chocar con PQ-124.

## Método: cuatro lentes nuevas

| Lente | Qué aporta | Origen |
|---|---|---|
| `developing-with-streamlit` | Las prácticas de la propia plataforma: componentes, rendimiento, accesibilidad (`alt=`), iconos y formato | Skill oficial de Streamlit, incluida en el paquete (1.67) |
| `dashboard-design` | Principios de Stephen Few (*Information Dashboard Design*): contexto de cada cifra, color con significado, resaltar solo lo que requiere atención | d7mtg/dashboard-design |
| `impeccable` | Crítica de diseño general: plantillas gastadas, ancho de línea, contraste | Instalada **incompleta** en esta máquina: solo trae `SKILL.md`, sin sus referencias ni scripts. Se aplicaron sus reglas generales; su crítica puntuada no se pudo usar |
| `accessibility-review` + `ux-copy` | WCAG 2.1 AA y coherencia de los textos | Plugins de diseño ya instalados en la máquina |

**Evidencia:**

- **Capturas** de las 9 pestañas con `scripts/capture_dashboard.py`, más una pasada a 375 px de
  ancho. Están en `img/ux-segunda-opinion/`.
- **Tiempos** medidos con la API de agente de Streamlit (`--server.enableAgentApi=true`).
- **Comprobaciones WCAG automáticas** con Playwright: idioma de la página, nombres accesibles,
  contraste calculado y zoom al 200 %.

## Resumen

El rediseño de PQ-124 resolvió lo más grave: el dashboard ya tiene una portada que se entiende. La
segunda opinión encuentra cinco cosas de peso que esa auditoría no vio:

1. **El mismo resultado se cuenta de dos formas opuestas.** La portada dice que el carry fue
   descartado en la prueba final; la pestaña del carry lo marca «✅ pasa» y dice que la prueba final
   «se abre una sola vez».
2. **El funding «en vivo» muestra datos de hace 4 días sin avisar.** El aviso solo salta si el dato
   es anterior al fin del holdout (2026-09-30).
3. **La primera carga tarda unos 36 s, y cada interacción, de 2 a 3 s.** Las 9 pestañas se calculan
   siempre, aunque solo se vea una.
4. **La portada pone ceros en el lugar más visible y todo en rojo.** No explica por qué el paper no
   ha operado, y presenta «descartada» como alarma, cuando descartar es la prueba de que el
   protocolo funciona.
5. **La localización no está completa,** al contrario de lo que dice la auditoría anterior. La
   simulación, la cartera, el funding y el paper siguen con punto decimal y fracciones en inglés.

## Hallazgos priorizados

Severidad: 🔴 alta (confunde o engaña al jurado), 🟡 media (resta claridad o accesibilidad),
🟢 baja (pulido).

### 🔴 Alta

| # | Hallazgo | Lente | Evidencia | Propuesta |
|---|---|---|---|---|
| 1 | **Veredictos contradictorios del carry.** Portada: «Descartada en la prueba final». Pestaña del carry: «H2 · ✅ pasa», y el texto dice que la prueba final «se abre una sola vez y con el titular», cuando ya se abrió (PQ-50). | `ux-copy` (coherencia), Few (el mensaje que se lee primero tiene que ser el verdadero) | [carry](img/ux-segunda-opinion/02-funciona-carry-y-gates.png), [portada](img/ux-segunda-opinion/01-inicio-como-va.png) | En la pestaña, separar «desarrollo: pasa los gates» de «prueba final: no pasa», con el resultado del holdout arriba, y actualizar el texto. Un solo vocabulario: «prueba final» en todo el tablero, con «holdout» solo en el glosario |
| 2 | **Funding «de hoy» con datos de hace 4 días.** La tabla usa la liquidación del 2026-11-20 16:00 y se consultó el 24-nov. `nowcast.forecast` solo lanza `StaleDataError` si el dato no pasa del 2026-09-30. | Few (contexto), confianza | [funding](img/ux-segunda-opinion/06-que-predice-hoy-funding-en-vivo.png), `research/nowcast.py:117` | Mostrar la antigüedad del dato junto al título y avisar a partir de un umbral corto, por ejemplo más de 16 h, es decir, dos liquidaciones. Si es viejo, cambiar el título a «Última predicción disponible» |
| 3 | **Rendimiento.** Primera carga: 30 s sin respuesta y 6 s más para terminar. Cada rerun con la caché caliente: 3,3 s y 1,9 s. `st.tabs` ejecuta las 9 pestañas en cada rerun, así que mover un control del simulador recalcula también la predicción del funding, el paper y la cartera. No se perfiló; los candidatos son el Monte Carlo del simulador y la predicción del funding, que se recalculan en cada rerun. | `developing-with-streamlit` (`performance.md`, `layouts.md`: no meter trabajo caro sin protección en `st.tabs`) | API de agente: primera respuesta `wait_timed_out` a los 30 s | Pasar a `st.navigation` con una página por pregunta (solo se ejecuta la visible), o usar `on_change="rerun"` en las pestañas y calcular solo la abierta. Envolver el simulador en `st.fragment`, para que sus controles no recalculen el resto |
| 4 | **La portada pone cifras sin contexto en el lugar más visible.** Capital 1.000,00 USD, ganancia 0,00 USD, caída 0,00 %: tres números enormes sin comparación ni explicación. Las dos estrategias llevan una insignia roja y faltan las que están en curso (momentum, Polymarket). | Few (contexto de cada cifra; el rojo solo para alertas), `impeccable` (plantilla de métrica protagonista: número enorme con etiqueta pequeña) | [portada](img/ux-segunda-opinion/01-inicio-como-va.png) | **Una frase arriba que lo explique:** «El paper está en efectivo: desde 2025 el funding nunca llegó al umbral del 20 %». Las cifras, en tamaño normal, con su contexto: días en marcha y comparación con el capital inicial. «Descartada por el protocolo» en gris o neutro, no en rojo. Una tarjeta por estrategia en curso, con su etapa: pre-registrada o en evaluación |

### 🟡 Media

| # | Hallazgo | Lente | Evidencia | Propuesta |
|---|---|---|---|---|
| 5 | **Localización incompleta:** `0.7564`, `0.5488` y `0.40%` en la simulación; `12.5%` y `-4.00%` en la cartera; `0.7%` en el funding; `5.10% anual`, `-0.000098` y `0.9%` en el paper; `0.95` y `0.5` en los criterios de los gates. La tabla del funding da `0.7%` y el texto de debajo dice «del 1 %» para el mismo dato. | `ux-copy` (coherencia) | [simulación](img/ux-segunda-opinion/04-que-riesgo-hay-simulacion.png), [cartera](img/ux-segunda-opinion/08-como-se-reparte-cartera.png), [funding](img/ux-segunda-opinion/06-que-predice-hoy-funding-en-vivo.png), [paper](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png) | Pasar todas las cifras por `style.pct` / `style.number` y mostrar las probabilidades como porcentaje. Un test que recorra las tablas del dashboard y falle si encuentra punto decimal en un número |
| 6 | **Accesibilidad (WCAG 2.1 AA):** (a) la página declara `lang="en"` y todo está en español (3.1.1); (b) los gráficos se anuncian como «Vega visualization», con descripciones automáticas que mezclan inglés y español (1.1.1); (c) ninguna tabla tiene nombre accesible (15 en la página); (d) el azul de marca `#2a78d6` da 4,30:1 sobre el fondo y 3,94:1 sobre la superficie secundaria (1.4.3 exige 4,5:1 en texto normal), y se usa en la pestaña activa y en el valor de los deslizadores. | `accessibility-review`, `developing-with-streamlit` (`alt=` en gráficos y tablas) | Pasada con Playwright | (a) Es una limitación de Streamlit: documentarla y revisar si una versión futura permite fijar el idioma. (b, c) Pasar `alt=` con la conclusión, no con la descripción: «Crece de 1 a 1,33 USD entre 2020 y 2024». (d) `primaryColor = "#266ec6"`, el mismo azul un 7 % más oscuro: 4,96:1 y 4,54:1 |
| 7 | **Alertas siempre encendidas.** En el paper, dos recuadros verdes grandes («Runner en marcha», «Kill-switch armado») para el estado normal. | Few (resaltar solo cuando algo requiere atención), `developing-with-streamlit` (`st.success` es demasiado pesado para un estado) | [paper](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png) | Estado normal: una insignia o un pie de texto. Recuadro de color solo si el runner está caído o el kill-switch activado |
| 8 | **El emoji ✅ sale como un cuadrado vacío** en las capturas: «☐ pasa». Esta máquina no tiene ninguna fuente de emojis (`fc-list`: 0), y las capturas del informe y de la documentación se toman aquí. El ❌ sí se ve. | `developing-with-streamlit` (iconos Material en lugar de emojis) | [carry](img/ux-segunda-opinion/02-funciona-carry-y-gates.png) | Usar `:material/check_circle:` y `:material/cancel:`, que vienen con Streamlit y no dependen de las fuentes del sistema. Ya se usan en la portada |
| 9 | **Tablas que repiten que no pasa nada:** 12 filas idénticas («mantener / fuera») en el paper y 5 frases idénticas en el funding. | Few (mostrar las excepciones, no todos los valores) | [paper](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png), [funding](img/ux-segunda-opinion/06-que-predice-hoy-funding-en-vivo.png) | Una frase de resumen (por ejemplo, «Ninguna liquidación superó el 20 %; la más alta fue 3,6 % en XRP») y la tabla completa en un desplegable |
| 10 | **Simulador:** (a) el histograma usa intervalos como texto (30 barras con etiquetas giradas) y la quiebra del exchange (22 USD) estira el eje, de modo que el rango que importa (992–1.132 USD) queda apretado a la derecha; (b) no marca el capital inicial ni la stablecoin como referencia; (c) «Horizonte» usa botones de radio para 2 opciones; (d) el deslizador muestra `2.00`. | Few (contexto), `developing-with-streamlit` (`selection-widgets.md`) | [simulador](img/ux-segunda-opinion/05-y-si-invierto-simula-tu-inversion.png) | (a) Histograma con eje numérico (`bin=True` en Altair) solo de los casos sin quiebra, y la probabilidad de quiebra como cifra aparte; (b) líneas verticales en 1.000 y en el valor de la stablecoin; (c) `st.segmented_control`; (d) formato `%.1f %%` |
| 11 | **Navegación y cabecera.** De 9 pestañas, a 375 px se ven 2 y media. El título se parte («PrometheusQuan-t») y, con la ruta local, ocupa toda la primera pantalla. La ruta (`/home/dq-datasci/...`) expone el usuario de la máquina y solo le sirve a quien desarrolla. | `developing-with-streamlit` (`st.navigation`), `impeccable` (texto que desborda) | [móvil](img/ux-segunda-opinion/movil-01-inicio.png) | `st.navigation` con las páginas en la barra lateral, que en móvil se pliega. Un título corto. La ruta, a la pestaña técnica |

### 🟢 Baja

| # | Hallazgo | Evidencia | Propuesta |
|---|---|---|---|
| 12 | El eje X de la curva del paper repite fechas («13 nov 13 nov 14 nov…»): marcas cada 12 h con formato de día | [paper](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png) | `axis=alt.Axis(format="%d %b", tickCount="day")` |
| 13 | El gráfico de importancia tiene el eje lleno de marcas (`0,000 0,001 … 0,024`) y etiquetas cortadas («diferencia entre el perpetuo y e…») | [funding](img/ux-segunda-opinion/06-que-predice-hoy-funding-en-vivo.png) | `tickCount=5` y etiquetas más cortas, o `labelLimit` mayor |
| 14 | En el carry, H1 (descartada en desarrollo) va antes que H2, la que llegó a la prueba final. El gráfico de crecimiento no muestra la referencia «siempre invertido» que sí compara la tabla. El Deflated Sharpe «1,000» puede leerse como «mil» | [carry](img/ux-segunda-opinion/02-funciona-carry-y-gates.png) | H2 primero, H1 en un desplegable. La referencia en gris en el mismo gráfico. «≈ 1,00» |
| 15 | Queda jerga para el público no técnico: `S_k anualizada`, «valoración: marca», «pata», el signo del CVaR (`-4.00%` en efectivo). Los estados vacíos dan comandos (`uv run pq …`) | [paper](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png), [cartera](img/ux-segunda-opinion/08-como-se-reparte-cartera.png) | Nombres llanos con ayuda (`help=`). Los comandos, en un pie de texto o en la pestaña técnica |
| 16 | Con `layout="wide"`, el párrafo de la portada ocupa todo el ancho, muy por encima de 75 caracteres por línea | [portada](img/ux-segunda-opinion/01-inicio-como-va.png) | Limitar el texto corrido a una columna |
| 17 | Quedan emojis en el icono de la página (📈) y en los botones del recorrido de la feria (◀ ▶) | `app.py:691-698` | `:material/monitoring:`, `:material/arrow_back:` y `:material/arrow_forward:` |

## Lo que la segunda opinión confirma

- **375 px y zoom al 200 %:** sin desbordes horizontales (el documento mide lo mismo que la
  ventana). Esto cierra la puerta 9 de `ux-audit`, que quedó pendiente en PQ-124.
- **Contraste del texto secundario:** 5,16:1 (texto `#0b0b0b` al 60 % de opacidad sobre `#fcfcfb`).
  Cumple.
- **Tema sin CSS:** solo `config.toml`, salvo el modo feria.
- **APIs vigentes:** usa `width="stretch"`, no el obsoleto `use_container_width`. La consola de
  Streamlit no muestra avisos ni APIs obsoletas.
- **Modelos en caché** con `st.cache_resource`.
- **Insignias de la portada** con icono, texto y color, que no dependen solo del color.

## Cómo repartirlo

Para no pisar PQ-124, se propone:

- **A PQ-124 (Claude A)**, porque son correcciones dentro de su rediseño: hallazgos 1, 5, 7, 8, 12,
  13, 14 y 17. Ninguno cambia la estructura.
- **Ticket nuevo de accesibilidad y textos:** 6, 15 y 16.
- **Ticket nuevo de estructura:** 2, 3, 4, 9, 10 y 11, que tocan la portada, la navegación y el
  rendimiento. Conviene hacerlos antes de la prueba con usuarios (PQ-76), porque cambian lo que se
  va a probar.

## Límites de esta revisión

- `impeccable` está instalada sin sus referencias, así que su crítica puntuada no se aplicó. Si se
  reinstala completa, merece una pasada.
- La accesibilidad se comprobó de forma automática. No hubo pruebas con un lector de pantalla
  real (VoiceOver, NVDA) ni solo con teclado.
- No hubo usuarios: eso es PQ-76.

## Después de PQ-126

Capturas del 24-nov-2026 con los hallazgos 1, 5 a 8 y 12 a 17 resueltos. Las de «antes» están en
`img/ux-segunda-opinion/`.

| Pestaña | Antes | Después |
|---|---|---|
| Inicio | ![](img/ux-segunda-opinion/01-inicio-como-va.png) | ![](img/pq-126/01-inicio-como-va.png) |
| Carry y gates | ![](img/ux-segunda-opinion/02-funciona-carry-y-gates.png) | ![](img/pq-126/02-funciona-carry-y-gates.png) |
| Paper trading | ![](img/ux-segunda-opinion/07-como-va-en-vivo-paper-trading.png) | ![](img/pq-126/07-como-va-en-vivo-paper-trading.png) |
| Cartera | ![](img/ux-segunda-opinion/08-como-se-reparte-cartera.png) | ![](img/pq-126/08-como-se-reparte-cartera.png) |

## Después de PQ-127

Hallazgos 2, 3, 4, 9, 10 y 11. Las capturas del 24-nov-2026 están en `img/pq-127/`.

**Tiempos.** Medidos con la API de agente de Streamlit (`scripts/medir_dashboard.py`), en la misma
laptop, con los datos reales y con la ingesta de Polymarket corriendo de fondo en los dos casos.

| Medida | Antes (9 pestañas) | Después (páginas) |
|---|---|---|
| Primera carga, servidor recién arrancado | 22,4 s | 4,8 s |
| Primera carga, segunda sesión | 2,2 s | 0,6 s |
| Cambio en el simulador (mediana de 3) | 1,75 s | 0,51 s |
| Visita a una página, con la caché caliente | (todo en cada rerun) | de 0,17 a 2,2 s |

El coste de entrenar el clasificador del cap. 5 no desaparece: se traslada a la primera visita de
«¿Qué predice hoy?», que tardó 32,9 s con la caché fría. Se paga una vez por servidor
(`st.cache_resource`) y solo si alguien abre esa página. Antes de la feria conviene abrirla una
vez para calentar la caché.

Antes del cambio, el informe midió unos 36 s en la primera carga. Esta vez se midieron 22,4 s
sobre el mismo código, con otra carga en la máquina. La comparación de la tabla se hizo en las
mismas condiciones.

| Pantalla | Escritorio | 375 px |
|---|---|---|
| Portada | ![](img/pq-127/01-inicio-como-va.png) | ![](img/pq-127/movil-01-inicio-como-va.png) |
| Simulador | ![](img/pq-127/05-y-si-invierto-simula-tu-inversion.png) | ![](img/pq-127/movil-05-y-si-invierto-simula-tu-inversion.png) |
| Funding hoy | ![](img/pq-127/06-que-predice-hoy-funding-en-vivo.png) | |
| Paper trading | ![](img/pq-127/07-como-va-en-vivo-paper-trading.png) | |

**Pendiente:** en una frase larga, «20 %» puede partirse entre el número y el signo. Habría que usar
un espacio duro (`\u00a0`) en `style.pct` y `style.usd`, lo que obliga a actualizar las
expectativas de los tests. Queda como mejora.
