---
name: inline-visuals
description: Create safe inline visual messages for chat responses. Use whenever the user asks for diagrams, charts, UI wireframes, component breakdowns, architecture maps, flowcharts, sequence diagrams, ER diagrams, status cards, comparisons, or small interactive visuals, even if they do not explicitly ask for a visual.
metadata:
  display_name: Inline Visuals
  default_prompt: Use $inline-visuals to turn this explanation into a safe inline visual message.
---

# Inline Visuals

Use this skill to decide whether a response should include an inline visual message and to emit the chat-safe `show_widget` / `visual_message` protocol.

## When To Use

Use an inline visual only when it materially improves understanding, comparison, exploration, or user feedback.

Prefer this skill for:

- UI wireframes, page layouts, and component breakdowns
- Card structures, status panels, compare cards, and information summaries
- Flowcharts, decision trees, sequence diagrams, and ER diagrams
- System architecture diagrams, layered structures, and simplified charts
- Small local interactive widgets, such as sliders, toggles, and step-through explainers

Do not use this skill for raster image generation, PPT decks, PDF/PNG art objects, or full application pages unless the user explicitly asks for an inline visual preview.

## Output Contract

Emit inline visuals as a visualization artifact payload when an artifact/event channel is available. If only normal assistant text is available, emit the fallback fenced JSON block.

Required fields:

```json
{
  "type": "visualization",
  "schema_version": 1,
  "render_kind": "html | svg | mermaid",
  "visual_kind": "wireframe | component | flowchart | sequence | er | architecture | chart | card | interactive",
  "name": "short-ascii-name.html",
  "content": "renderable source"
}
```

Rules:

- Use `type: "visualization"` for inline visual payloads.
- Keep `schema_version` at `1`.
- Use `.html` for `render_kind: "html"`, `.svg` for `render_kind: "svg"`, and `.mmd` or `.mermaid` for Mermaid.
- Keep `name` concise, lowercase, and ASCII.
- Put the full renderable source in `content`.
- Include only necessary labels, values, and accessible text.
- Do not include implementation explanations inside the visual.

Allowed `visual_kind` values:

- `wireframe`
- `component`
- `flowchart`
- `sequence`
- `er`
- `architecture`
- `chart`
- `card`
- `interactive`

## Preferred Emission

### 1. Structured artifact event

When the runtime or host can emit real artifacts, prefer:

```json
{
  "type": "visualization",
  "schema_version": 1,
  "render_kind": "mermaid",
  "visual_kind": "flowchart",
  "name": "decision-tree.mmd",
  "content": "flowchart TD\n  A[Start] --> B[Done]"
}
```

`agent_artifact` is an event type and payload type, not assistant text.

### 2. Text fallback: fenced JSON

If only normal assistant text is available, use fenced JSON:

````markdown
```visual_message
{
  "type": "visualization",
  "schema_version": 1,
  "render_kind": "html",
  "visual_kind": "card",
  "name": "status-card.html",
  "content": "<div>...</div>"
}
```
````

`show_widget` is an equivalent fence language:

````markdown
```show_widget
{
  "type": "visualization",
  "schema_version": 1,
  "render_kind": "svg",
  "visual_kind": "architecture",
  "name": "system-architecture.svg",
  "content": "<svg>...</svg>"
}
```
````

### 3. Text fallback: controlled tags

Only when the host explicitly needs tag-style protocol, allow:

```html
<visual_message render_kind="html" visual_kind="component" name="ui-components.html">
<!doctype html>...
</visual_message>
```

or:

```html
<show_widget render_kind="svg" visual_kind="architecture" name="architecture.svg">
<svg>...</svg>
</show_widget>
```

Do not accept arbitrary new tag names. Do not parse `<agent_artifact>` as assistant Markdown.

## Format Choice

| Scenario | Preferred `render_kind` | Notes |
| --- | --- | --- |
| Standard flowchart, decision tree | `mermaid` | Use `flowchart` or `graph`. |
| Sequence diagram | `mermaid` | Use `sequenceDiagram`. |
| ER diagram | `mermaid` | Use `erDiagram`. |
| UI wireframe or component breakdown | `html` | Use HTML/CSS for a closer-to-real interface. |
| Information card, status card, compare card | `html` | Use static HTML cards. |
| Small interactive simulator | `html` | `visual_kind` must be `interactive`. |
| Custom architecture diagram or layered system | `svg` or `mermaid` | Prefer Mermaid when it fits; use SVG for complex layout. |
| Simple chart | `svg` or `html` | Use SVG/HTML when not introducing a chart library. |

## Design Guidance

Use this when creating HTML or SVG visuals. The goal is a compact explanation inside chat, not a landing page, poster, or full app screen.

### Intent

- Keep visuals clear enough to scan in 3-5 seconds.
- Keep them compact enough to sit naturally between chat paragraphs.
- Make them polished without decorative excess.
- Make them specific to the user's subject, not generic SaaS filler.

### Visual System

Start with a small token set:

- `--bg`: neutral surface, usually `#ffffff` or `#0a0a0a`
- `--panel`: secondary surface, usually `#f4f4f5` or `#18181b`
- `--text`: primary text, high contrast
- `--muted`: secondary text
- `--line`: border or connector color
- `--accent`: one purposeful accent from the subject matter

