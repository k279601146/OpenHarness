# Kling Source Registry

last_verified: 2026-06-21

Use these sources before changing runtime behavior, pricing, model ids, or capability claims:

- Kling Open Platform API documentation: `https://kling.ai/document-api/apiReference/commonInfo`
- Kling Open Platform image-to-video API documentation: `https://kling.ai/document-api/apiReference/model/imageToVideo`
- Kling Open Platform product overview: `https://kling.ai/document-api/quickStart/productIntroduction/overview`
- Kling VIDEO 3.0 model user guide: `https://kling.ai/quickstart/klingai-video-3-model-user-guide`

## Current Source-Gated Facts

- Kling official docs describe Kling 3.0 and 3.0 Omni as supporting synchronized audio-video generation, intelligent storyboarding, and element references.
- Kling VIDEO 3.0 supports text-to-video, image-to-video, start/end frames-to-video, native audio, multi-shot, start frame plus element reference, multi-character coreference, multilingual support, dialects/accents, 15-second output duration, and flexible duration.
- Kling official guidance says VIDEO 3.0 can generate up to 15 seconds, with flexible duration from 3 to 15 seconds.
- Kling 3.0 multi-shot can automatically plan shot transitions, framing, and camera angle changes; custom multi-shot can specify shot details and durations.
- Kling 3.0 audio guidance emphasizes assigning which character speaks, supports Chinese, English, Japanese, Korean, Spanish, dialect/accent rendering, and code-switching.

## Local Runtime Notes

Bahew model aliases are resolved in `scripts/videogen_runtime/registry.py`. The expert reference should guide prompt craft and source checks; changing endpoint ids, billing, or adapter payloads belongs in runtime code and tests.
