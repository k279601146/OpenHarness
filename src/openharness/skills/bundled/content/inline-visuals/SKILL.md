---
name: inline-visuals
description: Create safe inline visual messages for Bahew chat responses. Use this skill whenever the user asks for visual or interactive content in the conversation, including diagrams, charts, UI wireframes, component breakdowns, architecture maps, flowcharts, sequence diagrams, ER diagrams, compact visual cards, simulators, or any answer that would be clearer as a structured HTML, SVG, or Mermaid visualization instead of plain text. Prefer this skill for chat-embedded visuals; do not use it for raster image generation, PPT decks, PDF/PNG art objects, or full application pages unless the user explicitly asks for an inline visual preview.
---

# Inline Visuals

Use this skill to decide whether a response should include an inline visual message and to emit the Bahew `show_widget` / `visual_message` artifact protocol.

## Decision Flow

1. Use a visual only when it materially improves understanding, comparison, exploration, or user feedback.
2. Keep the normal prose concise. Let the visual carry structure; do not duplicate it in paragraphs.
3. Choose the smallest render format that fits:
   - Mermaid for standard flowcharts, sequence diagrams, decision trees, and ER diagrams.
   - SVG for static custom architecture diagrams, layered systems, precise charts, and diagrams Mermaid cannot express cleanly.
   - HTML for UI wireframes, component breakdowns, visual cards, and interactive widgets.
4. Prefer emitting one structured `agent_artifact` event/payload with `type: "visualization"` and the protocol fields from `references/output-contract.md` when the host provides an artifact/event channel.
5. If only normal assistant text is available, emit exactly one fenced `visual_message` JSON block using the fallback format in `references/output-contract.md`.
6. Do not write `<agent_artifact>` as prose or Markdown. That name is an internal event type, not a chat text wrapper.
7. Do not embed raw HTML or SVG directly in Markdown outside the visual protocol.

## Reference Routing

- Read `references/output-contract.md` before emitting any inline visual artifact.
- Read `references/design.md` before creating HTML or SVG visuals, especially UI wireframes, cards, component breakdowns, architecture diagrams, and custom charts.
- Read `references/mermaid-diagram.md` for Mermaid flowcharts, sequence diagrams, decision trees, and ER diagrams.
- Read `references/svg-diagram.md` for hand-authored SVG diagrams or charts.
- Read `references/html-widget.md` for UI wireframes, visual cards, component layouts, and non-interactive HTML visuals.
- Read `references/interactive-widget.md` for local-only interactive HTML widgets.

## Safety Rules

- Keep visuals self-contained and under 2 MB.
- Do not use `fetch`, XHR, WebSocket, cookies, localStorage, external secrets, account tokens, or hidden network calls.
- Do not reveal internal file paths, sandbox paths, API keys, tokens, cookies, or raw tool output.
- Keep scripts local to the widget and presentation-only. If follow-up work is needed, ask in normal chat instead of making network calls.
- Prefer native HTML controls for interactivity.
