# Visual design standard

All current and future project visualizations should follow the shared theme in
src/ecommerce_customer_intelligence/analytics/theme.py. Framework-neutral design
tokens are exported to docs/visual_theme.json for future interactive components.

## Visual language

Use a white canvas, dark ink, muted slate labels, teal primary data, and light teal
context. Amber highlights a measured result or partial observation; muted red
represents deductions. Do not use rainbow palettes, 3D, heavy borders, or decorative
backgrounds. Segoe UI is preferred, with DejaVu Sans as a portable fallback.

Use a consistent header, descriptive business title, concise scope subtitle, generous
plot spacing, and a methodological footnote where needed. Counts use thousands
separators; money uses £ with K/M abbreviations; percentages include %. Wrap long
ranking labels instead of truncating them. Display rounding never changes source data.

## Analytical chart choice

- Revenue and order trends: line/area charts with partial periods shaded and labeled.
- Country, product and segment rankings: horizontal bars with readable labels and direct values.
- Customer share versus revenue share: paired dots connected by a line.
- Revenue reconciliation: signed waterfall with explicit deductions.
- Retention: annotated sequential teal heatmap, partial cells marked P, future cells blank.
- Concentration: cumulative curve with the actual 80% crossing.
- Value distribution: logarithmic monetary axis with a median reference.
- Frequency distribution: observed-frequency dots, with log scales clearly disclosed.
- Recency/value: neutral context with selected risk segments highlighted using limited colors and distinct markers.
- New/returning activity: two-series comparative time plot.

Annotations must derive from calculated outputs. Do not remove outliers, alter values,
or treat unavailable periods as zero to improve a chart.

## Rendering and validation

Run from the project root using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe scripts/render_figures.py
```

This reads existing analytical CSVs and KPI JSON files and replaces only the figure
exports. It does not rerun cleaning or KPI calculations. Every figure is saved as a
300-DPI PNG and an editable SVG using tight bounds. The renderer records input SHA-256
checksums in reports/metrics/visualization_integrity.json.

Inspect the exports at presentation size for overlapping titles, labels, legends, clipped
annotations, incorrect units, and misleading scales. Reuse the theme helpers and tokens
for new figures; avoid individual chart-specific style resets.

## Future dashboard direction

The eventual Streamlit interface should use these tokens as a coherent product system:
clear navigation, a restrained KPI hierarchy, consistent filter placement and spacing,
explicit time coverage, and scope definitions beside metrics. Charts should answer
business questions with focused annotations and accessible labels, not reproduce a
notebook cell sequence. No dashboard is implemented in this change.
