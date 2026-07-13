# Veo Workflow

## Mode Selection

| User goal | Mode | Bahew command |
|---|---|---|
| New scene from text | Text-to-video | `generate` |
| Animate a still image | Image-to-video | `image-to-video` |
| Transition between endpoints | First/last-frame | `first-last-frame` |
| Guide with several assets | Reference-image direction | `reference-to-video` if the runtime and active model expose it; otherwise image-to-video with explicit role notes |
| Continue accepted Veo footage | Extension planning | Verify active endpoint support; otherwise generate next clip from final frame/reference |

## Runtime Checklist

- Pass the exact user-selected model id when provided.
- Use `duration_seconds` only within the active model's verified range.
- Use `aspect_ratio` before finalizing framing.
- Use `resolution` deliberately; 4k can increase latency and cost and is not available for every tier.
- Use `generate_audio` only when audio is supported and the prompt includes audio direction.
- Do not claim generated video until `videogen_cli` reports success and returns artifacts.

## Continuity Workflow

1. Review the accepted clip's actual final frame and audio endpoint.
2. Write a one-line observed state: subject pose, camera position, lighting, environment, and unresolved action.
3. For extension, preserve observed state and continue with a single new beat.
4. For a new generation, use final frame as first frame or reference when supported.
5. Exclude already completed beats from the next prompt.

## Source-Sensitive Runtime Caveat

Google docs can distinguish Gemini API, Google Cloud, AI Studio, Flow, and third-party surfaces. When a user asks for API behavior, pricing, model ids, quotas, or commercial deployment details, answer from the current source registry rather than general Veo memory.
