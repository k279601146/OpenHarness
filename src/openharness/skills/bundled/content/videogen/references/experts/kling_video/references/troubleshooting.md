# Kling Troubleshooting

| Failure | Likely cause | Repair move |
|---|---|---|
| Chaotic multi-shot | Too many actions or unclear shot durations | Reduce shot count; number shots with seconds and endpoints. |
| Weak motion | Prompt uses pose adjectives instead of physics | Add force, contact point, trajectory, timing, and consequence. |
| Character drift | Reference role or character name changed | Reuse the same character tag and identity lock in every shot. |
| Product/logo drift | Text/product staged too small or moving too much | Move product closer, front-facing, stable, and lit; use reference role. |
| Speaker confusion | Multi-character audio not assigned | Name speaker, language, and line per shot. |
| Lip-sync instability | Line too long or head/camera moving | Shorten line; use medium close-up and stable face. |
| I2V loses composition | Allowed changes not bounded | Lock composition and identity; allow only motion/light/camera changes. |
| Start/end frame miss | Transition path unclear | Describe first state, physical transition, and final state in order. |
| Story feels cramped | More narrative than duration can hold | Use Kling 3.0 up to verified duration or split into connected clips. |
| Safety block | Protected identity, unsafe content, or evasive wording | Rewrite to authorized, generic, fictional, or safer framing. |

## Retry Rule

Change one major variable per retry: shot count, duration, reference role, camera, action physics, audio, or product staging. If three retries fail the same way, simplify the scene design.
