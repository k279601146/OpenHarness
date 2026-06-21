# Kling / Keling Provider Notes

last_verified: 2026-06-21

Official source to check before changing runtime behavior:

- Kling AI / Kling Open Platform API documentation and model pricing pages: `https://app.klingai.com/global/dev/document-api`
- Embedded Kling expert references under `../experts/kling_video/`, especially `references/source-registry.md`, `references/capability-map.md`, `references/prompt-guide.md`, and `references/workflow.md`

Use Kling when the user asks for Kling, Keling, strong motion, action, product motion, image-to-video, or current front-end `keling-*` model choices.

Runtime behavior:

- Text-to-video uses the provider's text prompt task.
- Image-to-video forwards a first-frame image where supported.
- First/last-frame and reference modes are model/surface-specific; use dry-run to inspect the selected adapter payload before enabling new fields.
- Multi-shot, native audio, element references, and flexible duration are model/surface-specific; verify current docs before changing adapter fields.

Billing should follow Kling's official resource-unit dimensions when available: model version, mode, resolution, duration, output count, and audio/voice options. If provider usage is returned, prefer it over local estimates.
