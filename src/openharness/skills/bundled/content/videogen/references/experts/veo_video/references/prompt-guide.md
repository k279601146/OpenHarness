# Veo Prompt Guide

## Base Formula

Use this compact order for most prompts:

`[Camera/framing + lens]: [subject] [one action with endpoint] in [scene/context], lit by [physical light]. Style/texture: [look]. Temporal behavior: [pace/evolution]. Audio: [dialogue/SFX/ambience/silence].`

## Required Decisions

| Decision | Veo-friendly wording |
|---|---|
| Subject | Specific identity, wardrobe, product surface, or object material. |
| Action | A concrete verb plus consequence: "sets the cup down and steam curls past her face." |
| Scene | Location, time, weather, atmosphere, and scale. |
| Camera angle | Eye-level, low angle, overhead, close-up, medium, wide, over-the-shoulder, POV. |
| Camera move | Static, slow dolly in/out, pan, tilt, truck, crane, drone, arc, rack focus. |
| Lens/optics | Shallow depth of field, telephoto compression, wide angle, macro, bokeh, lens flare. |
| Lighting | Natural source, direction, color, shadow behavior, volumetric haze, reflection. |
| Audio | Speaker and short line, ambience, SFX, music cue, or deliberate silence. |
| Negative prompt | Separate unwanted elements when the active surface supports it. |

## Mode Patterns

### Text to Video

Use one complete shot contract. Avoid stacking multiple actions unless the duration can clearly contain them.

### Image to Video

Start with the reference role:

`Use [Image1] as the exact starting frame and subject identity. Preserve face/product shape, clothing/material, and composition. Only camera, light, and motion may change: ...`

### First and Last Frame

Describe both endpoints before motion:

`Start on [first-frame state]. End on [last-frame state]. The transition is [physical mechanism], with [camera move] and [light change].`

### Reference Images

Assign one primary role per image:

- `[Image1] subject identity only`
- `[Image2] product/object material only`
- `[Image3] environment palette and architecture only`

Add exclusions: `do not transfer wardrobe`, `do not copy background`, `do not change logo shape`.

### Dialogue and Audio

Keep spoken lines short. Name the speaker before the line. Add ambience and SFX after dialogue so the audio mix has hierarchy.

## Quality Pass

- The first clause tells the camera where it is.
- The subject and action can be seen within the chosen aspect ratio.
- The action has a visible endpoint.
- Light comes from a physical source.
- Audio is intentional or explicitly silent.
- Any negative prompt is separate and uses concise unwanted elements.
