// Póster A3 de la feria (PQ-77). Ninguna cifra va a mano: todas salen de `_resultados.yml`,
// que escribe `uv run pq report inputs --out reports/poster` desde los artefactos.
// Se genera con `make poster`.

#let r = json("_resultados.yml").r

#let navy = rgb("#0F1B2D")
#let ink = rgb("#14213D")
#let soft = rgb("#4A5568")
#let paper = rgb("#F5F3EE")
#let sand = rgb("#E9E5DC")
#let amber = rgb("#E8A33D")
#let rust = rgb("#9C4F12")

#set page(paper: "a3", margin: (x: 15mm, top: 12mm, bottom: 12mm), fill: paper)
#set text(font: ("Liberation Sans", "DejaVu Sans"), size: 13pt, fill: ink, lang: "es")
#set par(leading: 0.62em)

#let eyebrow(body) = text(size: 11pt, weight: "bold", fill: rust, tracking: 1.5pt, upper(body))
#let card(body, fill: sand) = block(fill: fill, radius: 8pt, inset: 11pt, width: 100%, body)
#let big(value, label) = block(width: 100%)[
  #text(size: 30pt, weight: "bold", fill: navy, value) \
  #text(size: 11.5pt, fill: soft, label)
]

// --- Cabecera ----------------------------------------------------------------------------------
#block(fill: navy, radius: 10pt, inset: (x: 18pt, y: 12pt), width: 100%)[
  #text(size: 11pt, weight: "bold", fill: amber, tracking: 1.5pt)[PROYECTO INTEGRADOR · FERIA DEL 4 DE DICIEMBRE DE 2026]
  #v(4pt)
  #text(size: 40pt, weight: "bold", fill: paper)[PrometheusQuant]
  #v(2pt)
  #text(size: 17pt, fill: rgb("#C9D3E0"))[Cobrar el funding sin apostar al precio, y sin engañarnos con el backtest.]
  #v(2pt)
  #text(size: 12pt, fill: rgb("#C9D3E0"))[David Quintela · Boris Miranda]
]

#v(6pt)

// --- Problema y solución -----------------------------------------------------------------------
#grid(
  columns: (1fr, 1fr),
  gutter: 12pt,
  card[
    #eyebrow[El problema]
    #v(2pt)
    #text(size: 17pt, weight: "bold")[Quien opera cripto con algoritmos suele engañarse antes de perder dinero.]
    #v(4pt)
    - *Método:* prueba variantes sin contarlas; alguna sale bien por azar.
    - *Costes:* la literatura usa 1,44 pb en futuros; un minorista VIP 0 paga 5 pb.
    - *Contraparte:* el backtest supone que el exchange no quiebra nunca.
  ],
  card[
    #eyebrow[Nuestra respuesta]
    #v(2pt)
    #text(size: 17pt, weight: "bold")[Una estrategia solo opera si sobrevive a este protocolo.]
    #v(4pt)
    + Pre-registro antes de mirar resultados.
    + Costes reales en cada pata.
    + CPCV, Deflated Sharpe y PBO, con #r.ensayos.total ensayos contados.
    + Holdout de un solo uso (sigue cerrado).
    + Paper trading con kill-switch y alertas.
    + Recién ahí, capital real.
  ],
)

#v(6pt)

