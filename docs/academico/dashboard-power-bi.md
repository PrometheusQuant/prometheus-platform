# Dashboard de negocio en Power BI (cap. 7.2)

**Ticket:** PQ-47 · **Épica:** PQ-10 · **Datos:** [capa gold](../arquitectura/modelo-gold.md) (PQ-46)

El ítem 7.2 del Proyecto Integrador pide un panel en Power BI o Tableau, navegable por un usuario
no técnico. El tablero en Streamlit ([ADR-0009](../adr/0009-streamlit-y-docker-para-el-dashboard.md))
sigue siendo la demo en vivo del ítem 7.3.

Esta guía está pensada para alguien que **nunca usó Power BI**. El agente ya preparó todo lo que no
requiere hacer clic en la aplicación:

| Archivo (en [`reports/powerbi/`][carpeta]) | Para qué |
|---|---|
| [`consultas.pq`][consultas] | Una consulta de Power Query por tabla, ya tipada: se copian y pegan |
| [`medidas.dax`][medidas] | Todas las medidas DAX, comentadas |
| [`tema-prometheusquant.json`][tema] | Colores accesibles (paleta Okabe-Ito, segura para daltonismo) |

A David o a Boris les queda importar, relacionar, armar las 5 páginas y comprobar los
**valores de control** del final. En total son unas 2 horas la primera vez.

[carpeta]: https://github.com/PrometheusQuant/prometheus-platform/tree/develop/reports/powerbi
[consultas]: https://github.com/PrometheusQuant/prometheus-platform/blob/develop/reports/powerbi/consultas.pq
[medidas]: https://github.com/PrometheusQuant/prometheus-platform/blob/develop/reports/powerbi/medidas.dax
[tema]: https://github.com/PrometheusQuant/prometheus-platform/blob/develop/reports/powerbi/tema-prometheusquant.json

!!! note "Sobre los nombres de los menús"
    Se dan en español, con el nombre en inglés entre paréntesis. Los marcados con **(†)** no se
    pudieron verificar en una instalación en español. Si no coinciden, busque el nombre en inglés:
    la posición en la cinta es la misma.

## 1. Preparación (una sola vez)

1. **Instalar Power BI Desktop.** Es gratis, desde Microsoft Store, buscando «Power BI Desktop».
   Solo existe para Windows.
2. **Generar los datos** en la terminal de Ubuntu:

    ```bash
    cd ~/code/prometheus-platform
    uv run pq gold build
    ```

    Deja 13 archivos CSV y un `DICCIONARIO.md` en `data/gold/export/`.

3. **Copiar la carpeta a Windows.** Power BI lee mejor una ruta de Windows que la red de WSL.
    - En el Explorador de archivos, abra
      `\\wsl.localhost\Ubuntu\home\dq-datasci\code\prometheus-platform\data\gold\export`.
      En versiones viejas de Windows, `\\wsl$\Ubuntu\...`.
    - Copie la carpeta `export` completa a `C:\PrometheusQuant\gold\export`.
    - Para actualizar los datos más adelante: `uv run pq gold build`, volver a copiar la carpeta y
      pulsar **Actualizar** (*Refresh*) en Power BI.
4. **Desactivar dos automatismos que estorban.** Vaya a **Archivo > Opciones y configuración >
   Opciones** (*File > Options and settings > Options*). En **Archivo actual > Carga de datos**
   (*Current file > Data load*), desmarque:
    - **Detectar automáticamente nuevas relaciones después de cargar los datos** (*Autodetect new
      relationships after data is loaded*) (†). Si queda marcado, Power BI une columnas que solo
      se llaman igual: `hipotesis` o `cvar95`.
    - **Fecha y hora automáticas** (*Auto date/time*) (†). Ya tenemos nuestra propia tabla de
      fechas.
5. **Separadores de DAX.** Si al pegar una medida aparece un error de sintaxis con las comas, vaya a
   **Opciones > Global > Configuración regional** (*Global > Regional settings*) (†) y elija usar
   los **separadores de DAX estándar** (coma entre argumentos y punto decimal), que son los de
   `medidas.dax`.

## 2. Importar las 13 tablas

Las consultas de [`consultas.pq`][consultas] tipan cada columna con la configuración regional
**Inglés (Estados Unidos)**. Esto importa en Bolivia: con la configuración española, `0.0001` se
leería como `1` o como texto, porque allí el decimal es la coma.

