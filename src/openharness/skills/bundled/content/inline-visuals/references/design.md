# Inline Visual Design Guidance

Use this reference when creating `html` or `svg` inline visuals. The goal is a compact visual explanation inside a chat message, not a landing page, marketing hero, poster, or full app screen.

## Design Intent

Inline visuals should feel like precise product UI artifacts:

- Clear enough to scan in 3-5 seconds.
- Compact enough to sit naturally between chat paragraphs.
- Polished without decorative excess.
- Specific to the user's subject, not a generic SaaS template.

Spend visual personality in one controlled place: a distinctive structure, one accent color, a meaningful icon system, or a domain-specific layout metaphor. Keep the rest quiet.

## Format Guidance

- Use `html` for UI wireframes, cards, component breakdowns, comparisons, and interactive widgets.
- Use `svg` for custom architecture diagrams, layered systems, charts, and precise static diagrams.
- Use `mermaid` for standard flowcharts, sequence diagrams, and ER diagrams; do not force Mermaid into a custom visual style.

## Visual System

Start every HTML/SVG visual with a tiny token set:

- `--bg`: neutral surface, usually `#ffffff` or `#0a0a0a`.
- `--panel`: secondary surface, usually `#f4f4f5` or `#18181b`.
- `--text`: primary text, high contrast.
- `--muted`: secondary text.
- `--line`: border or connector color.
- `--accent`: one purposeful accent, chosen from the subject matter.

Avoid one-note palettes. Do not make the whole visual blue, purple, beige, or charcoal. Use zinc-like neutrals for structure and reserve color for meaning.

## Layout Rules

- Fit naturally in a chat card: target 520-760px wide, responsive down to 320px.
- Use stable dimensions: aspect ratio, fixed row heights, grid tracks, or min/max sizes.
- Prefer 2-4 clear regions over many small boxes.
- Use labels close to the thing they describe.
- Keep whitespace deliberate; do not fill every corner.
- Avoid nested cards. Use bands, rows, columns, or grouped nodes instead.

## Type Rules

- Use system fonts unless the visual is explicitly about typography.
- Keep type small and dense: 11-15px for most labels, 16-20px for one title.
- Use `font-weight: 600` for headings and key labels; avoid heavy bold everywhere.
- Do not use negative letter spacing.
- Ensure long words, paths, or labels wrap or truncate cleanly.

## Components

For HTML visuals:

- Use real semantic elements where practical.
- Use `button`, `input`, `select`, `checkbox`, and `range` controls for interactive widgets.
- Use `border-radius: 8px` for small controls and `12px` at most for larger panels.
- Include hover/focus states only when the widget is interactive.

For SVG visuals:

- Use consistent stroke widths, usually 1-1.5px.
- Use rounded corners sparingly: `rx="8"` or less for most nodes.
- Align nodes to a grid; avoid hand-wavy placement.
- Prefer simple arrows and connectors over decorative paths.
- Include a title and concise labels as text elements.

## Content Rules

- Use real labels from the user's request.
- Do not include instructions like "click here to use this visual" inside the visual.
- Do not duplicate the surrounding answer. The visual should add structure, not repeat paragraphs.
- For architecture diagrams, show ownership and flow direction.
- For status cards, show state, progress, and the next relevant signal.
- For comparisons, make differences visible by position, not just color.

## Quality Check

Before emitting the visual:

1. Can the user understand the main point without reading the source code?
2. Does every color encode meaning or hierarchy?
3. Does the layout still work at 320px width?
4. Is there exactly one visual emphasis?
5. Is the output self-contained, with no external assets, network calls, storage, or secrets?
