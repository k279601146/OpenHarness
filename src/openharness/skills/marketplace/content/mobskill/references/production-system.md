# Production System

## Blueprint contract

Render a legible 16:9 multi-panel production board (3×3 is a useful default), not a text-only plan. It must resolve positioning, conversion risk, deliverable map, story arc, feature priority, layout/fixed regions, exact typography, color roles, copy rules, platform adaptations, and three representative frames. Every later prompt/brief must include this image reference.

Quality gate:

- reads at normal viewing size and store-thumbnail scale;
- uses exact fonts/weights/fallbacks, alignment, line limits, and hierarchy ratios;
- shows real evidence or labels conceptual UI;
- frames demonstrate one coherent system with controlled variation;
- each narrative slot contributes distinct proof;
- localized copy has defined expansion/line-wrap tolerance;
- platform adaptation is structural, not a resize.

Reject generic moodboards, unlabeled placeholders, decorative directions with no UI proof, repeated cards/modules, or a Blueprint that cannot drive production.

## Master lock

Create an actual reusable image and record:

| Lock | Required decision |
| --- | --- |
| Canvas | exact platform bucket/size, orientation, export format |
| Object | device frame, app window, or UI-only posture; exact pixels/style |
| Placement | x/y anchor, scale, crop, rotation, safe margins |
| Text zone | anchor, width, alignment, line count, font/weight/size/leading |
| Background | palette, lighting/texture/depth rules and focal hierarchy |
| Fixed pixels | regions reused unchanged through edit/compositing |
| Variables | headline, UI state, approved scene/content changes only |
| Variant Slots | named alternate layouts, fixed rules, and assigned screens |

The text spec alone is not the lock. Pass both Blueprint and rendered Master into downstream generation. Preserve fixed frame/window pixels using masking/compositing. If a new layout becomes necessary, return to Master approval and add a named Variant Slot.

Reject a Master before user review if it:

- resembles a moodboard/example instead of a reusable skeleton;
- lacks a rendered base, exact typography, fixed/changeable regions, or platform canvas;
- uses the wrong posture convention;
- contains bolted-on badges, fake storefront/status chrome, competing focal points, or accidental edge crops;
- depends on tiny copy or repeated information modules;
- has weak balance, unclear reading order, or insufficient UI evidence;
- cannot be reused without redrawing fixed objects.

## Narrative and generation

For each screen specify purpose, one headline, UI state, context/background, unique proof, and Variant Slot. Default phone arc: Hook → Core Feature → Use Case → Outcome → Trust/System → Close. Adapt count and sequence to category; never force this arc on TV/watch/spatial postures.

Before generation, approve one consolidated table. Then:

1. Reuse Blueprint + Master image references.
2. Freeze fixed pixels and edit only declared variables.
3. Preserve exact type hierarchy, color roles, object scale/position, margins, and orientation.
4. Use authentic UI when available; mark conceptual states.
5. Compare the whole set side by side after every batch.
6. Regenerate a failing screen from the Master, never by imitating a neighboring generated screen.

## Icon and Feature Graphic

Icon: share palette/motif with the listing system without becoming a miniature screenshot. Use one dominant silhouette, no baked text or fine detail, and test near 40px. Keep source square and do not pre-round corners unless previewing the platform mask.

Android Feature Graphic: build a separate 1024×500 composition with app identity, optional short tagline, safe central focal area, crop/overlay tolerance, and the same brand DNA. Never resize a screenshot into it.
