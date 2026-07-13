# Veo / video3 Provider Notes

last_verified: 2026-06-21

Official source to check before changing runtime behavior:

- Google Gemini API video generation documentation: `https://ai.google.dev/gemini-api/docs/video`
- Google API pricing documentation for Veo/video models: `https://ai.google.dev/gemini-api/docs/pricing`
- Embedded Veo expert references under `../experts/veo_video/`, especially `references/source-registry.md`, `references/capability-map.md`, `references/prompt-guide.md`, and `references/workflow.md`

Use Veo when the user asks for Veo, video3, Google video generation, cinematic realism, strong semantic adherence, or high-quality native video output.

Runtime behavior:

- Text-to-video uses Gemini/Veo long-running video generation.
- Image-to-video forwards a starting image when present.
- Resolution and duration affect billing.
- Some model tiers expose different resolution, duration, audio, and latency limits. Do not assume one Veo model's limits apply to another.
- Google surfaces may expose different GA/preview endpoint ids. Verify current docs before changing `api_model` values.

Billing should follow Google official pricing dimensions: model tier, resolution, duration seconds, and provider usage when returned. The local fallback in `registry.py` stores per-second USD prices by resolution for Veo Standard/Fast/Lite style ids and converts them to Bahew billing units with `BILLING_CREDITS_PER_USD`; update those values whenever Google's pricing page changes.
