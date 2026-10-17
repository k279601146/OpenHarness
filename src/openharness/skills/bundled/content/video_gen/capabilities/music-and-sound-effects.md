# Music and Sound Effects

Read this only when generating new BGM, ambience, or action sound effects. Reuse existing audio directly; use the corresponding capabilities for speech generation and transcription. For an audio-only task, deliver the audio directly

First distinguish music from sound effects, then establish the purpose, target duration, mood or sound source, looping requirements, and sound layers. Follow the actual tool schema for models, durations, formats, and fields

## BGM

If `music-prompter` is available in the current environment, read it first to organize the composition prompt; otherwise continue with the available tools. Reuse its writing approach while taking generation parameters from the current schema

First establish the emotional progression of the whole piece, then describe the style, rhythm, core instruments, density, sense of space, and how it opens, develops, and resolves. Use `Instrumental only, no vocals` for a score without vocals

For narration, use a spacious arrangement with steady dynamics. Generate sections according to the current tool's capabilities, keeping rhythm, timbre, and section joins continuous

## Ambience and Action SFX

For audible Seedance videos, generate ambience and action SFX together with the picture: enable video audio and describe each sound source, action, and timing in the shot prompt. Do not generate those effects separately here. Preserve the generated video’s SFX when mixing in separately produced BGM; a music track does not replace action sounds

The standalone SFX method below is for audio-only requests, editing existing footage, or other video models without synchronized audio. First retain usable existing sound, then produce the needed effects and align them to the action onset, contact, or landing

Directly describe the specific sound source, action, material, distance, space, whether it is continuous or a single event, and its onset and natural tail. Examples include a nearby wooden door closing, a glass bottle being placed on a table, or steady rain in the distance

Build an action sound effect around one event, preserving a clean onset and complete tail. Keep ambience spatially continuous and state the looping purpose when a loop is needed. Generate an isolated track containing only the target sound source

## Review and Delivery

Audition and check the sound source or musical style, audio quality, actual duration, and tail; check the join for looping material. For music, confirm the vocal requirements and ending; for SFX, confirm that the action is clear and the sense of space is appropriate. For video tasks, also audition the final mix: planned effects must be audible and synchronized, not missing or masked by BGM

Name and deliver the audio files separately. Arrange them against picture during local assembly: retain or mix in the needed dialogue, ambience, and action SFX instead of replacing the entire source audio track when adding BGM; let music yield to dialogue and key effects, align action effects with events, and use ambience to maintain scene continuity
