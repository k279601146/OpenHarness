# SVG Diagram Guidance

Use SVG for static custom visuals where geometry matters more than UI controls.

Rules:

- Include one root `<svg>` with a `viewBox`.
- Add `<title>` and `<desc>` for accessibility.
- Keep text readable and inside the viewBox.
- Use consistent stroke widths and spacing.
- Avoid embedded scripts, remote images, and foreignObject.

Use cases:

- Layered architecture diagrams.
- System maps.
- Custom process diagrams.
- Small custom charts where Mermaid is too limited.

