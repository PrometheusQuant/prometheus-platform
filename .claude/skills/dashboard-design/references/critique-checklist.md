# Dashboard Critique Checklist

A structured pass for evaluating an existing dashboard. Walk through these in order. For each issue found, note what the problem is, why it hurts the user, and what a better solution looks like.

## Stage 1: Purpose and audience

Before critiquing visual choices, clarify intent. Many visual issues trace back to confusion about what the dashboard is supposed to do.

- Who is the intended user? What role, what level in the organization?
- Which of the three types is this: strategic, analytical, or operational?
- What decisions or actions should this dashboard support?
- What questions is the user trying to answer when they look at it?
- How often will they look at it? (Daily, throughout the day, weekly?)
- How much time do they have? (Ten seconds? Five minutes?)

If the dashboard's purpose is unclear or mismatched to the displayed content, that is the first issue to flag. No amount of visual polish fixes a dashboard that shows the wrong data for its users.

## Stage 2: Structural mistakes

These break the dashboard's fundamental contract. Check these first.

**Single-screen test.** Can the user see everything at once? No scrolling, no tabs that split related information across separate views?

**Signal-to-noise test.** Is most of the screen taken up by data, or by logos, borders, decoration, navigation chrome, instructions, and ornaments?

**Hierarchy test.** Is it obvious which measures are most important? If everything is equally bold and colorful, the hierarchy has failed.

**Prime real estate test.** Is the upper-left corner used for the most important data, or wasted on a logo, company name, or menu?

**Context test.** Do key measures have comparisons (target, history, forecast) or are they floating naked numbers?

## Stage 3: Chart-by-chart review

For each chart or display element on the dashboard, ask:

**Is the chart type right for this data?**

- Pie chart? Replace with bar graph.
- Radar graph? Replace with bar graph.
- 3D anything? Replace with flat equivalent.
- Radial gauge? Replace with bullet graph.
- Bubble sizes encoding value? Replace with bar graph.
- Line graph over a nominal/ordinal scale? Replace with bar graph.
- Bar graph for time series where shape matters? Consider line graph instead.
- Single-instance stacked bar? Replace with regular bar graph.

**Is the chart well-designed?**

- Does the bar graph axis start at zero?
- Are bars in a meaningful order (by value or by category logic)?
- Are data labels direct rather than requiring a legend lookup?
- Is color used with meaning, or arbitrarily?
- Are grid lines muted or absent rather than visually competing with the data?
- Is 3D being used for any reason? If yes, remove it.
- For bar comparisons (actual vs target), are the compared bars adjacent?

**Is the encoding accurate?**

- Do bar lengths accurately represent values (scale starts at zero)?
- Do sizes/areas correspond to actual value ratios?
- Is the message the chart conveys at first glance the truthful message?

## Stage 4: Color audit

Go through every color choice on the dashboard.

**Bright color inventory.** List every bright, saturated color used. Is each reserved for alerts or critical data? If bright colors appear on decorative backgrounds, routine data, or headings, they are diluting their signaling power.

**Colorblind check.** Imagine the screen in grayscale, or view it converted. Do red/green distinctions still communicate? If the only way to tell "good" from "bad" is hue, the design excludes colorblind users. Fix by using intensity variation or combining color with shape/icons.

**Meaning consistency.** Does the same color mean the same thing everywhere on the dashboard? If "yellow" means "satisfactory" in one area and "June" in another, viewers will connect them incorrectly.

**Palette discipline.** How many distinct hues are in use? More than six or seven suggests the palette has escaped control.

**Background check.** Is the background pure white (harsh) or busy (distracting)? A slightly off-white neutral is easier to look at.

## Stage 5: Layout and grouping

**Grouping logic.** Are related items close to each other? Are unrelated items separated? Does the grouping reflect how the user actually uses the information?

**Delineation style.** How are groups separated? By white space (ideal), by muted borders (acceptable when density forces it), or by heavy borders and fill colors (usually too much)?

**Reading order.** Is there a natural scanning sequence (left-to-right, top-to-bottom)? Are the most important measures in the regions of highest prominence?

**Comparison support.** Are measures that should be compared placed adjacent, encoded consistently, or linked by color? Conversely, are unrelated measures placed apart so viewers do not falsely compare them?

**Alignment.** Do elements line up cleanly on a grid? Misalignment creates visual noise even when nothing else is wrong.

## Stage 6: Decoration and chrome

List every element on the dashboard that does not encode data. For each:

- Does it support the dashboard's function (title, axis label, necessary instruction)?
- Could it be removed without loss?
- If it must stay, is it visually subdued so it does not compete with data?

Specific decorative patterns to flag:

- Photographic backgrounds
- Skeuomorphic gauges, dials, chrome, rivets, leather textures, etc.
- Color gradients across panels or backgrounds
- Drop shadows on charts or bars
- Ornate titles, decorative fonts
- Prominent company logos
- Navigation buttons taking up major real estate
- Instructions explaining how to use the dashboard (move to separate help, not main view)
- Photos of people

Each of these is a candidate for removal.

## Stage 7: Highlighting

**Always-important data.** Is it placed in prime locations? Given visually stronger treatment than secondary data?

**Threshold-important data.** Are alert indicators dynamic (appearing only when needed) or static (always there)? Static alerts waste attention on routine conditions.

**Over-highlighting.** Is so much data highlighted that the highlights have lost their meaning? If three-quarters of the dashboard is bold, red, or colored, nothing stands out.

## Stage 8: Overall aesthetics

After the specific checks, step back.

- Is this dashboard pleasant to look at?
- Would a user enjoy returning to it daily?
- Does it feel calm and professional, or busy and stressful?
- Does it look like the work of someone who respects the viewer's time and intelligence?

Aesthetics are not decoration. A dashboard users avoid is a failed dashboard, and ugly dashboards get avoided. The aesthetic solution is not to add ornament but to strengthen the discipline: cleaner type, more white space, less color, more alignment.

## Producing the critique

A useful critique does three things:

1. States the specific issue (what is wrong).
2. Explains why it hurts the user (why it matters).
3. Proposes the fix (what to do instead).

Avoid vague complaints. "The colors feel off" is not actionable. "Bright red is used on routine data, diluting its effectiveness as an alert color, which means actual alerts will fail to grab attention" is actionable.

Prioritize fixes by impact. Structural problems (single-screen violations, wrong chart types, missing context) matter more than polish problems (alignment, font choice). Fix the foundation before the finish.

When the critique is extensive, consider sketching a redesign rather than listing abstract fixes. Seeing the target state clarifies what the changes amount to.
