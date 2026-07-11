# Interactive Widget Guidance

Use interactive HTML only when changing inputs helps the user understand or decide.

Rules:

- Keep all state local to the iframe.
- Use native buttons, inputs, selects, checkboxes, and range sliders.
- Make the initial render useful before any interaction.
- Do not call external APIs or store data.
- Keep controls compact and directly tied to the visual.

Use cases:

- Simulators.
- Adjustable comparisons.
- Step-through explainers.
- Small local calculators with transparent assumptions.

