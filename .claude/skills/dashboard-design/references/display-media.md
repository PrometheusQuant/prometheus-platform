# Dashboard Display Media

The full library of graphical and textual media suited to dashboard use, with selection guidance for each. A dashboard usually needs several of these, each matched to specific data.

## Text vs graphics: the first choice

Text is serial and precise. Graphics are parallel and pattern-revealing. The trade-off:

Use text when displaying a single value, when the precise number matters, or when the user needs to look up a specific value. A single measure like "YTD Expenses: $487,321" does not need a chart. Text in table form works well for ranked lists (top 10 customers, open issues, tasks needing attention).

Use graphics when shape, trend, comparison, or pattern matters. Bar graphs for comparing discrete values. Line graphs for trend. Scatter plots for correlation. When a dashboard must show multiple measures and enable comparisons, graphics usually win.

Most dashboards blend both. A key measure displayed as text with a sparkline next to it gives the precise current value plus historical context in a tiny footprint.

## Bullet graphs

The bullet graph is the single most important chart type for dashboards. It replaces the gauges, meters, and thermometers that dashboards are often cluttered with. It displays a key measure against one or more comparative measures, with qualitative range bands for instant good/bad interpretation.

**Anatomy:**

- A horizontal or vertical quantitative scale
- A bar (or symbol marker if scale does not start at zero) encoding the primary measure
- A short perpendicular line marking the comparative measure (target, prior period, forecast)
- Two to five background fill bands varying by color intensity to mark qualitative ranges (bad, satisfactory, good)

**Design rules:**

- Quantitative scale starts at zero if using a bar. Use a symbol marker if the scale is narrowed for detail.
- Qualitative ranges use intensity variations of a single hue (not red/yellow/green) so colorblind users can read them.
- No more than five qualitative ranges.
- Multiple comparative markers can be shown with different stroke weights or symbols.
- For a current-vs-future-target comparison, the bar can split into actual-so-far and projected-remainder segments.

**Why this beats gauges:**

Radial gauges waste space on their circular shape. Realistic thermometers waste space on decorative chrome. Bullet graphs are linear so multiple fit in a small area. They support the same comparative and qualitative information in a fraction of the screen real estate. They also read faster because the eye perceives the cross formed when the bar exceeds the target marker preattentively.

## Bar graphs

The workhorse of quantitative comparison. Use when comparing discrete values across a nominal or ordinal category.

**When to use:**

- Sales by region, department, product, or any other nominal category
- Rankings (top N customers, worst N performers)
- Part-to-whole data as an alternative to pie charts
- Interval data where individual values matter more than the overall shape

**Orientation:** Horizontal bars suit long category labels. Vertical bars suit time series when a bar is preferred over a line.

**Rules:**

- Quantitative scale always starts at zero (because bar length encodes value)
- Sort by value unless another order is meaningful
- Use one color for bars unless color encodes something
- Label directly when possible rather than using a legend

## Stacked bar graphs

Narrower use case than people assume. Appropriate only when displaying multiple instances of a whole and its parts, with emphasis on the whole.

**Appropriate use:** Quarterly total sales, broken down by sales channel, shown across four quarters. Total is the primary message, channel breakdown is secondary.

**Inappropriate use:** A single pie-chart-style part-to-whole breakdown. A regular bar graph works better.

**Problem:** Only the bottom segment of each stack has a common baseline for comparison. Other segments appear to float. Reading changes in the middle segments is hard.

If the breakdown of parts matters, use a small-multiples layout of separate bar graphs instead, or a combination bar-and-line graph.

## Combination bar and line graphs

Use when some series are best displayed as bars (individual values matter) and others as a line (trend matters).

**Common pattern:** Revenue and expenses as bars, profit as a line, across twelve months. Bars emphasize the monthly values; the line emphasizes the profit trend.

**Also useful for:** Showing parts and whole together. Parts as bars (one quantitative scale), total as a line (second quantitative scale).

**Pareto charts** are a specific combination type: individual values as bars in ranked order, with a cumulative total as a line. The line slope reveals how concentrated the distribution is.

## Line graphs

The best choice for time-series data and other interval scales when the shape of change matters.

**When to use:**

- Trends over time (daily, monthly, quarterly)
- Rates of change
- Comparison of two or more series' shapes over time
- Cycles, fluctuations, seasonality

**Rules:**

- Scale does not need to start at zero. Narrowing the scale to the data range reveals more detail.
- Data lines should be more visually prominent than axes, grid lines, or reference lines.
- Limit the number of distinct lines to about five. Beyond that, colors become hard to distinguish.

**Not for:** Nominal or ordinal categorical scales. Lines imply continuity between adjacent values. That continuity does not exist between "West," "East," and "Central." Use bars there.

## Sparklines

Tiny line graphs meant to live inline with text or values, providing a compact historical context. Edward Tufte's invention, ideal for dashboards.

**Properties:**

- No quantitative scale shown (precision is not the point)
- Very small footprint, word-sized
- Reveals trend shape at a glance
- Can include a light band to show acceptable range
- Can mark the final value with a colored dot

**Use cases:**

- Next to any current value where history is informative
- Replacing simple up/down trend arrows (which are ambiguous)
- Dense tables where each row shows a metric with its history

A table of key metrics, each with its current value and a sparkline showing twelve months of history, packs enormous context into a small space.

## Box plots