1. **Inicio > Transformar datos** (*Home > Transform data*) abre el **Editor de Power Query**.
2. Cree el parámetro de la carpeta:
    - Vaya a **Inicio > Administrar parámetros > Nuevo parámetro** (*Manage Parameters > New
      Parameter*).
    - Nombre: `Carpeta`. Tipo: **Texto** (*Text*).
    - Valor actual: `C:\PrometheusQuant\gold\export\`, **con la barra final**.
3. Por cada bloque de `consultas.pq` (son 13; cada uno empieza con `// ---- nombre`):
    1. **Inicio > Nuevo origen > Consulta en blanco** (*New Source > Blank Query*).
    2. **Inicio > Editor avanzado** (*Advanced Editor*). Borre lo que haya y pegue el bloque desde
       `let` hasta `Tipado`.
    3. En el panel derecho, en **Nombre** (*Name*), ponga el nombre exacto de la tabla, por
       ejemplo `dim_fecha`.
4. Revise que cada columna muestre el ícono de su tipo:
    - fecha (calendario);
    - número (1.2 o 123);
    - texto (ABC);
    - verdadero/falso.

    Las celdas vacías deben decir `null`, no `Error`.
5. **Inicio > Cerrar y aplicar** (*Close & Apply*).

Para cambiar la carpeta más adelante, basta con editar el parámetro `Carpeta`: todas las tablas la
usan.

## 3. Modelo: las 8 relaciones de la estrella

Abra la **Vista de modelo** (*Model view*), el tercer ícono de la barra izquierda. Borre cualquier
relación que Power BI haya creado sola, y cree **exactamente** estas desde **Inicio > Administrar
relaciones > Nueva** (*Manage relationships > New*):

| Desde (muchos) | Columna | Hacia (uno) | Columna |
|---|---|---|---|
| `fact_funding_diario` | `fecha` | `dim_fecha` | `fecha` |
| `fact_funding_diario` | `simbolo` | `dim_simbolo` | `simbolo` |
| `fact_mercado_diario` | `fecha` | `dim_fecha` | `fecha` |
| `fact_mercado_diario` | `simbolo` | `dim_simbolo` | `simbolo` |
| `fact_retorno_estrategia` | `fecha` | `dim_fecha` | `fecha` |
| `fact_retorno_estrategia` | `configuracion_id` | `dim_configuracion` | `configuracion_id` |
| `fact_desempeno` | `configuracion_id` | `dim_configuracion` | `configuracion_id` |
| `fact_metricas_modelo` | `modelo_id` | `dim_modelo` | `modelo_id` |

Configure **cada una** así:
- **Cardinalidad:** **Varios a uno (\*:1)** (*Many to one*).
- **Dirección de filtro cruzado:** **Único** (*Single*).
- Casilla **Activar esta relación** (*Make this relationship active*) marcada.

Las tablas `fact_gates`, `fact_escenarios`, `fact_frontera` y `fact_calidad` quedan **sin
relaciones**. Son resultados agregados, no series en el tiempo ([modelo gold](../arquitectura/modelo-gold.md)),
y se filtran por sus propias columnas.

**Tabla de fechas:**
1. Seleccione `dim_fecha`.
2. Vaya a **Herramientas de tabla > Marcar como tabla de fechas** (*Table tools > Mark as date
   table*).
3. Elija la columna `fecha`.

## 4. Medidas

1. Cree una tabla vacía para agruparlas:
    - Vaya a **Inicio > Escribir datos** (*Enter data*).
    - Nombre: `Medidas`.
    - Pulse **Cargar** (*Load*).
2. Con la tabla `Medidas` seleccionada, por cada bloque de [`medidas.dax`][medidas], vaya a
   **Herramientas de tabla > Nueva medida** (*New measure*). Pegue el bloque desde el nombre hasta
   antes del siguiente comentario y pulse Enter.
3. Dé formato a cada medida en **Herramientas de medidas > Formato** (*Measure tools > Format*):
    - **Porcentaje** con 2 decimales para retornos, CAGR, volatilidad, drawdown, funding,
      probabilidades y CVaR.
    - **Número** con 2 decimales para Sharpe y Calmar.
4. La columna auxiliar de la tabla `Medidas` se puede ocultar con clic derecho > **Ocultar en la
   vista de informe** (*Hide in report view*).

Las medidas de rendimiento solo calculan con **una** configuración en contexto. Con varias,
devuelven vacío para no mezclar estrategias. En un gráfico con `configuracion_id` en la leyenda,
cada línea se calcula por separado.

