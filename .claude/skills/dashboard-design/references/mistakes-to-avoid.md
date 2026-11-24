# The Thirteen Common Dashboard Design Mistakes

Detailed treatment of each mistake, with explanation of why it fails and what to do instead. Based on Chapter 3 of Stephen Few's *Information Dashboard Design*.

## 1. Exceeding the boundaries of a single screen

A dashboard's defining feature is simultaneity of vision. Everything must be visible at once so the eye can scan, compare, and build an overview.

**Fragmenting data into separate screens.** If a banking executive needs to see deposits, loans, profitability, growth, and market share together to understand the business, splitting these onto ten tabs destroys the value. Each tab isolates a measure from its natural comparisons. Navigation to supporting detail is fine. Fragmentation of the core overview is not.

**Requiring scrolling.** Anything below the fold is effectively invisible. Users assume hidden content is less important and often never look. Short-term memory cannot bridge the gap between what is on screen and what has scrolled out of view.

**Fix.** Keep the overview on a single screen. Use small, compact display media (bullet graphs, sparklines, small multiples) to fit more. Push details to separate screens reached through drill-down, not to scrolled regions of the main view.

## 2. Supplying inadequate context for the data

A number alone is almost meaningless. "$736,502 QTD sales" is good or bad depending on target, history, forecast, and prior quarter. Without that frame, the viewer cannot act.

**Fix.** Pair every key measure with at least one meaningful comparison. Common choices include target or budget, same period last year, forecast, benchmark, or a short time series. Visually subdue the context so the primary measure dominates, but include enough to make the measure interpretable.

## 3. Displaying excessive detail or precision

Dashboards need high-level summaries. Numbers with four decimal places, timestamps to the second, or transaction-level granularity waste the viewer's time filtering out what matters.

**Fix.** Round to the level of precision that supports the decision. Executives rarely need below the nearest thousand or million. Only surface detail when the dashboard's role demands it (operational dashboards showing specific order numbers, for instance).

## 4. Choosing a deficient measure

The number displayed should directly answer the question the viewer has. If the question is "how far off target are we," displaying actual and target side by side forces the viewer to do math. Displaying variance as a percentage answers directly.

**Fix.** For each measure, identify the question it answers. Choose the expression that answers it most directly. Variance percentages, ratios, deltas, and indexed values often communicate faster than raw values.

## 5. Choosing inappropriate display media

Common failure modes:

**Pie charts.** Designed for part-to-whole data, but humans cannot accurately compare 2D areas or angles. A bar graph communicates the same information faster and more precisely. Avoid pie charts on dashboards without exception.

**Radar graphs.** A line graph bent into a circle. The circular arrangement makes values harder to read than a linear bar graph. The only justified use is when the categorical scale has natural circular meaning (like hours of the day).

**Bubble charts sizing by 2D area.** Viewers systematically underestimate area differences. A bubble nine times larger than another looks about three times larger.

**Maps.** Only use a geographic map when geography is meaningful to the data. A four-region sales breakdown does not need a map. Shipment data by state with tax implications might.

**Fix.** Default to bar graphs for nominal/ordinal comparisons, line graphs for time series, sparklines for dense historical context, bullet graphs instead of gauges, and treemaps for large hierarchical data where spotting conditions matters more than precise comparison.

## 6. Introducing meaningless variety

Varying chart types to avoid boredom forces the viewer to shift perceptual strategies across the screen. Consistency makes scanning fast.

**Fix.** Use the same chart type for the same kind of relationship everywhere on the dashboard. If six sections all show a measure against a target over time, all six should use the same chart type. Variety for its own sake is friction.

## 7. Using poorly designed display media

Even the right chart type fails with poor execution. Common problems:

**Legends when direct labels would work.** Forcing the eye to bounce between a chart and a legend is wasted effort. Label data directly when you can.

**Arbitrary ordering.** Sort bars by value unless another order (temporal, conventional, categorical) serves the purpose.

**Meaningless color variation.** If bars have unique labels, making each a different color adds nothing and attracts attention that should go to the data.

**3D effects.** Obscure values, cause occlusion, and add no information. Avoid 3D on dashboards essentially always.

**Odometer-style numerical displays.** Realistic car-dashboard number styling without commas makes numbers harder to read.

**Wrong bar adjacency.** When comparing actual to target across four regions, the actual and target bars for each region should be adjacent. Grouping all actuals together and all targets together defeats the comparison.

**Fix.** Design every chart to serve its specific comparison. Label directly. Order meaningfully. Use color only to encode meaning or highlight.

## 8. Encoding quantitative data inaccurately

Bar lengths encode values. A bar graph whose axis starts at $500,000 rather than $0 shows bars whose lengths do not correspond to their values, making comparisons misleading.

**Fix.** Bar graphs always start at zero. Line graphs can narrow the scale because line graphs encode values by position, not length.

## 9. Arranging the data poorly

Prime real estate is the upper-left and center of the screen. Placing a logo, navigation, or a minor measure there wastes it. Conversely, important data in the lower-right corner is easy to miss.

**Fix.** Rank measures by importance. Put the most important in the upper-left and center. Put navigation and selectors in less prominent positions (lower-right, edges). Ensure data that should be compared is placed close together.

## 10. Highlighting important data ineffectively or not at all

If everything on the screen is equally bold, colorful, and prominent, nothing stands out. The viewer has no guidance on where to look first.

**Fix.** Establish a visual hierarchy. Most important data gets the strongest treatment (location, size, or contrast). Secondary data recedes. Dynamic highlights (alerts, colored icons) appear only when data crosses a threshold. Avoid always-on traffic light icons because they waste the attention-grabbing mechanism on routine conditions.

## 11. Cluttering the display with useless decoration

Fake cockpits, spiral notebook bindings, decorative rivets, ornate logos, background images of maps with no data encoding, color gradients across panels: all of this competes with the data for attention. The novelty fades in days, then only the friction remains.

**Fix.** Remove every graphic element that does not encode data or support comprehension. Logos get small and subtle if they must appear at all. Backgrounds are a single muted color. No ornamentation.

## 12. Misusing or overusing color

Several common failures:

- Red/yellow/green traffic light schemes fail for colorblind users (about 10% of males, 1% of females).
- Too many bright colors create sensory overload.
- The same color used for unrelated things invites the viewer to falsely connect them.
- Bright color on every section means nothing gets emphasis.

**Fix.** Build a color palette with a small muted set for default use and a small bright set reserved for emphasis and alerts. Signal severity through intensity of a single hue rather than different hues. Combine color with shape or icons so information survives desaturation. Use the same color for the same meaning throughout the dashboard.

## 13. Designing an unattractive visual display

Ugly dashboards get avoided. The user's reluctance to look at a harsh, cluttered, or dreary screen is a real failure mode, not a cosmetic complaint.

**Fix.** Aesthetics on a dashboard come from restraint: consistent typography, clean alignment, muted palette, generous white space, high-resolution rendering, off-white background. Never add decoration to compensate for poor layout. Fix the layout.

## The meta-principle

These thirteen are not independent. They cluster around one idea: every pixel should serve communication, and anything that competes with the data for attention is a defect. A dashboard that avoids all thirteen mistakes tends to look spare, almost understated. That restraint is what makes dense information legible.
