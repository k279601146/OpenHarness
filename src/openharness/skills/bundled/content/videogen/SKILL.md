---
name: videogen
description: Generate videos from text, images, first/last frames, or reference assets through the unified OpenHarness videogen_cli tool. Use for real video generation with Seedance, Veo/video3, or Kling/keling models, including cinematic clips, social videos, product videos, image-to-video animation, first/last-frame interpolation, and reference-guided video. Do not use legacy video tools.
license: MIT
user-invocable: true
tags: [video-generation, seedance, veo, kling]
---

# Videogen

Unified OpenHarness video generation skill.

## Rules

- Loading this skill is not video generation. After reading these instructions, call `videogen_cli` before claiming that a video was generated.
- In OpenHarness SaaS, `videogen_cli` is the only real video generation tool. It routes Seedance, Veo/video3, and Kling/keling models through the bundled provider registry, runs on the host, and publishes artifacts to the UI.
- Do not call legacy tools such as `gen_creative_video`, `animate_first_frame`, `video_interpolation`, or `video_with_reference`.
- If the user names a model, pass that exact model id to `videogen_cli.model`. If the UI selected a video model and the user did not override it, omit `model` and let the runtime use the selected preference.
- Do not claim success unless `videogen_cli` reports success and returns artifact path(s). If the script, credentials, API, or output file is missing, report the exact failure.
- After `videogen_cli` succeeds, do not add sandbox links or a separate download section. The OpenHarness UI already receives and renders the video through the artifact event.
- If `videogen_cli` returns `delivery_required=false`, `do_not_deliver_artifact=true`, or `sandbox_path_role=workspace_mirror`, do not call `deliver_artifact` for that output path as a standalone file. The E2B path is a workspace mirror for editing and may be included as a member when the user requested a zip/bundled final package. Continue with other tools only when the user request requires additional editing, transformation, packaging, analysis, or project/code changes.

## Command Selection

- Text-to-video: `command="generate"`.
- Image-to-video from a single starting image: `command="image-to-video"` with `first_frame` or `images=[...]`.
- First/last-frame interpolation: `command="first-last-frame"` with `first_frame` and `last_frame`.
- Reference-guided video: `command="reference-to-video"` with `reference_files=[...]` or `images=[...]`.

Use `duration_seconds`, `aspect_ratio`, `resolution`, `quality` or `mode`, and `generate_audio` when the user or selected model needs those controls. Put visual direction in `prompt`, not in provider-specific fields.

## Provider References

Read only the relevant provider reference when model choice or API behavior matters:

- Seedance: `references/providers/seedance.md`
- Veo/video3: `references/providers/veo.md`
- Kling/keling: `references/providers/kling.md`
- Capability matrix: `references/providers/capability-matrix.md`

For model-specific prompt craft, continuity, first/last-frame handling, references, source gates, and professional workflow guidance, use the embedded expert notes under:

- Seedance: `references/experts/seedance_video/`
- Veo/video3: `references/experts/veo_video/`
- Kling/keling: `references/experts/kling_video/`

These expert bundles are reference material inside `videogen`, not separate generation tools. Still call `videogen_cli` for the actual generation.

## Prompt Guidance

Keep video prompts compact and operational:

- one visible beat;
- one primary camera move;
- concrete subject action;
- physical lighting and environment;
- sound/audio intent when the selected model supports generated audio;
- reference roles and what must not transfer.

For multi-clip stories, generate one clip at a time and update continuity after each accepted output. Do not promise native extend/edit unless the selected provider supports it.