For showing distribution across a range, not just a single summary value. The median of a salary range tells you less than the full distribution does.

**Simple form suitable for dashboards:** A range bar from minimum to maximum, with a data point marking the median. Position of the median relative to the ends reveals skew.

**Full form (box-and-whiskers):** Adds a box showing the interquartile range and whiskers showing outlier thresholds. Often more information than a dashboard needs.

**Use only when distribution matters.** If the viewer only cares about a single summary statistic, use a simpler display.

## Scatter plots

For displaying correlation between two paired quantitative variables. Does nothing else well, but does this one thing better than any alternative.

**Reveals:**

- Whether two variables are correlated
- Direction of correlation (positive, negative)
- Strength of correlation (tight grouping around trend line vs scattered)

**Design:** Add a straight trend line (line of best fit) to make direction and strength visible at a glance. Avoid 3D scatter plots even when they are offered, because they require too much study for a dashboard context.

**Splitting into series:** Two or three series on one scatter plot (by category) is fine if trend lines are included per series.

## Treemaps

For large hierarchically or categorically structured datasets where the goal is spotting conditions of interest, not precise comparison.

**Encoding:** Rectangle size encodes one quantitative variable. Rectangle color can encode a second. Hierarchy is shown by nesting rectangles inside rectangles.

**Good use:** Sales across fifty states where you want to see at a glance which large-revenue states are performing poorly. Size = revenue, color intensity = percent of quota.

**Poor use:** Fine quantitative comparisons. Ranking items. Small datasets where a bar graph works fine.

**Color recommendation:** Single hue varying by intensity rather than red/green, unless a qualitative below/above-target distinction is genuinely useful.

## Icons

A small number of icons serve dashboards well. Three categories cover most needs:

**Alert icons.** Simple colored shape (circle, square) that appears next to data needing attention. Appears only when the alert condition is met so it is perceived preattentively as an added mark. Multiple alert levels use intensity of a single hue, not different hues.

**Up/down icons.** Simple arrows or triangles indicating direction of change. Colors can support the meaning (using intensity-varied colors so colorblind users see the distinction).

**On/off icons.** Flags for items in a list (checkmarks, asterisks, Xs). Pick one shape and stick with it throughout the dashboard.

## Tables

Tables arrange text or other display media in columns and rows. Useful for:

- Lookup-oriented data where precise values matter
- Small-multiples layouts of related graphs
- Ranked lists
- Presenting several related measures with their current value, comparison, and sparkline

**Design rules for dashboard tables:**

- Right-justify numbers so digits align for comparison
- Use white space to separate columns and rows when possible
- Fall back to muted grid lines or alternating row fills only when density forces it
- Limit to data that genuinely benefits from tabular arrangement

## Small multiples

A tabular arrangement of the same chart repeated with one variable changing across instances. Ideal when too many variables would overcrowd a single chart.

**Example:** Revenue across four regions, split into bookings vs billings, split further into three sales channels. One chart cannot cleanly show all three dimensions. Three small bar graphs side by side (one per channel), each showing the four regions with bookings and billings, reveals everything at a glance.

**Design:** All small multiples share the same axes, scales, and chart type. Only one variable differs between them. Eliminate redundant labels (region labels, legends, titles) that would repeat identically across instances.

## Spatial maps

Use only when physical location is meaningful to the data. A geographic map for state-level data is useful when geography matters (shipping logistics, regional disease outbreaks). A map for a four-region sales breakdown is decorative.

A floor plan can be a useful spatial display when monitoring data tied to physical areas of a building (temperatures, security incidents, foot traffic).

## Drawing objects

For showing relationships between entities that are not quantitative comparisons. Process flows, organizational hierarchies, project dependencies.

Rectangles or circles represent entities. Lines connect them. Arrows add directionality. Quantitative information can be layered in through line thickness, rectangle size, or inline labels.

## Media to avoid

- Pie charts (use bar graphs for part-to-whole)
- Donut charts (same problems as pie charts, worse)
- Radar graphs (use bar graphs)
- Bubble charts that encode value as 2D area
- 3D bars, 3D pies, 3D anything (occlusion and perceptual error)
- Realistic gauges, speedometers, thermometers (bullet graphs replace these)
- Funnel charts unless a funnel is literally the subject
- Waterfall charts outside very specific financial contexts
- Word clouds on dashboards (imprecise, hard to scan)
- Heatmaps with more than about seven distinguishable cells (use treemaps for dense data)

## Summary table

| Data pattern | First choice | Avoid |
|---|---|---|
| Single key value vs target | Bullet graph | Radial gauge, thermometer |
| Single value, historical context | Value + sparkline | Trend arrow alone |
| Discrete categorical comparison | Bar graph | Pie chart, radar graph |
| Part-to-whole (single instance) | Bar graph | Pie chart |
| Part-to-whole (across instances, emphasis on whole) | Stacked bar | Multiple pie charts |
| Time series, shape matters | Line graph | Bar graph |
| Time series, individual values matter | Bar graph | Line graph |
| Correlation between two variables | Scatter plot with trend line | 3D scatter |
| Distribution across a range | Simplified box plot | Single median alone |
| Large hierarchical data, spotting conditions | Treemap | Nested pie charts |
| Mix of individual values and trend | Combination bar and line | Separate graphs apart |
| Same chart, many variants | Small multiples | Crowded single chart |
