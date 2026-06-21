# Veo Capability Map

last_verified: 2026-06-21

## Design Into These

| Capability | Extraction move |
|---|---|
| Cinematic realism | Give camera position/move, subject, action, scene, light, lens/optics, and material details instead of vague quality adjectives. |
| Native audio | Put audio in a separate sentence: dialogue, ambience, SFX, narration, or silence. Keep dialogue short and assign the speaker clearly. |
| Short high-fidelity clips | Design one beat for 4, 6, or 8 seconds. Use an observable endpoint rather than a broad plot. |
| 16:9 and 9:16 framing | Choose aspect ratio before writing the shot; keep the subject position compatible with the frame. |
| First/last-frame generation | Lock the first and final visible states, then describe the transformation path between them. |
| Reference-image direction | Assign up to three image roles when the active surface supports references. Avoid mixing identity, style, product, and environment in the same asset unless intentional. |
| 720p/1080p/4k output | Prefer 720p/1080p for iteration; reserve 4k for final-quality use where latency and cost are acceptable and the model tier supports it. |
| Extension | Continue only from accepted Veo output and preserve observed final-frame state, camera logic, lighting, and subject continuity. Verify extension support for the active endpoint. |

## Design Around These

- Veo clips are short; split long stories into connected clips and update observed continuity after each accepted output.
- Prompt languages, reference support, audio, resolution, and usage type differ across model tiers and surfaces.
- Reference-image-to-video can be constrained to specific duration on some surfaces; verify before promising variable length.
- 4k and audio increase cost and latency; do not default to them for rough exploration.
- Tiny text, hands, logos, and distant faces remain risk zones; stage important details close and stable.
- Negative prompts should be passed as a separate supported field when possible, using noun phrases for unwanted elements rather than instructional "no/don't" wording.
