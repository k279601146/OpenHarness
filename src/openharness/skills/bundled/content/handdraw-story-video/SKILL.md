---
name: handdraw-story-video
description: Create 35-45 second vertical hand-drawn warm-story videos from 7-9 generated color mother images. Use for Chinese warm-story shorts, hand-drawn line reveal with color fill, locked art styles, optional licensed BGM handoff, or Douyin-ready release copy.
---

# Handdraw Story Video

Use this skill to plan and assemble a compact hand-drawn story video. This skill is the creative thinking layer: it decides the story beats, locks one visual style, writes image prompts, checks quality, and prepares optional platform copy. The tools and SaaS backend are the execution layer.

## Boundary

- Use `generate_image` to create one color mother image for each beat.
- Use `create_handdraw_story_video` only after all color mother images have stable workspace references.
- Treat Remotion-style layer timing, preview, render, BGM mix, and FFmpeg checks as visual or acceptance references only. The SaaS backend Tool owns video rendering, optional BGM mixing, MP4 validation, artifact registration, and UI events. Do not promise audible music unless the backend result says BGM was applied.
- Do not create local Remotion projects, start local preview servers, run local render commands, run FFmpeg/ffprobe, run local scripts, HyperFrames, Node, provider CLIs, or direct HTTP requests.
- Do not read API keys, base URLs, upstream model names, provider fields, prices, billing units, host paths, or output paths.
- Do not call `deliver_artifact` for images from `generate_image` or videos from `create_handdraw_story_video`.
- Do not write local release files such as `douyin-caption.txt`; if release copy is requested, return it in the assistant response.

## Workflow

1. Read `references/story-spec.md` when planning the beats or checking story quality.
2. Read `references/styles.md` before choosing an art direction. Lock one style for the full story.
3. Read `references/prompts.md` before writing image prompts.
4. Read `references/publishing.md` when the user asks for BGM, preview/render expectations, platform copy, or final release prep.
5. Plan 7-9 distinct beats with concrete cause and effect. Prefer 8 beats and about 5 seconds per beat.
6. For each beat, write a short beat row covering event, characters, setting, key prop, action/reaction, two visual details, and framing.
7. Generate exactly one complete color mother image per beat with `generate_image`. Use a 3:4 vertical composition or 720x960-friendly intent, the locked style, enough linework for backend line extraction, and a broad paper-white top safe area for backend captions.
8. Reject repeated mother images, crops, mirrors, recolors, style drift, face jumps, or zooms used to pad runtime.
9. After each approved image is published, keep its stable reference such as `artifact:<id>` or `/artifacts/...`.
10. If the user requests BGM, prefer a backend library mood that matches the story, such as warm, gentle, playful, nostalgic, calm, or hopeful. If the user supplies licensed audio, use the stable upload/artifact reference instead. If no valid BGM is available, proceed with silent video when acceptable.
11. Call `create_handdraw_story_video` with the title, topic, scene timing, captions, optional BGM intent, and one stable color image reference per scene.
12. Validate that the final MP4 is 35-45 seconds, 720x960, uses left-to-right line reveal and color fill, keeps captions in the top safe area, and does not reuse the same visual beat.
13. If the user asks for Douyin copy, draft it in chat after the story and final asset are clear.

## Defaults

- Prefer 8 scenes, 5 seconds each, 40 seconds total.
- Use 720x960, 30 fps, MP4.
- Keep captions optional and concise: 0-3 lines, no more than about 18 Chinese characters per line.
- Use no BGM unless the user requests it or the story clearly benefits from a soft backend library mood. BGM failures may fall back to a silent MP4.
- Prefer style D for grounded everyday warm stories, style G for childlike low-age stories, style B for nostalgic family moments, and style A for parent-child coloring-page tone. Use style C or F only when the user explicitly wants a softer picture-book look and accepts weaker line extraction.
- Keep the main illustrated action in the lower half when captions are present.

## Ask Only When Needed

Ask a short clarification only when the answer changes the result materially:

- The story theme, audience, or platform is missing.
- The user requires exact characters, brand/product identity, or a recurring protagonist.
- The user requires BGM or embedded prop text.
- The user asks for a specific style but the story tone conflicts with it.
- The user wants fewer or more than the default 8 beats.

If details are not critical, make a reasonable story-specific choice and proceed.

## Validation

Before final delivery, check:

- Every scene has a distinct action and composition.
- One art style is locked across the full story.
- Each color image is a complete mother image, not a partial sketch, collage, or captioned poster.
- Characters keep recognizable face, hair, clothing silhouette, body proportion, and line quality.
- Captions are short enough for the top safe area.
- Stable references are workspace artifact/upload refs, not local files, blob/data/file URLs, provider URLs, or downloaded temporary files.
- BGM status is reported honestly: absent, applied from library/upload, or fallen back to silent.
- The final tool result says the MP4 artifact was published to the UI.
- Douyin copy, if requested, is returned as text and does not claim local files were created.