// --- Evidencia ---------------------------------------------------------------------------------
#card(fill: rgb("#FBFAF7"))[
  #eyebrow[La evidencia · carry de funding, desarrollo 2020 a junio de 2024, neto de costes]
  #v(6pt)
  #table(
    columns: (1.6fr, 1fr, 1fr, 1fr, 0.8fr, 1.5fr),
    stroke: 0.5pt + sand,
    fill: (col, row) => if row == 0 { sand } else { none },
    inset: (x: 6pt, y: 7pt),
    [*Hipótesis*], [*Retorno anual*], [*Siempre invertido*], [*Caída máx.*], [*PBO*], [*Veredicto*],
    [H1 · BTC y ETH], [#r.h1.cagr], [#r.h1.b1_cagr], [#r.h1.max_dd], [#r.h1.pbo], [#r.h1.veredicto],
    [H2 · SOL, BNB y XRP], [#r.h2.cagr], [#r.h2.b1_cagr], [#r.h2.max_dd], [#r.h2.pbo], [*#r.h2.veredicto*],
  )
  #v(6pt)
  #grid(
    columns: (1fr, 1fr),
    gutter: 14pt,
    [*Le gana a estar siempre invertido:* #r.stats.he1_exceso más al año (p = #r.stats.he1_p).],
    [*Frente a una stablecoin al 4 %, todavía no:* p = #r.stats.he2_p. Por eso no hay capital real aún.],
  )
]

#v(6pt)

// --- Riesgo y arquitectura ---------------------------------------------------------------------
#grid(
  columns: (1fr, 1fr),
  gutter: 12pt,
  card(fill: navy)[
    #text(size: 11pt, weight: "bold", fill: amber, tracking: 1.5pt)[LO QUE EL BACKTEST NO VE · MONTE CARLO]
    #v(6pt)
    #set text(fill: paper)
    #grid(
      columns: (1fr, 1fr),
      gutter: 10pt,
      [#text(size: 30pt, weight: "bold", fill: amber)[#r.sim.media] \ #text(size: 11.5pt, fill: rgb("#C9D3E0"))[retorno medio simulado, sin quiebra]],
      [#text(size: 30pt, weight: "bold", fill: amber)[#r.sim.media_p2] \ #text(size: 11.5pt, fill: rgb("#C9D3E0"))[si el exchange quiebra con un 2 % anual]],
    )
    #v(6pt)
    Por encima de *#r.sim.quiebra_equilibrio* anual de probabilidad de quiebra, conviene la
    stablecoin: con ese número se calibra el límite de capital por exchange.
  ],
  card[
    #eyebrow[Arquitectura hexagonal]
    #v(6pt)
    #let step(name, detail) = block(
      fill: paper, radius: 5pt, inset: (x: 8pt, y: 4pt), width: 100%, above: 3pt, below: 3pt,
    )[*#name* #h(4pt) #text(size: 10.5pt, fill: soft, detail)]
    #let arrow = block(width: 100%, above: 0pt, below: 0pt, align(center, text(size: 8pt, fill: rust)[▼]))
    #step[Binance][API pública y Data Vision, con checksum]
    #arrow
    #step[Lakehouse][bronze → silver → gold, Parquet y DuckDB]
    #arrow
    #step[Research][costes reales, CPCV, DSR, PBO, ensayos]
    #arrow
    #step[Riesgo y ejecución][pre-trade, kill-switch, runner]
    #arrow
    #step[Operación][dashboard, Telegram, respaldos cifrados]
  ],
)

#v(6pt)

// --- Qué sigue ---------------------------------------------------------------------------------
#card[
  #eyebrow[Qué sigue]
  #v(4pt)
  #grid(
    columns: (1fr, 1fr, 1fr),
    gutter: 12pt,
    [*Abrir el holdout, una sola vez*, tras verificar las comisiones reales en la cuenta.],
    [*Más estrategias por el mismo filtro:* tendencia, carry con señal de ML y Polymarket.],
    [*Repartir el carry entre exchanges*, para que una quiebra no lo borre todo.],
  )
  #v(4pt)
  #text(size: 15pt, weight: "bold", fill: navy)[No prometemos rentabilidad. Prometemos no engañarnos.]
]

#v(1fr)

// --- Pie con QR --------------------------------------------------------------------------------
#block(fill: sand, radius: 10pt, inset: 12pt, width: 100%)[
  #grid(
    columns: (auto, 1fr),
    gutter: 16pt,
    image("qr-resultados.svg", width: 40mm),
    [
      #text(size: 18pt, weight: "bold")[Escanea: los resultados, actualizados]
      #v(2pt)
      prometheusquant.github.io/prometheus-platform/resultados \
      Código abierto: github.com/PrometheusQuant/prometheus-platform
      #v(6pt)
      #text(size: 10.5pt, fill: soft)[No es asesoramiento financiero. Resultados de desarrollo y de paper trading con dinero
      simulado; rentabilidades pasadas no garantizan las futuras.]
    ],
  )
]
