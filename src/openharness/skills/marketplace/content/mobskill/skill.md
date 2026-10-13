## Conversation Language

Before user-visible output, set the language in this order: explicit user request > runtime/app UI locale > dominant language of the latest user message > English. Do not default to Chinese from the Skill source, examples, triggers, title, or conversation history. Keep replies, updates, `ask_human` cards and options, and delivery notes in that language unless bilingual output or fixed copy is requested; generation prompts may remain English.

# Mobile App Listing Kit

## Conversation and intake

Before any greeting, roadmap, progress note, or text question, determine whether information needed to route, preserve product truth, choose a direction, approve a gate, or continue is missing. If so, the first visible action MUST be one localized `ask_human` card. Bundle related fields, stop after the card, and never duplicate its questions in text. If `ask_human` is unavailable, state that the required intake card is unavailable and stop.

Infer known facts from the request and assets. Collect only missing fields:

- app name, one-line promise, 3–5 key features, audience, category;
- real assets: logo, UI captures, Figma, brand colors/type, or none;
- platform family and posture: Apple (iPhone/iPad, Mac, TV, Watch, Vision), Android (phone, tablet, TV, Wear, Chromebook, Automotive/XR), or both;
- orientation, locale(s), screen count (default 6 only for phone), and delivery scope;
- scope defaults to visual assets only. ASO and video script require explicit opt-in. Android Feature Graphic is core, not optional.

If posture is unspecified, assume iPhone for Apple and phone for Android. Never silently transfer phone composition to another posture. Once the posture is known, read `references/platform-routing.md` before planning.

## Non-negotiable decisions

1. Treat supplied UI and brand assets as truth. Never fabricate a real screen, feature, metric, review, award, rank, price, or compliance claim. Clearly label conceptual UI/assets.
2. Preserve product/feature names and supplied copy. Competitors may inform abstract mood, density, or imagery only; never imitate distinctive layouts, icons, or motifs.
3. Produce and approve a rendered Listing Blueprint before final assets unless the user supplied an already approved equivalent. A text moodboard is insufficient.
4. Lock exact type, color roles, composition, platform canvas, fixed/changeable regions, and representative frames. Generic phrases such as “modern sans” are not production locks.
5. After Blueprint approval, approve the narrative, then a rendered Master Template, then one consolidated per-screen plan. Do not generate final screenshots before these gates.
6. Reuse the approved Blueprint and Master image as visual inputs downstream. For framed mobile assets, preserve the actual rendered frame pixels by masked edit/compositing; independently redrawing each device causes drift.
7. Permit layout variety only through named Variant Slots declared at Master approval. Never improvise a new layout mid-set.
8. Keep each platform set in one visual world and one orientation: exact type hierarchy, color roles, frame/window treatment, scale, margins, and text zone. Only approved variable content may change.
9. Keep marketing text immediately readable at store-thumbnail size. Prefer one headline; move proof into authentic UI. Avoid microcopy, repeated feature lists, icon rows, badges, watermarks, CTA clutter, and simulated storefront chrome.
10. Use `ask_human` for every approval/selection. Do not merge gates unless the user explicitly requests a one-shot run and has already supplied the locked decisions.
11. Verify current App Store Connect/Play Console requirements at submission time; this Skill provides production guidance, not a review guarantee.

## Conditional references

Load only what the current stage needs:

- `references/platform-routing.md`: immediately after platform/posture is known; contains platform composition and narrative differences.
- `references/production-system.md`: before Blueprint, narrative, Master, generation, icon, or Feature Graphic work; contains artifact contracts and approval checks.
- `references/canvas-specs.md`: when selecting/exporting dimensions or formats. Re-verify live requirements before upload.
- `references/qa-and-extensions.md`: before presenting any artifact; load its ASO/video section only when explicitly requested.

## Workflow

### 00 — Truth and positioning

Inspect real assets and extract the visual DNA: palette, exact type if identifiable, UI density, component language, icon/logo identity, and imagery. When no UI exists, define a conceptual-content boundary before continuing.

Return a concise snapshot: category comparisons, felt promise, named store archetype, primary conversion risk, platform/posture scope, and real-versus-conceptual status. Ask to approve or revise.

### 01 — Rendered Listing Blueprint

Read `references/production-system.md`. Render a legible 16:9 multi-panel Blueprint showing:

- positioning and conversion risk;
- platform deliverables/adaptation map;
- screenshot story and feature priority;
- layout system and fixed/changeable regions;
- exact font families, weights, fallbacks, alignment, line limits, and scale hierarchy;
- color roles and background logic;
- copy rules with representative copy;
- three representative preview frames, including any planned Variant Slots.

Use real visual evidence where available and label conceptual content. Present the image and ask to approve, revise, or choose another direction. Stop until approved.

### 02 — Narrative lock

Build a platform-appropriate arc. Phone default: 6 screens — Hook/Identity → Core Feature → Use Case → Emotional Outcome → Trust/System → Conversion Close — adaptable to 3–10. Other postures follow `platform-routing.md`.

For each slot state: purpose, single headline, authentic/conceptual UI state, background/context, unique proof, and Variant Slot if applicable. No two slots may repeat the same message module. Ask to approve the arc/count or revise.

### 03 — Rendered Master lock

Create the actual reusable Master image plus a concise lock spec covering canvas, frame/window/UI treatment, placement/scale, margins, text zone, exact typography, background logic, fixed pixels, changeable regions, and named Variant Slots. The Master must look production-ready, not like a moodboard.

Run the Master checks in `production-system.md`. Present image + spec and ask to lock or adjust. Stop until that exact Master is approved.

### 04 — Plan and produce screenshots

Before generation, consolidate every slot into one plan: headline, UI content, background/context, unique proof, and Variant Slot. Reject repeated or microcopy-heavy modules. Ask for one plan approval.

Generate from the approved Blueprint and Master assets. Use masked edit/compositing for fixed pixels and change only approved variable regions. For Android, prioritize authentic UI and keep captions minor; build Feature Graphic as a separate composition. Run `qa-and-extensions.md` before presenting. Ask to approve the set, regenerate named screens, or return to the Master.

### 05 — Platform adaptations

Produce only postures in approved scope. Each structurally different posture gets its own Master lock while retaining brand DNA and narrative intent. Re-layout; never stretch or crop a phone asset into tablet, desktop, TV, watch, or spatial output. Validate against `platform-routing.md` and `canvas-specs.md`.

### 06 — Icon and Android core extras

After screenshots are approved, produce icon variations when in scope. Keep the screenshot system's palette/motif but design a mark, not a miniature screenshot: no baked text, no pre-rounded source corners unless requested for preview, and no detail that disappears near 40px.

For Android, also produce the mandatory 1024×500 Feature Graphic as its own locked composition. If Android TV is in scope, include its required banner. Ask for approval.

Only now offer ASO copy and preview-video script as optional extensions; do not create them unless requested.

### 07 — Final kit

Summarize per platform/posture, marking each asset `present`, `not built`, or `opted out`: screenshots, tablet/desktop/TV/watch/spatial adaptations, icon, Android Feature Graphic/TV banner, alt text, ASO, and video script. Include Master spec identifiers, conceptual-content disclosures, localization status, and a reminder to verify current console requirements.

## Completion

Complete only when the approved Blueprint and platform Master(s) were used downstream; each set is internally consistent; every slot contributes unique conversion proof; supplied assets/copy remain truthful; conceptual material is labeled; Android core extras are present when applicable; QA passes; and opt-in extensions were produced only when requested.