---
name: veo-video
description: "Use this embedded expert reference when planning, prompting, improving, or troubleshooting Google Veo / video3 video generation through OpenHarness videogen, including text-to-video, image-to-video, first/last-frame, reference-image direction, extension planning, cinematic realism, native audio, dialogue, prompt structure, model-id caveats, and API/source-status checks. Not for Seedance, Kling/keling, Sora, Runway Gen, or image-only prompting."
license: MIT
user-invocable: true
tags: [veo, video3, video-generation]
metadata:
  version: "1.0.0"
---

# veo-video

Veo operating guide for OpenHarness video work. Use this root reference to route facts, design prompts around current Veo strengths, and keep generation requests compatible with the unified `videogen_cli` runtime.

## OpenHarness Runtime

In OpenHarness SaaS, this is an embedded Veo expert reference inside `videogen`. Real video generation must call the unified `videogen_cli` tool with a Veo/video3 model id such as `veo-3.1`, `veo-3.1-fast`, `veo-3.1-lite`, or a `video3*` alias. Do not call legacy video tools such as `gen_creative_video`, `animate_first_frame`, `video_interpolation`, or `video_with_reference`.

## Operating Loop

1. Intake: identify the user's production goal, target surface, model id, mode, duration, aspect ratio, resolution, references, audio/dialogue needs, delivery target, and safety/IP risks.
2. Source gate: before making model, endpoint, pricing, duration, resolution, or feature claims, load `[ref:source-registry]` and `[ref:workflow]`.
3. Capability gate: load `[ref:capability-map]` before choosing one-shot, first/last-frame, image-to-video, reference-image, or extension strategy.
4. Mode gate: choose T2V, I2V, FLF2V, reference-image direction, or extension planning before writing prompt prose. Keep extension behavior source-gated because API support and model ids have changed.
5. Prompt build: load `[ref:prompt-guide]`; describe subject, action, scene, camera angle/move, lens/optics, lighting, temporal behavior, style, and audio as concrete production decisions.
6. Reference map: assign each image one role: starting frame, ending frame, subject identity, product/object, environment, or style cue. State what must not transfer.
7. Quality pass: check one dominant visible action, one camera move, physical light, audio intent, aspect-ratio framing, and negative prompt terms if supported by the active surface.
8. Repair loop: when a take returns, use `[ref:troubleshooting]`; change one variable per retry and record observed failures before rewriting.

## Load Map

| Situation | Load |
|---|---|
| API, model ids, endpoint lifecycle, pricing, or source freshness | `[ref:source-registry]`, `[ref:workflow]` |
| Selecting mode, duration, aspect ratio, resolution, references, or audio | `[ref:capability-map]` |
| Writing or compressing a production prompt | `[ref:prompt-guide]` |
| Image-to-video, first/last-frame, reference-image direction, or extension | `[ref:workflow]`, `[ref:capability-map]` |
| Dialogue, ambience, SFX, narration, or lip-sync | `[ref:prompt-guide]`, `[ref:capability-map]` |
| Bad result, blocked prompt, drift, bad audio, weak realism, or wrong framing | `[ref:troubleshooting]` |
| Need a starting template | `examples/golden-prompts/` |

## Prompt Contract

Keep final Veo prompts compact but explicit:

- camera and framing first;
- stable subject identity or reference role;
- one observable action with an endpoint;
- scene context and physical lighting;
- temporal pacing inside the clip length;
- audio in a separate sentence when audio matters;
- negative prompt as a separate field when the active surface supports it.

Never convert third-party or field-observed Veo tricks into official guarantees. If a claim affects runtime behavior, verify it against current Google documentation before changing code.