## 5. Tema

Vaya a **Vista > Temas > Examinar temas** (*View > Themes > Browse for themes*) y elija
[`tema-prometheusquant.json`][tema]. Los colores son distinguibles con daltonismo, y el verde y el
rojo se reservan para «bueno» y «malo».

## 6. Las 5 páginas

Cada página responde a una pregunta, igual que las pestañas del tablero en Streamlit. Para agregar
una página, use el **+** de la barra inferior. Los visuales están en el panel **Visualizaciones**
(*Visualizations*).

**Segmentadores** (*Slicers*). El ticket pide al menos tres:
- **Símbolo:** `dim_simbolo[simbolo]`.
- **Fecha:** `dim_fecha[fecha]`, con estilo **Entre** (*Between*).
- **Hipótesis:** `dim_configuracion[hipotesis]`.
- **Configuración:** `dim_configuracion[configuracion]`.

Para que un segmentador afecte a todas las páginas, use **Vista > Sincronizar segmentaciones**
(*View > Sync slicers*).

### Página 1. Resumen ejecutivo: «¿Vale la pena el carry?»

```text
┌─ Hipótesis [H2] ──────────┐ ┌─ Configuración [k9-theta20] ─┐ ┌─ Fecha [2020 ─── 2024] ─┐
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────────────────┤
│ CAGR         │ Sharpe       │ Máx. drawdown│ Gates        │ P(pérdida) sin quiebra   │
│ (tarjeta)    │ (tarjeta)    │ (tarjeta)    │ (tarjeta)    │ (tarjeta)                │
├──────────────┴──────────────┴──────────────┴──────────────┴──────────────────────────┤
│ Capital acumulado (líneas): eje = dim_fecha[fecha], valores = [Capital acumulado]    │
├──────────────────────────────────────────────┬───────────────────────────────────────┤
│ Texto: qué es el carry y qué decidió el      │ Tarjeta de varias filas: Configuración│
│ protocolo (H1 descartada, H2 al holdout)     │ elegida, Sharpe B1, CAGR B1           │
└──────────────────────────────────────────────┴───────────────────────────────────────┘
```

**Tarjetas** (*Card*):
- [CAGR], [Sharpe anualizado] y [Máximo drawdown].
- [Gates (texto)]: filtre el visual con `fact_gates[hipotesis]` = H2 en el panel **Filtros**
  (*Filters*).
- [P(pérdida)]: filtre el visual con `fact_escenarios[escenario]` = «sin quiebra del exchange».

**Valores iniciales de los segmentadores:** Hipótesis = H2, Configuración = k9-theta20.

### Página 2. Datos y calidad: «¿Qué pasó? ¿Son confiables los datos?»

| Visual | Campos |
|---|---|
| Tarjetas | [Filas en silver], [Huecos detectados], [Outliers marcados], [Días incompletos] |
| Tabla (*Table*) | `fact_calidad`: tabla, filas, huecos, periodos_faltantes, hueco_mayor_horas, outliers, desde, hasta |
| Gráfico de líneas | Eje `dim_fecha[fecha]`, valores [Funding anualizado medio], leyenda `dim_simbolo[simbolo]` |
| Gráfico de columnas agrupadas (*Clustered column*) | Eje `dim_simbolo[simbolo]`, valores [Días incompletos] |
| Segmentadores | Símbolo, Fecha |

Pie de página sugerido: «Los huecos se informan, no se rellenan. `fact_calidad` describe toda la
historia de silver (hasta 2026-09-30): es la única tabla que pasa del inicio del holdout, y solo
contiene disponibilidad de datos, sin precios ni tasas.»

### Página 3. Estrategia frente al benchmark: «¿Funciona? ¿Le gana a no hacer nada especial?»

