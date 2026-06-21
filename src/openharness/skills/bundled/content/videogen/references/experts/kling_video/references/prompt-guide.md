# Kling Prompt Guide

## Single-Shot Formula

`Single shot, [duration]. [Camera/framing]: [subject/reference role] [physical action with endpoint] in [scene], with [light/material/atmosphere]. Audio: [speaker/language/line/SFX/ambience].`

## Multi-Shot Formula

Use numbered shots with duration budgets:

```text
Multi-shot, total [duration].
Shot 1 ([seconds]s): [camera/framing], [subject] [action], ending on [state].
Shot 2 ([seconds]s): [camera/framing/change], [subject] [action], ending on [state].
Audio: [dialogue and ambience by shot].
```

Keep each shot simple enough for the chosen duration. If a shot has dialogue, reduce body action and camera complexity.

## Reference Roles

| Role | Wording |
|---|---|
| Character | `Use [Image1] as Character A identity only; preserve face, hair, outfit, and age.` |
| Product | `Use [Image2] as product geometry and label only; preserve logo placement and material.` |
| Environment | `Use [Image3] as set layout and color palette only; do not transfer people.` |
| Start frame | `Begin exactly from [Image1]; composition and subject pose are locked.` |
| End frame | `End exactly at [Image2]; transition must resolve into that pose/composition.` |
| Motion | `Use [Video1] only for movement rhythm/camera path; do not copy identity or environment.` |

## Audio and Dialogue

- Assign speaker identity before each line.
- Include language and accent when relevant.
- Keep lines short enough for lip motion.
- Put ambience and SFX after dialogue.
- For code-switching, label it intentionally: `Character A speaks Mandarin, then switches to English for the final phrase.`

## Text and Product Work

Kling 3.0 guidance highlights stronger lettering, but exact text remains production-sensitive. Keep text:

- close to camera;
- front-facing and unobstructed;
- high contrast;
- stable for the final second;
- preferably sourced from a reference image when exact brand/product text matters.

## Quality Pass

- Single-shot or multi-shot is explicit.
- Total duration matches the active model.
- Each shot has one action, one camera idea, and a visible endpoint.
- Character and element references are role-separated.
- Audio speaker, language, and line are clear.
- Product/text goals are staged close and steady.
