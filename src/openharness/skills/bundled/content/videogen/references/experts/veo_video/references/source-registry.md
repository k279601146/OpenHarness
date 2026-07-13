# Veo Source Registry

last_verified: 2026-06-21

Use these sources before changing runtime behavior, pricing, model ids, or capability claims:

- Google Gemini API Veo video generation: `https://ai.google.dev/gemini-api/docs/video`
- Google Cloud / Gemini Enterprise Veo 3.1 model specs: `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate`
- Google Cloud Veo prompt guide: `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/video-gen-prompt-guide`
- Google DeepMind Veo overview: `https://deepmind.google/models/veo/`
- Google AI pricing: `https://ai.google.dev/gemini-api/docs/pricing`

## Current Source-Gated Facts

- Gemini API docs describe Veo 3.1 as generating high-fidelity 8-second videos at 720p, 1080p, or 4k with native audio.
- Gemini API docs list portrait and landscape aspect ratios, video extension for previously generated Veo videos, first/last-frame generation, and up to three reference images for image-based direction.
- Google Cloud model specs list 4, 6, or 8 second video lengths, up to four outputs per prompt, 9:16 and 16:9 aspect ratios, 24 FPS MP4 output, and per-model capability differences.
- Google Cloud docs show GA endpoint ids such as `veo-3.1-generate-001` and `veo-3.1-fast-generate-001`, and warn that older preview endpoint ids are discontinued or scheduled for removal. Treat local `*-preview` ids as implementation details that need verification before runtime changes.
- Prompt language and usage type can differ by platform, model tier, and launch stage. Do not assume Gemini API and Google Cloud surfaces expose identical behavior.

## Local Runtime Notes

Bahew model aliases are resolved in `scripts/videogen_runtime/registry.py`. The expert reference should guide prompt craft and source checks; changing endpoint ids, billing, or adapter payloads belongs in runtime code and tests.