```text
┌─ Hipótesis ─┐ ┌─ Configuración (selección múltiple) ─┐ ┌─ Fecha ─────────────────────┐
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Capital acumulado por configuración (líneas, leyenda = dim_configuracion[configuracion]) │
├───────────────────────────────────────────────┬─────────────────────────────────────┤
│ Matriz: filas configuracion; valores CAGR,     │ Columnas agrupadas: Sharpe (research)│
│ Sharpe anualizado, Volatilidad anual,          │ por configuracion_id, filtrado a la  │
│ Máximo drawdown, Calmar, % días con exposición │ elegida y a B1 de cada hipótesis     │
├───────────────────────────────────────────────┴─────────────────────────────────────┤
│ Tabla fact_gates: gate, criterio, valor, pasa   (filtro: fact_gates[hipotesis])      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Nota para el texto de la página.** B1 (carry siempre activo) no tiene serie diaria en gold, solo
sus métricas en `fact_desempeno`. Por eso se compara con las medidas «(research)», no con la curva.

### Página 4. Modelo de funding: «¿Qué predice?»

| Visual | Campos |
|---|---|
| Tarjetas | [Mejor AUC], [Mejor clasificador], [Mejor R2] |
| Tabla | `dim_modelo`: tarea, algoritmo, ajustado; `fact_metricas_modelo`: rmse, mae, r2, auc, f1 |
| Gráfico de barras (*Bar chart*) | Eje `dim_modelo[algoritmo]`, valores `fact_metricas_modelo[auc]`, leyenda `dim_modelo[ajustado]` (filtro `tarea` = clasificacion) |
| Segmentador | `dim_modelo[tarea]` |

Texto sugerido: «El clasificador mejora a la regla simple, pero no se usa para operar sin un
pre-registro nuevo (H3): adoptarlo tras verlo funcionar sería sobreajuste.»

### Página 5. Riesgo: «¿Qué riesgo hay?»

| Visual | Campos |
|---|---|
| Segmentador (selección única, *Single select*) | `fact_escenarios[escenario]` |
| Tarjetas | [Retorno anual medio simulado], [P(pérdida)], [P(rendir menos que el 4 %)], [CVaR 95 %] |
| Gráfico de columnas agrupadas | Eje `fact_escenarios[escenario]`; valores media, mediana, p5, p95 |
| Gráfico de dispersión (*Scatter chart*) o de líneas | Eje X `fact_frontera[peso_carry]`, eje Y `fact_frontera[retorno_esperado]`, leyenda `fact_frontera[cumple]` |
| Tarjeta | [Peso máximo que cumple] |

Texto sugerido: «Con un 2 % anual de probabilidad de quiebra del exchange, el carry rinde menos
que una stablecoin al 4 %. Por eso el capital por exchange se limita (cap. 6).»

## 7. Guardar y exportar

1. Para guardar: **Archivo > Guardar como** (*Save as*) en
   `\\wsl.localhost\Ubuntu\home\dq-datasci\code\prometheus-platform\reports\powerbi\prometheusquant.pbix`,
   o guarde en Windows y cópielo ahí.
2. Para exportar el PDF: **Archivo > Exportar > Exportar a PDF** (*Export > Export to PDF*), y guárdelo
   junto al `.pbix` como `prometheusquant.pdf`.
3. Para las capturas de cada página, use **Recorte** (Windows + Shift + S). Guárdelas como PNG en
   `reports/powerbi/capturas/01-resumen.png`, `02-datos.png` y así sucesivamente.
4. Súbalo en un PR con la clave PQ-47. El `.pbix` incluye los datos (≈ 3 MB) y no contiene
   secretos.

## 8. Valores de control: comprobar que el DAX está bien

Antes de dar el tablero por terminado, ponga cada medida en una tarjeta con los filtros indicados
y compare con esta tabla. **Si un valor no coincide, la medida o la relación está mal.** Los
valores se calcularon el 2026-11-06 sobre el lakehouse real, con las mismas fórmulas que research
(`research/validation.py`), usando:

```bash
uv run python scripts/powerbi.py control --gold data/gold
```

Si se reconstruye gold con datos nuevos, hay que volver a ejecutar ese comando.

**Filas de cada tabla.** Vista de tabla, abajo a la izquierda, o una tarjeta con «Recuento» de
cualquier columna:

| Tabla | Filas | Tabla | Filas |
|---|---|---|---|
| `dim_fecha` | 1.643 | `fact_desempeno` | 4 |
| `dim_simbolo` | 5 | `fact_gates` | 8 |
| `dim_configuracion` | 20 | `fact_metricas_modelo` | 15 |
| `dim_modelo` | 15 | `fact_escenarios` | 3 |
| `fact_funding_diario` | 7.911 | `fact_frontera` | 21 |
| `fact_mercado_diario` | 7.898 | `fact_calidad` | 15 |
| `fact_retorno_estrategia` | 29.538 | | |

**Estrategia.** Segmentador de configuración en el valor indicado y sin filtro de fechas:

| Medida | H2 / k9-theta20 | H1 / k3-theta20 |
|---|---|---|
| [Días evaluados] | 1.641 | 1.641 |
| [Retorno acumulado] | 24,70 % | 32,89 % |
| [CAGR] | 5,03 % (5,0330 %) | 6,53 % (6,5290 %) |
| [Sharpe anualizado] | 5,57 (5,5746) | 7,70 (7,6964) |
| [Volatilidad anual] | 0,88 % | 0,82 % |
| [Máximo drawdown] | −0,39 % | −0,51 % |
| [% días con exposición] | 41,13 % | 42,90 % |
| [Sharpe (research)] | 5,5728 | 7,6937 |
| [CAGR (research)] | 5,0299 % | 6,5249 % |

**¿Por qué el Sharpe de gold (5,5746) no es idéntico al de research (5,5728)?** No es un error. Las
medidas «(research)» son las que publicó la evaluación, calculadas sobre **1.642 días**. Ese último
día se valora a las 00:00 del 2024-07-01, e incluye una liquidación que ya es del holdout
([KE-014](../runbooks/errores-conocidos.md)). La capa gold lo excluye y termina el 2024-06-29, con
**1.641 días**. La diferencia es de la tercera cifra decimal y no cambia ninguna conclusión.

**Otros:**

| Medida | Filtro | Valor |
|---|---|---|
| [Funding anualizado medio] | Símbolo = BTCUSDT | 15,05 % |
| [Funding anualizado medio] | Símbolo = ETHUSDT | 18,29 % |
| [Funding anualizado medio] | Símbolo = XRPUSDT | 20,10 % |
| [Funding anualizado medio] | Símbolo = BNBUSDT | −0,44 % |
| [Funding anualizado medio] | Símbolo = SOLUSDT | −1,35 % (lo arrastra la quiebra de FTX: el 2022-11-10 el día promedió −6.144 % anualizado; la mediana es 10,95 %) |
| [Gates (texto)] | `fact_gates[hipotesis]` = H2 | 4 de 4 |
| [Gates (texto)] | `fact_gates[hipotesis]` = H1 | 3 de 4 |
| [P(pérdida)] | Escenario «sin quiebra del exchange» | 15,90 % |
| [CVaR 95 %] | Escenario «sin quiebra del exchange» | 1,02 % |
| [Mejor AUC] | Sin filtros | 0,9775 |
| [Mejor clasificador] | Sin filtros | clasificacion/random_forest/ajustado |

Los porcentajes de [% días con exposición] son mayores que el «tiempo invertido» de la evaluación
(27 % en H2). La medida cuenta cualquier día con un retorno distinto de cero, aunque la posición
haya estado abierta unas pocas horas. Es una aproximación y su nombre lo dice.

## 9. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| Los números aparecen alineados a la izquierda o con ícono ABC | Se importó con el asistente de CSV en configuración española | Use las consultas de `consultas.pq`, que fijan `en-US`; o, en Power Query, clic derecho en la columna > **Cambiar tipo > Usar configuración regional** (*Change type > Using locale*) > Número, Inglés (Estados Unidos) |
| `0.0001` aparece como `1` o como 1.000.000 | Ídem: el punto se tomó como separador de miles | Ídem |
| Las fechas son texto y no se puede marcar la tabla de fechas | Columna `fecha` sin tipo fecha | Revise el paso `Tipado` de la consulta; debe decir `type date` |
| «Error» en celdas vacías | Se tipó antes de convertir los vacíos en null | Use la consulta completa, que tiene el paso `SinVacios` |
| `DataSource.Error: no se encuentra el archivo` | El parámetro `Carpeta` no termina en `\` o la carpeta no se copió | Edite el parámetro y revise la ruta |
| Relación «ambigua» o línea punteada (inactiva) | Hay una relación extra creada automáticamente | Borre todas las que no estén en la tabla de la sección 3 |
| Una medida de rendimiento sale vacía | Hay varias configuraciones en contexto | Elija una en el segmentador o ponga `configuracion_id` en la leyenda |
| [Máximo drawdown] tarda unos segundos | Es un cálculo cuadrático en el número de días (por diseño) | Normal; con 1.641 días tarda alrededor de 1 s |
| Error de sintaxis en una medida pegada | Separadores de DAX regionales (punto y coma) | Sección 1, paso 5 |
| La curva de capital no se reescala al filtrar fechas | Se usó la columna `capital` (acumulada desde 2020) | Use [Capital acumulado]: compone solo los días del periodo seleccionado (el primer punto vale 1 + el retorno de ese día) |
