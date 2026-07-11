# Inline Visual Output Contract

Emit inline visuals as an OpenHarness artifact payload when an artifact/event channel is available. If only normal assistant text is available, emit the fallback fenced `visual_message` JSON block.

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

Guidelines:

- Prefer a fenced `visual_message` JSON block for chat text output.
- `show_widget` is accepted as an equivalent fence language when the user or host names that protocol.
- If a host requires tag-style text wrappers, only use `<visual_message ...>...</visual_message>` or `<show_widget ...>...</show_widget>`.
- Do not write `<agent_artifact>` as assistant Markdown; `agent_artifact` is the internal event/payload name.
- Use `.html` for `render_kind: "html"`, `.svg` for `render_kind: "svg"`, and `.mmd` or `.mermaid` for Mermaid.
- Keep `name` concise, lowercase, and ASCII.
- Put the full renderable source in `content`.
- Include only necessary labels, values, and accessible text.
- Do not include implementation explanations inside the visual.

Assistant text fallback:

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

Fallback rules:

- Use `visual_message` or `show_widget` as the fence language exactly.
- Put only one JSON object in the fence.
- Do not use `format` instead of `render_kind`.
- Do not put explanatory prose inside the JSON.
