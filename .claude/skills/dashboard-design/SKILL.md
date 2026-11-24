---
name: dashboard-design
description: Apply Stephen Few's dashboard design principles when designing, critiquing, or improving any single-screen information display, analytics UI, admin panel, executive overview, operational monitoring screen, KPI display, reporting view, or data-dense interface. Use whenever the task involves arranging multiple measures, metrics, or data points in a limited screen space so a user can monitor them at a glance. Trigger even when the word "dashboard" is absent if the work is clearly about a monitoring or overview screen (e.g. "admin home", "sales overview page", "ops console", "metrics screen", "analytics view", "KPI summary"). Also use for critiquing existing dashboards, choosing between chart types for a dashboard context, deciding layout of measures, or selecting display media like gauges, bullet graphs, sparklines, bar graphs, or scorecards.
---

# Dashboard Design

A dashboard is a visual display of the most important information needed to achieve one or more objectives, consolidated and arranged on a single screen so the information can be monitored at a glance. This skill codifies Stephen Few's principles from *Information Dashboard Design* for making that work.

The fundamental challenge is squeezing a great deal of often disparate information into a small amount of space while preserving clarity. Every design decision should serve communication. If something on the screen does not help the viewer understand what is happening and what needs attention, it should be cut.

## When this skill applies

Use this skill whenever designing or critiquing a single-screen monitoring display. This includes executive overviews, sales dashboards, CIO/operations consoles, call center monitoring screens, analytics landing pages, KPI scorecards, admin home screens, and similar surfaces. The user may not use the word "dashboard" — watch for any screen where multiple related measures need to be seen together at a glance.

This skill does not apply to:
- Detailed reports that support lookup of precise values (tables are fine there)
- Deep-dive analytical tools where users spend extended time exploring one dataset
- Standard transactional UI screens (forms, settings, lists without monitoring intent)

## The three dashboard types

Design characteristics shift based on the dashboard's role. Identify which type the user needs before making design choices.

**Strategic dashboards** support decision-makers who monitor health and opportunities. They use high-level measures with light context (targets, brief history, simple good/bad evaluators). Static snapshots (daily, weekly, monthly) are fine. Keep display mechanisms extremely simple. Interaction is minimal because strategic users rarely drill in themselves.

**Analytical dashboards** support analysts investigating causes. These need richer context: more history, subtler comparisons, more sophisticated display media. They still monitor at a glance but should link seamlessly to tools for deeper investigation. Static snapshots are fine because analysis does not require real-time data.

**Operational dashboards** support people responding to events as they happen. Real-time or near real-time updates matter here. Alert mechanisms must grab attention immediately when thresholds are crossed. Detail levels can be deeper because responders need specifics (order numbers, locations, responsible parties). Interaction (drill-down, hover) is common.

## Core principle: data-pixel ratio

Every pixel on a dashboard falls into one of two categories. Data pixels encode the actual information. Non-data pixels are everything else: borders, grid lines, fill colors, gradients, decorative graphics, logos, 3D effects, ornate frames, navigation chrome.

The visual design process reduces to two sequential goals:

1. Reduce non-data pixels. First eliminate any that are unnecessary. Then de-emphasize and regularize the ones that remain.
2. Enhance data pixels. First eliminate unnecessary data (summarize, show exceptions rather than all values). Then highlight what matters most.

When in doubt, remove it. White space alone handles most grouping and delineation needs. Only reach for borders, fill colors, or grid lines when white space is genuinely insufficient, and when doing so, keep them muted (thin, light gray).

## The thirteen mistakes to avoid

These are the design failures that undermine most dashboards. Reference `references/mistakes-to-avoid.md` for detailed discussion and examples of each. The short list:

1. Exceeding the boundaries of a single screen (fragmenting data across screens, requiring scrolling)
2. Supplying inadequate context for the data (values without targets, history, or comparison)
3. Displaying excessive detail or precision
4. Choosing a deficient measure (raw values when the message is variance)
5. Choosing inappropriate display media (pie charts, radar graphs, bubble sizes)
6. Introducing meaningless variety (different chart types for no reason)
7. Using poorly designed display media (3D bars, random bar colors, legends where direct labels would work)
8. Encoding quantitative data inaccurately (bar graph axes not starting at zero)
9. Arranging the data poorly (important data in low-value screen positions)
10. Highlighting important data ineffectively or not at all
11. Cluttering the display with useless decoration (fake cockpits, spiral bindings, logos in prime real estate)
12. Misusing or overusing color (traffic light red/green fails for colorblind users)
13. Designing an unattractive visual display

## Selecting display media

Start with a question: does this data need text, graphics, or both? Text is precise but processed serially. It wins when the user needs to look up a specific value, or when a single measure stands alone. Graphics win when shape, pattern, trend, or comparison matters. Most dashboards need both.

For graphical encoding of quantitative data on dashboards, stick to this library:

**Bullet graphs** — the best replacement for gauges and meters. A single bar encoded with a comparative marker (typically a target) against qualitative range bands (bad/satisfactory/good). Linear, compact, supports multiple comparisons. Always use this instead of radial gauges.

**Bar graphs** — the workhorse for comparing discrete values across a nominal or ordinal category (regions, departments, products). Also the right choice for part-to-whole data (never use pie charts). Quantitative scale must start at zero.

**Line graphs** — for time series and other interval scales where the shape of change matters. Scale does not need to start at zero.

**Sparklines** — tiny inline line graphs for historical context next to a current value. Ideal for dashboards because of density.

**Stacked bar graphs** — only when showing multiple instances of a whole and its parts with emphasis on the whole. Never for a single part-to-whole breakdown.

**Combination bar and line graphs** — when some series are best as bars (individual values matter) and some as lines (trend matters), shown together.

