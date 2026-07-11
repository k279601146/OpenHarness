# Mermaid Diagram Guidance

Use Mermaid for standard structured diagrams.

Recommended diagram types:

- `flowchart` for flows, decision trees, pipelines, and state transitions.
- `sequenceDiagram` for time-ordered interactions.
- `erDiagram` for database relationships.

Rules:

- Keep node labels short and quoted when they contain punctuation.
- Avoid raw HTML labels.
- Do not rely on custom JavaScript, Mermaid init blocks, or unsafe directives.
- Prefer one diagram per artifact.

