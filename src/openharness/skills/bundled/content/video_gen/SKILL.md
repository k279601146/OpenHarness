---
name: video_gen
description: Video generation planning skill for creating, animating, interpolating, or reference-generating video clips. Use when the user asks for text-to-video, image-to-video, first/last-frame interpolation, motion/style/reference video generation, short cinematic clips, product motion, character action, or canvas video generation.
---

# Video Generation

Use this skill to decide whether a request should become a video generation request and to organize the creative brief before calling the `generate_video` tool.

## Core Rules

- Call `generate_video` for new video clips, animating a still image, interpolating between first and last frames, or using image/video/audio references.
- After this skill is loaded, call the exact `generate_video` tool directly when video generation is needed. Do not use `tool_search`, shell commands, or filesystem scans to rediscover the video generation tool.
- Keep the tool request canonical: describe user intent, not provider implementation details.
- Do not include provider names, upstream model names, base URLs, API keys, CLI commands, output paths, local filesystem paths, or adapter fields in the request.
- Do not use or mention deprecated video CLI tools.
- Before calling `generate_video`, confirm the user's output requirements for resolution, frame size/aspect ratio, and duration. If any of these are missing, ask one concise clarification and do not call the tool in the same turn.
- When the user explicitly accepts defaults, says the choice is up to you, or asks to minimize cost, use the lowest-cost values supported by the selected backend: typically 480p, 5 seconds, and the backend's default aspect ratio. Never silently choose a higher-cost setting.
- Treat resolution, frame size/aspect ratio, and duration as separate choices. A user specifying one does not imply the other two.
- Ask additional clarification when another missing choice materially changes the result, such as required subject identity or whether audio is needed.

## Brief Shape

Convert the user request into a concise production brief:

- `prompt`: final user-visible video instruction. This is the required top-level generation prompt; it must not be nested inside `brief` or `output`.
- `purpose`: why the clip exists, such as social ad, product reveal, story beat, or canvas asset.
- `subject`: main person, product, place, or object.
- `scene`: location, environment, time period, and action context.
- `motion`: what moves, how it moves, and the desired continuity.
- `camera`: shot size, movement, lens feel, and framing priorities.
- `lighting`: mood, time of day, contrast, and color temperature.
- `audio`: dialogue, ambience, sound effects, music, or silence preference.
- `constraints`: must-preserve identity, brand, text, safety, aspect, timing, or platform limits.

Keep the final prompt direct and production-ready. Avoid stuffing unrelated analysis into the prompt.

## Canonical Field Reminders

- `prompt` is required at the top level and must be non-empty.
- `brief` and `output` are required nested objects; use empty objects when there is no detail.
- Use `output.duration_seconds` for video length. Do not use `output.duration`.
- Use `output.count` only for the requested number of videos.
- Do not pass provider-native fields, adapter fields, or old CLI fields.

## Reference Roles

Use stable references exactly as provided by the workspace or canvas, such as `artifact:<id>`, `/artifacts/...`, or `/uploads/...`.

- `first_frame`: start the clip from this image.
- `last_frame`: end the clip on this image.
- `identity`: preserve a person, character, product, or object identity.
- `style`: borrow visual style.
- `motion`: borrow movement or pacing.
- `environment`: preserve place, set, or background.
- `audio`: use as audio guidance when supported.
- `video_reference`: use a video as source or reference.
- `mask`: target a detected subject in a multi-subject source image when the selected model supports subject masks.

Choose `intent` from the workflow: generate from text, animate one first frame, interpolate first and last frames, or reference-generate from multiple assets.

## Model Family Guidance

Use the logical model family that best matches the creative need when a choice is available:

- Seedance: prefer for multi-reference clips, multi-shot motion, Chinese/social-video aesthetics, character continuity, dance/action timing, and cases that benefit from the bundled Seedance expert reference.
- Veo: prefer for photorealism, cinematic language, natural lighting, environmental realism, camera-motivated storytelling, and audio-aware narrative beats.
- Kling: prefer for continuous action, image-to-video subject preservation, complex reference use, dynamic object movement, and keeping a protagonist stable through motion.
- OmniHuman 1.5: use `volcengine-omnihuman-1.5` for one source image plus one driving audio clip. Supply the image as `first_frame`, the audio as `audio`, and optional detected subject masks as `mask`. The generated duration follows the audio.
- DreamActor 2.0: use `volcengine-dreamactor-2.0` for one source image plus one motion-template video. Supply the image as `first_frame` and the template clip as `video_reference`. The generated duration follows the template video.

Do not include provider-native fields or upstream implementation details in the tool request. If the selected family is unavailable, use the canonical model choice or let the backend fail closed with a clear model availability error.

## Seedance Expert Reference

Read `references/experts/seedance_video/` when its creative vocabulary or planning craft would improve the request, even if the selected logical model is not Seedance. Shared references such as camera movement, shot size, lighting, motion continuity, character consistency, audio intent, prompt concision, and anti-slop checks are broadly useful across video models.

Only treat Seedance-specific capability notes, model behavior, examples, troubleshooting, or provider assumptions as Seedance-specific. For non-Seedance models, adapt the general descriptive language and ignore Seedance-only constraints. Load only the relevant expert files needed for the current request.

## Light Validation

Before calling the tool, check:

- The prompt is non-empty and describes visible motion.
- Nested brief and output values are objects, not quoted JSON strings.
- References are stable workspace references, not local paths, blob URLs, data URLs, provider URLs, or downloaded files.
- Requested count, duration, resolution, aspect ratio, audio, and watermark are user-visible output choices.
- The request does not include old CLI fields or provider-native payload fields.
