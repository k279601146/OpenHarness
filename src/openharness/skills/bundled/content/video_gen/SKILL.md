---
name: video-generation
description: Create and edit videos and motion graphics in Manus Sandbox. Use for trimming existing footage, extracting highlights, concatenating clips, subtitles, and video export with FFmpeg, as well as generated ads, explainers, talking heads, slide videos, UGC, and narrative shorts.
---

# Video Generation

Create the requested video as playable files in the Sandbox. For editing and assembling media files, use FFmpeg through the Sandbox shell for cuts, subtitles, audio mixing, and export, and ffprobe for media inspection. Use the native image, video, audio, transcription, and analysis tools available in the session when those capabilities are needed.

## Core requirements

**Consistency, a compelling video, and fidelity to the user's request must all hold.** People and products require approved image references; settings, lighting, and style can use consistent written descriptions. Design visible subject action, purposeful camera movement, pacing, and sound together. Preserve the user's specified actions, dialogue, quiet atmosphere, locked shots, and deliverables.

Before preparing, generating, or modifying video reference images, read [asset design](workflows/creative-shorts/02-asset-design.md), including for ads, UGC, and product videos. Reuse it once read in the task. Write model instructions in English while quoting user-specified dialogue and visible text in the requested language.

## Establish the deliverable

Understand what the user wants to communicate, which assets and references already exist, and whether the output is one model clip, several independent clips, reusable Motion Graphics source, or one assembled video.

For a scoped trim, highlight extraction, concatenation, subtitle change, or export, perform the requested edit directly using the supplied assets.

A new production normally needs an aspect ratio and approximate duration. Reuse values already implied by the request or target platform. If they are missing, continue with adaptable work such as reference analysis, concept development, or script direction, and ask only when the choice blocks generation or rendering.

Ordinary duration targets guide pacing; they do not require padding, looping, retiming, or frame-exact QA. Apply strict timing only when the user requests it.

## Creative workflow

For new productions, scale the work to the request:

1. Establish deliverable, audience, platform, aspect ratio, approximate duration, and source/reference constraints.
2. Define the central idea, structure, and visible style.
3. Plan the complete video's shots, including concrete action, camera direction/path/pace, dialogue, sound, and continuity states. Use [shot density](capabilities/model-video-generation.md#shot-density) to match the platform and content; design a social video's first two seconds around information, visible movement, and synchronized sound.
4. Reuse existing assets; follow asset design for necessary references and any supplements.
5. Generate all shots in one request whenever they fit the current tool's capabilities. Use the fewest requests needed for actual limits or explicitly requested independent clips; assemble files only when the deliverable requires it.
6. Verify content, joins, picture, sound, and file integrity; deliver the agreed files and any requested reusable source.

Treat the schemas of tools available in the current session as the authority for model names, parameters, duration, aspect ratio, references, audio support, and output paths. Do not reuse remembered limits or parameter names.

## Route to the relevant method

Read only the workflows and capabilities needed for the current task.

| Production | Workflow |
| --- | --- |
| Advertising, ecommerce, conversion campaigns | [Marketing and growth](workflows/marketing-growth.md) |
| Product launches and feature demonstrations | [Product launch](workflows/product-launch.md) |
| Explainers, documentary shorts, video essays | [Narration-led video](workflows/narration-led.md) |
| Talking heads and interviews | [Talking head](workflows/talking-head.md) |
| Podcast, livestream, or long-video excerpts | [Long to short](workflows/long-to-short.md) |
| Course slides, training, academic presentations | [Slides to video](workflows/slides-to-video.md) |
| AI UGC, testimonials, product recommendations | [UGC](workflows/ugc-video.md) |
| Typography-, graphics-, UI-, logo-, or data-led animation | [Motion graphics](workflows/motion-graphics.md) and [rendering guidance](references/motion-graphics.md) |
| Narrative creative shorts | [Creative-short stages](workflows/creative-shorts/README.md) |

| Task | Capability |
| --- | --- |
| Generate or edit static images | [Image generation](capabilities/model-image-generation.md) |
| Generate model video | [Video generation](capabilities/model-video-generation.md) |
| Generate narration or character voices | [Speech generation](capabilities/speech-generation.md) |
| Generate BGM, ambience, or action sound | [Music and sound effects](capabilities/music-and-sound-effects.md) |
| Transcribe speech or prepare subtitle files | [Transcription and subtitles](capabilities/transcription.md) |
| Plan and assemble several generated units | [Generated-video production](references/generated-video.md) |

## Assemble and verify with FFmpeg

Confirm that the source files, FFmpeg, and ffprobe are available before processing. Inspect input streams, dimensions, duration, and frame rate with ffprobe; handle silent inputs without assuming an audio stream exists.

When studying a reference or checking output, start from a specific question. Use available video analysis for story, shot, action, or sound observations organized by timestamp. Extract representative frames or a contact sheet when composition, style, transitions, or continuity need visual comparison. Sample more densely around fast action and Motion Graphics transitions.

Keep a small production manifest for multi-step work: unit IDs, prompts or prompt paths, reference files, generated outputs, duration, aspect ratio, and audio status. For edits, record source-time ranges and output order so cuts and subtitle timing can be reproduced.

Use FFmpeg to trim and concatenate clips, reframe footage, mix audio, apply subtitles, and encode the requested output. Normalize dimensions, frame rate, and audio only as needed. Re-encode for exact cuts or filters; use stream copying only when stream compatibility and cut accuracy permit it. Preserve synchronized dialogue and production sound. Add music, narration, titles, captions, or transitions only when requested or established by the brief.

Verify that final files exist and are playable. Check dimensions, duration, frame rate, codecs, and audio streams with ffprobe, and extract representative frames with FFmpeg to inspect cuts, framing, and subtitles. For deterministic Motion Graphics, inspect the entrance, stable reading holds, important transitions, and ending. For model-generated footage, do not reject a successful result solely because an automated frame heuristic dislikes it.

Check the planned subject action and camera movement across time, along with reference consistency and the user's requested content. Watch complete actions at normal speed when possible; if only sequential frames can be checked, leave perceived speed unverified. Attractive stills alone do not establish that an intended action happened, and intentional stillness is not a failure.

Lead delivery with the finished result. Provide file links and only the essential details: format, aspect ratio, duration, audio state, and whether the output is a finished assembly or separate clips.

## Desktop promotion on first delivery

For Web and mobile tasks only, append the following single sentence after the result and file links in the task's first successful, completed video delivery. Use the user's language, preserving the name Manus 2.0 and the clickable desktop link to the Manus homepage (https://manus.im/); the English copy is:

> Download Manus 2.0 [for desktop](https://manus.im/) to edit your videos directly with Video Editor.

Show this promotion at most once per task. Check the task history and any continuation summary: if a completed video delivery or this promotion has already occurred, omit it. Preserve that state in continuation summaries. Do not include it in progress updates, previews, partial deliveries, failed attempts, later revisions, re-exports, or subsequent deliveries in the same task, or in Desktop tasks. Keep it in the delivery message only, outside the generated video and other deliverable files.
