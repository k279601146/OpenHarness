# Edit Workflow

Use this short workflow for all edits; use [edit-patterns.md](edit-patterns.md) only for the selected operation. The slots below support prompt construction inside the existing generation workflow, not a new API or mandatory extra model call.

## 1. Select the operation

| Requested change | Pattern section |
|---|---|
| Color, finish or texture | Attribute |
| Literal replacement or text removal | Text |
| Translate commerce graphics into another language | [Ecommerce localization](image-translation.md); use its full workflow |
| Move, resize, reshape, attach or change interaction | Structure and placement |
| Rotate the object or change the camera | Viewpoint |
| Background, lighting or visual style | Environment and style |
| Remove an object or insert from another image | Removal and compositing |

Multiple requested changes may use multiple patterns in one call. Select by user intent, not product category. A short instruction may require spatial work; a long instruction does not automatically require a complex model mode.

Localization uses its specialized text-region map instead of loading all edit patterns.

## 2. Fill a small edit specification

Inspect the actual sources. Identify each input's role and order. Fill four items using the selected pattern's questions: **target**, **desired end state**, **protected properties**, **necessary dependent changes**. Use concrete observations and the user's requirements, not an inventory of the whole image. Keep unknown facts explicitly unknown. Do not infer hidden ports, unreadable text or measured dimensions as product facts.

The user's requested change overrides the original state of that property. Preserve unrelated identity and content; allow necessary changes to projection, contact, shadows or layout. An attribute donor supplies only that attribute. An explicit concept redesign can change designated structure but is not proof of existing inventory. If requirements materially conflict, resolve the conflict rather than silently changing the target.

For a clear request, answer the pattern questions internally and proceed. Ask only when missing evidence or conflicting cues prevent a faithful result. If a necessary source is inaccessible, report that limitation instead of claiming visual grounding.

## Canvas overlay marks

Before building the prompt, test each visible logo, watermark or overlay by physical location. A mark printed, embossed, woven or engraved on the product or its package is part of the product: protect it silently through `Product invariants`, and never ask about it. A flat graphic pasted on the photo canvas — a corner brand badge, seller/shop watermark, site URL, QR code, stock-photo overlay or contact info — needs the user's decision. If the request does not state what happens to it, ask once before any call, listing each detected overlay with its location (for example "a red brand badge in the upper-left", "a site watermark across the lower right") and offering keep or remove per mark. Follow the answer literally: keep means keep, remove means remove — no reinterpretation, no partial application, no deciding it yourself. The only exceptions are a request that already states the intent and a pure native operation that cannot alter the mark.

A confirmed keep is a layout instruction, not a product part: declare it in `Graphics and callouts` with its position zone, its size relative to the canvas, and a count of exactly one — reproduce the single mark at the source's relative position and scale with unchanged artwork. Never duplicate it per product copy, column, panel or SKU, re-anchor it onto the product, tilt it into the product's perspective, or give it a shadow. A confirmed keep outranks destination requirements: mention the listing-compliance risk once and still keep the mark; only a new user instruction removes it.

## 3. Write and check the actual prompt

Fill the chosen sentence pattern, then place the sentences in the existing prompt labels. Carry every decisive slot value into the final `prompt`; do not compress a resolved relationship back into vague wording. Omit irrelevant slots and placeholders. Do not add template example facts to the current product. Use coordinates only when useful and grounded in the actual source dimensions and coordinate system; retain semantic landmarks and account for cropping/resizing.

Apply the main Skill's coverage, consistency, binding and fidelity checks. In particular, test each preservation clause against the desired end state: replace a conflicting freeze of pose, silhouette or shadows with protection of the underlying identity and permission for the required change. Preserve reference features used to locate the target unless changing them is requested. Keep execution-critical instructions in `prompt` even when supported auxiliary fields repeat them.

For prompt-only review use [prompt-review.md](prompt-review.md); otherwise execute through the existing Accio contract without adding an approval step.

## 4. Inspect the result against the same specification

Check the requested change first, then the protected properties and dependent changes. Use the operation's acceptance cue. Compare to original sources and target relations, not merely the latest generated image. A brief whole-image check catches collateral changes. Inspect actual text and file properties when required. If the result or a detail cannot be inspected, label it unverified rather than claiming success. When a mark was confirmed to keep, verify it in every output: present, exactly one, at the source's relative position and scale, with unchanged artwork and opacity.

For a failure, identify the observed discrepancy. Fix source interpretation, missing evidence or conflicting prompt clauses before retrying; for execution error, make one focused correction. Re-state critical invariants. Use the latest output only if identity and protected content remain sound; otherwise return to the original. Preserve source roles and order. After one targeted repair fails, explain the limitation unless more iteration is authorized. Report concise verified status in the user's language, keeping diagnostic records internal unless requested.
