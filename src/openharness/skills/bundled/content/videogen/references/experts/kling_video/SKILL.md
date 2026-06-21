---
name: kling-video
description: "Use this embedded expert reference when planning, prompting, improving, or troubleshooting Kling / Keling video generation through OpenHarness videogen, including Kling 3.0, Kling 3.0 Omni, Kling 2.6, text-to-video, image-to-video, start/end frames, element references, multi-shot narratives, native audio, multilingual dialogue, product/action motion, model-id caveats, and API/source-status checks. Not for Seedance, Veo/video3, Sora, Runway Gen, or image-only prompting."
license: MIT
user-invocable: true
tags: [kling, keling, video-generation]
metadata:
  version: "1.0.0"
---

# kling-video

Kling/Keling operating guide for OpenHarness video work. Use this root reference to route facts, plan around Kling motion and multi-shot strengths, and keep generation requests compatible with the unified `videogen_cli` runtime.

## OpenHarness Runtime

In OpenHarness SaaS, this is an embedded Kling expert reference inside `videogen`. Real video generation must call the unified `videogen_cli` tool with a Kling/keling model id such as `kling-3.0`, `kling-3.0-omni`, `kling-2.6`, or a `keling-*` alias. Do not call legacy video tools such as `gen_creative_video`, `animate_first_frame`, `video_interpolation`, or `video_with_reference`.

## Operating Loop

1. Intake: identify target model, mode, duration, aspect ratio, resolution, references, element/character consistency needs, audio/dialogue language, delivery target, and safety/IP risks.
2. Source gate: before API, pricing, duration, model, audio, or capability claims, load `[ref:source-registry]` and `[ref:workflow]`.
3. Capability gate: load `[ref:capability-map]` before choosing single-shot, multi-shot, I2V, start/end frames, element reference, or Omni-style multimodal planning.
4. Mode gate: choose T2V, I2V, FLF2V, element/reference mode, or multi-shot narrative before prompt prose.
5. Prompt build: load `[ref:prompt-guide]`; emphasize action physics, subject consistency, shot order, camera changes, audio speaker assignment, and language.
6. Reference map: assign every asset one primary role: start frame, end frame, character identity, product/object, environment, style, motion, or element lock. State what must not transfer.
7. Quality pass: check duration budget, shot count, one action per shot, stable subject references, native-audio intent, and text/logo expectations.
8. Repair loop: when a take returns, use `[ref:troubleshooting]`; change one variable per retry and record observed drift or motion failure.

## Load Map

| Situation | Load |
|---|---|
| API, model ids, official docs, pricing, or source freshness | `[ref:source-registry]`, `[ref:workflow]` |
| Selecting mode, duration, references, audio, or multi-shot | `[ref:capability-map]` |
| Writing a production prompt | `[ref:prompt-guide]` |
| Multi-shot, storyboarding, action choreography, or dialogue coverage | `[ref:prompt-guide]`, `[ref:capability-map]` |
| Image-to-video, start/end frames, element consistency, or reference video/image | `[ref:workflow]`, `[ref:capability-map]` |
| Chinese, English, Japanese, Korean, Spanish, dialect, accent, or code-switching dialogue | `[ref:prompt-guide]`, `[ref:capability-map]` |
| Bad result, drift, poor action, wrong speaker, weak text, or blocked prompt | `[ref:troubleshooting]` |
| Need a starting template | `examples/golden-prompts/` |

## Prompt Contract

Kling prompts can carry more story than many short-video models, but still need controlled shot budgets:

- define single-shot or multi-shot up front;
- keep each shot's subject, action, camera, and endpoint explicit;
- assign element references and speaker identity precisely;
- use native audio intentionally, especially for multilingual dialogue;
- keep text/logo goals close, stable, and well-lit;
- split sequences when the story exceeds the verified active duration.

Never convert third-party or field-observed Kling tricks into official guarantees. If a claim affects runtime behavior, verify it against current Kling documentation before changing code.