Avoid one-note palettes. Do not make the whole visual blue, purple, beige, or charcoal.

### Layout Rules

- Fit naturally in a chat card: target 520-760px wide, responsive down to 320px.
- Use stable dimensions: aspect ratio, fixed row heights, grid tracks, or min/max sizes.
- Prefer 2-4 clear regions over many small boxes.
- Use labels close to the thing they describe.
- Keep whitespace deliberate.
- Avoid nested cards. Use bands, rows, columns, or grouped nodes instead.

### Type Rules

- Use system fonts unless the visual is explicitly about typography.
- Keep type small and dense: 11-15px for most labels, 16-20px for one title.
- Use `font-weight: 600` for headings and key labels.
- Do not use negative letter spacing.
- Ensure long words, paths, or labels wrap or truncate cleanly.

### Components

For HTML visuals:

- Use semantic elements where practical.
- Use `button`, `input`, `select`, `checkbox`, and `range` controls for interactive widgets.
- Use `border-radius: 8px` for small controls and `12px` at most for larger panels.
- Include hover and focus states only when the widget is interactive.

For SVG visuals:

- Use consistent stroke widths, usually 1-1.5px.
- Use rounded corners sparingly: `rx="8"` or less for most nodes.
- Align nodes to a grid.
- Prefer simple arrows and connectors over decorative paths.
- Include a title and concise labels as text elements.

### Content Rules

- Use real labels from the user's request.
- Do not include instructions like "click here" inside the visual.
- Do not duplicate the surrounding answer.
- For architecture diagrams, show ownership and flow direction.
- For status cards, show state, progress, and the next relevant signal.
- For comparisons, make differences visible by position, not just color.

### Quality Check

Before emitting the visual:

1. Can the user understand the main point without reading the source code?
2. Does every color encode meaning or hierarchy?
3. Does the layout still work at 320px width?
4. Is there exactly one visual emphasis?
5. Is the output self-contained, with no external assets, network calls, storage, or secrets?

## HTML Rules

Use HTML when the answer benefits from layout, component structure, cards, UI wireframes, or local interactions.

- Produce a self-contained HTML document or fragment that works in a sandboxed iframe.
- Use inline CSS and local JavaScript only when needed.
- Keep layout responsive from 320px upward.
- Use restrained SaaS styling: neutral surfaces, clear hierarchy, compact controls, and no decorative gradients.
- Avoid external network resources unless the task explicitly requires them and the host policy allows them.
- Keep scripts local to the widget and presentation-only.

## SVG Rules

Use SVG for static custom visuals where geometry matters more than UI controls.

- Include one root `<svg>` with a `viewBox`.
- Add `<title>` and `<desc>` for accessibility.
- Keep text readable and inside the viewBox.
- Use consistent stroke widths and spacing.
- Avoid embedded scripts, remote images, and `foreignObject`.

## Interactive Widget Rules

Use interactive HTML only when changing inputs helps the user understand or decide.

- Keep all state local to the iframe.
- Use native buttons, inputs, selects, checkboxes, and range sliders.
- Make the initial render useful before any interaction.
- Do not call external APIs or store data.
- Keep controls compact and directly tied to the visual.

## Mermaid Rules

Use Mermaid for standard structured diagrams.

Recommended diagram types:

- `flowchart` for flows, decision trees, pipelines, and state transitions
- `sequenceDiagram` for time-ordered interactions
- `erDiagram` for database relationships

Rules:

- Keep node labels short and quoted when they contain punctuation.
- Avoid raw HTML labels.
- Do not rely on custom JavaScript, Mermaid init blocks, or unsafe directives.
- Prefer one diagram per artifact.
- Use the local `mermaid` dependency, not a CDN.
- Use `securityLevel: "strict"`.
- Use `startOnLoad: false`.
- Use a stable render id.

## Safety Rules

- Keep visuals self-contained and under 2 MB.
- Do not use `fetch`, XHR, WebSocket, cookies, localStorage, sessionStorage, external secrets, account tokens, or hidden network calls.
- Do not reveal internal file paths, sandbox paths, API keys, tokens, cookies, or raw tool output.
- Do not depend on external fonts, images, CSS, or JS.
- Do not embed raw HTML or SVG directly in Markdown outside the protocol.
- Do not use base64 HTML data URLs.

## Skill Responsibilities

`inline-visuals` is a thin routing skill, not a full visualizer:

- Decide whether the answer should become an inline visual.
- Choose `html`, `svg`, or `mermaid`.
- Follow the output contract above.
- Do not merge, rename, or rewrite other skills to solve visual confusion.

## Compatibility

Compatibility is protocol compatibility, not historical-test compatibility:

- Accept `visual_message` and `show_widget`.
- Accept snake_case and camelCase field variants when needed, such as `render_kind` and `renderKind`.
- Infer render kind from `.svg`, `.mmd`, and `.mermaid` when appropriate.
- Do not add compatibility for `<agent_artifact>` text wrappers, HTML entity test output, or arbitrary legacy wrappers.

If you think you need a new compatibility path, first ask:

1. Is this a real protocol or test residue?
2. Does it widen XSS or arbitrary HTML rendering?
3. Does it blur internal events and text protocols?
4. Has the skill doc, renderer, and tests been updated together?


