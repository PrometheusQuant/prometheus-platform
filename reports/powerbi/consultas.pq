// Consultas de Power Query (M) para el modelo gold. Generado por scripts/powerbi.py.
// No editar a mano: regenerar con `uv run python scripts/powerbi.py consultas`.
// Requiere un parámetro de texto «Carpeta» que termine en barra invertida, p. ej.
// "C:\PrometheusQuant\gold\export\"

// ---- dim_fecha: Calendario continuo que cubre todas las fechas de los hechos.
// Consulta en blanco > Editor avanzado; nombre de la consulta: dim_fecha
let
    Origen = Csv.Document(File.Contents(Carpeta & "dim_fecha.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"fecha", type date}, {"anio", Int64.Type}, {"trimestre", Int64.Type}, {"mes", Int64.Type}, {"nombre_mes", type text}, {"dia_semana", type text}, {"periodo", type text}}, "en-US")
in
    Tipado

// ---- dim_simbolo: Pares negociados y la hipótesis pre-registrada que los usa.
// Consulta en blanco > Editor avanzado; nombre de la consulta: dim_simbolo
let
    Origen = Csv.Document(File.Contents(Carpeta & "dim_simbolo.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"simbolo", type text}, {"activo_base", type text}, {"activo_cotizado", type text}, {"hipotesis", type text}}, "en-US")
in
    Tipado

// ---- dim_configuracion: Grid pre-registrado del carry (k x θ) y el benchmark B1 de cada hipótesis.
// Consulta en blanco > Editor avanzado; nombre de la consulta: dim_configuracion
let
    Origen = Csv.Document(File.Contents(Carpeta & "dim_configuracion.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"configuracion_id", type text}, {"hipotesis", type text}, {"configuracion", type text}, {"ventana_k", Int64.Type}, {"umbral_theta", type number}, {"es_seleccionada", type logical}, {"es_benchmark", type logical}, {"sharpe_cpcv", type number}}, "en-US")
in
    Tipado

// ---- dim_modelo: Modelos del funding: regresión del nivel/residuo y clasificación del régimen.
// Consulta en blanco > Editor avanzado; nombre de la consulta: dim_modelo
let
    Origen = Csv.Document(File.Contents(Carpeta & "dim_modelo.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"modelo_id", type text}, {"tarea", type text}, {"algoritmo", type text}, {"ajustado", type logical}, {"formulacion", type text}}, "en-US")
in
    Tipado

// ---- fact_funding_diario: Funding cobrado o pagado por las posiciones cortas en el perpetuo, por día.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_funding_diario
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_funding_diario.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"fecha", type date}, {"simbolo", type text}, {"funding_total", type number}, {"funding_medio", type number}, {"funding_anualizado_medio", type number}, {"liquidaciones", Int64.Type}}, "en-US")
in
    Tipado

// ---- fact_mercado_diario: Cierre diario de spot y perpetuo, base y volumen negociado.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_mercado_diario
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_mercado_diario.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"fecha", type date}, {"simbolo", type text}, {"cierre_spot", type number}, {"cierre_perp", type number}, {"base", type number}, {"volumen_spot_usd", type number}, {"volumen_perp_usd", type number}, {"horas_spot", Int64.Type}, {"horas_perp", Int64.Type}}, "en-US")
in
    Tipado

// ---- fact_retorno_estrategia: Retorno diario de cartera de cada configuración del grid, neto de costes.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_retorno_estrategia
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_retorno_estrategia.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"fecha", type date}, {"configuracion_id", type text}, {"retorno", type number}, {"capital", type number}}, "en-US")
in
    Tipado

// ---- fact_desempeno: Métricas del periodo de desarrollo de la configuración elegida y del benchmark.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_desempeno
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_desempeno.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"configuracion_id", type text}, {"sharpe", type number}, {"cagr", type number}, {"max_drawdown", type number}, {"calmar", type number}, {"t_stat", type number}, {"dias", Int64.Type}}, "en-US")
in
    Tipado

// ---- fact_gates: Gates anti-sobreajuste del pre-registro (G1-G4) y su resultado.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_gates
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_gates.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"gate_id", type text}, {"hipotesis", type text}, {"gate", type text}, {"criterio", type text}, {"valor", type number}, {"pasa", type logical}}, "en-US")
in
    Tipado

// ---- fact_metricas_modelo: Métricas de validación walk-forward; las que no aplican a la tarea quedan nulas.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_metricas_modelo
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_metricas_modelo.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"modelo_id", type text}, {"rmse", type number}, {"mae", type number}, {"r2", type number}, {"auc", type number}, {"f1", type number}}, "en-US")
in
    Tipado

// ---- fact_escenarios: Distribución del retorno anual simulado del carry según el riesgo del exchange.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_escenarios
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_escenarios.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"escenario", type text}, {"media", type number}, {"mediana", type number}, {"p5", type number}, {"p95", type number}, {"var95", type number}, {"cvar95", type number}, {"prob_bajo_hurdle", type number}, {"prob_perdida", type number}, {"tiempo_invertido", type number}, {"ciclos", type number}}, "en-US")
in
    Tipado

// ---- fact_frontera: Optimización con CVaR: retorno esperado y riesgo según el peso en el carry.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_frontera
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_frontera.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"peso_carry", type number}, {"retorno_esperado", type number}, {"cvar95", type number}, {"cumple", type logical}}, "en-US")
in
    Tipado

// ---- fact_calidad: Informe de calidad de cada tabla silver: filas, huecos y outliers. Única excepción al corte del holdout: describe la disponibilidad de **toda** la historia de silver (hasta 2026-09-30), sin precios, tasas ni retornos.
// Consulta en blanco > Editor avanzado; nombre de la consulta: fact_calidad
let
    Origen = Csv.Document(File.Contents(Carpeta & "fact_calidad.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    // Los nulos llegan como texto vacío: se convierten en null antes de tipar.
    SinVacios = Table.TransformColumns(
        Encabezados, {}, each if _ = "" then null else _),
    Tipado = Table.TransformColumnTypes(SinVacios, {{"tabla", type text}, {"filas", Int64.Type}, {"duplicados_eliminados", Int64.Type}, {"huecos", Int64.Type}, {"periodos_faltantes", Int64.Type}, {"hueco_mayor_horas", type number}, {"outliers", Int64.Type}, {"desde", type text}, {"hasta", type text}}, "en-US")
in
    Tipado
