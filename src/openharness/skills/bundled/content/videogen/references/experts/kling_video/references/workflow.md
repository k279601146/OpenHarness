# Kling Workflow

## Mode Selection

| User goal | Mode | OpenHarness command |
|---|---|---|
| New scene from text | Text-to-video | `generate` |
| Animate a starting image | Image-to-video | `image-to-video` |
| Transition between endpoints | Start/end frames | `first-last-frame` when supported by runtime and active model |
| Use characters/products/scenes as anchors | Element/reference mode | `reference-to-video` when supported; otherwise I2V plus explicit reference roles |
| Several shots in one clip | Multi-shot | `generate` with numbered shot prompt and verified duration |
| Audio-led scene | Native audio | `generate_audio=true` with speaker/language/SFX prompt |

## Runtime Checklist

- Pass the exact user-selected model id when provided.
- Use `duration_seconds` within the active model's verified range; Kling 3.0 official guidance supports 3-15 seconds on its native surface.
- Use `aspect_ratio` before finalizing shot composition.
- Use `resolution` deliberately; confirm output tier and cost when it matters.
- Use `generate_audio` only when audio is supported and the prompt contains audio direction.
- Do not claim generated video until `videogen_cli` reports success and returns artifacts.

## Multi-Shot Continuity

1. Decide total duration and shot count before writing prose.
2. Allocate seconds per shot.
3. Give each shot a camera, action, and endpoint.
4. Carry named characters and element references unchanged.
5. Put dialogue in the shot where the speaker is visible and stable.
6. If the take fails, reduce shot count before adding detail.

## Connected Clip Workflow

For stories longer than one Kling output, generate one accepted clip at a time. Record observed end state, then use start frame/reference or a concise continuity line for the next clip. Accepted observed state overrides the planned storyboard.
