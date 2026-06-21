# Seedance Provider Notes

last_verified: 2026-06-21

Official source families to check before changing runtime behavior:

- BytePlus ModelArk Seedance documentation: `https://docs.byteplus.com/en/docs/ModelArk/`
- Volcengine Ark Seedance documentation: `https://www.volcengine.com/docs/`
- Embedded Seedance expert references under `../experts/seedance_video/`, especially `references/api-workflow.md`, `references/model-name-map.md`, and platform/source status files

Use Seedance when the user asks for Seedance, Doubao video, ByteDance/Dreamina video, strong motion, Chinese-market video generation, first/last-frame transitions, or multi-reference work.

Runtime behavior:

- Text-to-video maps to a Seedance task payload with text content.
- Image-to-video uses image content with `first_frame`.
- First/last-frame uses `first_frame` and `last_frame` roles.
- Reference-to-video uses `reference_image` roles.
- `generate_audio` is forwarded when supported by the selected surface.

Billing should follow official Seedance provider usage when returned. Otherwise estimate from model, command/input type, duration, resolution, and output count; keep this estimate conservative and visible in metadata.