**Scatter plots** — for showing correlation between two paired quantitative variables.

**Box plots** — for showing distribution across a range. Use a simplified version for dashboards, not the full statistician's box-and-whiskers.

**Treemaps** — for large hierarchically or categorically structured data when the goal is spotting conditions of interest (not precise comparison). Rectangle size encodes one variable, color can encode a second.

**Avoid entirely on dashboards:** pie charts, radar graphs, 3D anything, bubble charts that use 2D area to encode values, speedometer-style realistic gauges, donut charts, funnel charts unless the funnel metaphor is literally the point.

Reference `references/display-media.md` for detailed guidance on each, including the bullet graph specification.

## Context enriches measures

A raw number without context tells almost nothing. "Quarter-to-date sales: $736,502" begs a dozen questions. The useful comparisons to consider:

- Same measure at the same point in a prior period (last year, last quarter)
- Target or budget for this period
- Relationship to a future target (percentage of quarter budget so far)
- Forecast or prior prediction
- Norm, benchmark, or competitor value
- Related measure (order count next to order revenue)
- Short time series

Pick the comparisons that answer the viewer's actual questions. Avoid piling on so many comparisons that the primary value gets buried. Visually subdue the context and let the primary measure stand out.

## Layout and organization

Screen position is one of the strongest tools available. The upper-left and center get the most attention by default. Never waste the upper-left on a logo, navigation, or a decorative title. Put the most important measures there.

Group data by business function, entity, or use case. Co-locate items that belong together so they can be compared. Separate items that should not be compared. Delineate groups with the least visible means possible — white space first, then thin muted borders only if space forces it.

Maintain consistency. If two graphs serve similar purposes, use the same chart type and the same visual treatment. Arbitrary variety makes viewers hunt for meaning that is not there.

## Color discipline

Color is the single most abused element in dashboards. Rules that hold almost always:

- Reserve bright, saturated colors for data that needs attention. Everything else uses muted, nature-inspired tones (soft grays, browns, blues, greens).
- Differences in color must mean something. If bars are different colors with no encoding purpose, make them the same color.
- Never rely on red/green alone to signal good/bad. Roughly 10% of males and 1% of females are colorblind. Use intensity variations of a single hue, or combine color with added marks (icons, boldface).
- Background should be slightly off-white, not pure white, to reduce harsh contrast.
- Limit the total number of distinct hues. Short-term memory cannot hold more than about nine meanings at once, and dashboards look cluttered well before that.

## Highlighting what matters

Static highlighting (location, size, weight) works for data that is always important. Dynamic highlighting (color change, added icon, blink) works for data that becomes important only when a threshold is crossed.

The most effective dynamic highlight is often the simplest: a small colored symbol that appears next to a value only when attention is needed. Because it is an added mark, it is perceived preattentively. A traffic-light scheme with green dots always present wastes attention — only show the alert when there is something to alert about.

Vary intensity of a single hue rather than using different hues to signal severity levels. This keeps colorblind users included.

## Interaction as a launch pad

A dashboard rarely contains everything a user needs to act. It provides the overview that tells them where to look next. Design it as a launch pad: clicking a value, bar, or region should open the supporting detail view. Keep launch actions consistent across the dashboard so viewers learn the pattern once.

Hover tooltips are ideal for showing precise values on top of a graph without cluttering the default view.

## Usability and aesthetics

An ugly dashboard gets avoided. That is a functional problem, not just a taste one. Aesthetic quality comes from discipline rather than decoration:

- Legible typeface, consistent throughout
- High resolution, crisp rendering
- Subdued color palette with selective emphasis
- Strong alignment and consistent spacing
- Minimal ornament, generous white space

Never try to make a dashboard look like a car dashboard, airplane cockpit, control panel, or notebook. These metaphors waste space and grow tiresome within days.

## Workflow for designing a new dashboard

When designing from scratch:

1. Identify the dashboard type (strategic, analytical, operational) and the specific user role.
2. List every measure that belongs on the screen. For each, decide: what level of summarization, what unit, what comparisons provide context, how important relative to other measures, what display medium suits it.
3. Rank measures by importance to the user's workflow.
4. Sketch a layout putting the most important measures in the upper-left and center. Group related measures. Plan for left-to-right, top-to-bottom reading order.
5. Choose display media from the library above. Default to bullet graphs over gauges, bar graphs over pie charts, sparklines for history.
6. Draft with minimal non-data pixels. White space for grouping. Muted colors. Off-white background.
7. Add alerts only for data that needs attention when something is wrong.
8. Review against the thirteen mistakes list.
9. Test with real data and real users. The design that survives real data and real use is the right one.

## Workflow for critiquing an existing dashboard

When asked to critique or improve:

1. Identify the dashboard type and intended user. If unclear, ask.
2. Walk through the thirteen mistakes systematically. See `references/critique-checklist.md` for a structured pass.
3. For each problem identified, state what the issue is, why it hurts communication, and what would work better.
4. Prioritize fixes. Layout and mistake correction usually matter more than polish.
5. If producing a redesign, sketch the replacement. Do not just describe improvements abstractly.

## Reference files

- `references/mistakes-to-avoid.md` — detailed treatment of the thirteen design mistakes with examples of what goes wrong and what to do instead
- `references/display-media.md` — full library of dashboard display media with selection guidance, including the bullet graph specification
- `references/visual-perception.md` — preattentive attributes, Gestalt principles, short-term memory limits, and how each applies to dashboard design
- `references/critique-checklist.md` — structured walkthrough for evaluating an existing dashboard

Pull these in when the task needs the detail. For a quick layout or chart-type decision, the principles in this SKILL.md are usually enough.
