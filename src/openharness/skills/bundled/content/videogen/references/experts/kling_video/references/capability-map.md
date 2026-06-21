# Kling Capability Map

last_verified: 2026-06-21

## Design Into These

| Capability | Extraction move |
|---|---|
| Strong motion and action | Use physical verbs, cause/effect, contact points, and clear endpoints. |
| 3-15 second narrative space | Let one clip hold a short scene or several simple shots when the active model supports it. |
| Multi-shot | Declare "Multi-shot" or "Custom multi-shot" and number shots with duration, action, camera, and endpoint. |
| Image-to-video | Use the image as exact starting identity/composition and describe allowed motion, camera, and light changes. |
| Start/end frames | Lock both endpoints and describe the transition path. |
| Element references | Assign character, product, prop, or scene reference roles and specify what must stay consistent. |
| Multi-character coreference | Name characters and reference roles consistently across shots and dialogue. |
| Native audio | Assign speaker, language, accent/dialect, line, ambience, and SFX. |
| Multilingual dialogue | Keep lines short, tag language per speaker, and avoid mixing languages unless code-switching is intentional. |
| Text/logo fidelity | Keep text close, front-facing, well-lit, and stable; use I2V or element reference when exact product text matters. |

## Design Around These

- Do not overload multi-shot clips; more shots require simpler actions and clearer durations.
- Keep element references role-separated. Avoid asking one reference to supply identity, style, environment, and motion unless testing deliberately.
- Complex hand/product interactions can drift; simplify contact and show important product states close to camera.
- Native audio can improve scene coherence, but long dialogue reduces visual reliability. Use short lines and clear speaker assignment.
- Duration, audio, start/end frame, and reference support are model/surface-specific. Verify before promising them for a routed provider.
- For long stories, generate one accepted clip at a time and carry observed continuity forward.
