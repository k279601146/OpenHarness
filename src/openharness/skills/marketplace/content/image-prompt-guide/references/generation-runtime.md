# Accio Image Tool Contract

Use Accio's existing `image_generate` and `image_edit` tools. New images and reference-based edits share the same planning/checking loop. This Skill adds no service, SDK, provider or agent framework.

## Operation and sources

Use `image_generate` when the current output requires no inherited source content. Use `image_edit` when it must inherit a product, base canvas, person, style or continuity from supplied or preceding images. Images elsewhere in a conversation do not make every output an edit. A new composition does not remove the need for a product reference.

For edits, supply `reference_images` and an explicit `prompt`. Use the current exposed tool schema; the field and mode examples below describe the previously reviewed interface and do not override a different live definition. Inspect the sources first. Preserve reference order and match each numbered image to its prompt role. A finish donor cannot replace the product identity source. Use only needed images and reuse an accepted result for a follow-up edit.

Follow the current exposed schema for reference representation. If it explicitly accepts asset IDs, pass the real supported IDs; do not turn them into invented URLs. The previously reviewed Accio edit contract uses accessible HTTPS image URLs. Verify remote inputs as readable images. Validate local inputs and upload through the configured asset mechanism before using the returned URL. Do not pass raw local paths or `file://` URLs to the remote tool. Do not invent an upload tool or URL. If required images cannot be read or uploaded, report that specific blocker instead of falling back to text-only generation.

## Mode resolution

Inspect current tool definitions once and reuse them while unchanged. Retain the original mapping:

| Tool | Preferred when supported | Standard fallback | Dense-layout fallback |
|---|---|---|---|
| `image_generate` | `auto` | `simple` | `complex` |
| `image_edit` | `auto_generation` | `simple_generation` | `complex_generation` |

Pass the value through `task_type`. Prefer auto when exposed in the valid enum. If the schema cannot be inspected, use auto only when the runtime explicitly advertises it; otherwise use the documented fallback. Ordinary preservation edits, recoloring, background changes, restoration and single-region text editing are standard. Comparison grids, dense annotations, multi-region composition, technical drawings and full creative posters are dense-layout. A detailed background alone is not a dense-layout task.

`task_type` is a mode, not a model ID or business intent. Do not invent values such as `recolor` or `text_edit`, or add a `model` parameter unless Accio exposes one. Honor model preferences through the existing supported selection mechanism; report unavailable choices.

## Parameters and dimensions

Size is an explicit per-call decision, never left to a service-side default.

| Mode family | Original parameter shape |
|---|---|
| `auto`, `auto_generation` | Concrete `size: "WxH"`; include the closest supported `aspect_ratio` according to the exposed definition. Do not substitute `resolution` for `size`. |
| `simple`, `simple_generation`, `complex`, `complex_generation` | Supported `aspect_ratio` plus `resolution: "1K"` or `"2K"` when a target is specified. Do not pass raw `size`. |

The exposed runtime schema wins if it differs. Validate calls against it; do not copy an upstream example that omits a required field.

Original supported ratios: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`. Priority: explicit user size/ratio, selected platform specification, measured source proportions for edits, then `1:1` for unspecified new images. Keep desired final size separate from legal generation size. If the model cannot express the exact ratio, select a suitable supported ratio and finish through proportional canvas/composition operations; disclose a material substitution. Never silently stretch the product or crop essential content.

Auto-mode size rules:

1. For source-following edits, measure the source only to extract its aspect ratio; the measured pixel values are never the call's `size`. A 1K target means a 1024-pixel long edge; 2K means 2048, with the selected proportions.
2. Without specified final pixels, derive a default long edge of at least 2048. This default does not override explicit user or destination pixels. Write the derived decision into the call itself: `size` in auto modes, `resolution: "2K"` in fallback modes. Omitting the size fields is a contract violation, not a neutral choice; the runtime then silently applies its own 1K default. Under this default, a `1024x1024` source still generates at `2048x2048`, not `size: "1024x1024"`; an explicit user request for `1024x1024` overrides the default and stays `1024x1024`.
3. Generated edges must be multiples of 16, with area from 655360 through 8294400 pixels. Scale proportionally when outside the bounds, round to legal edges, then recheck area.
4. If the exact final size is not legal, generate at suitable legal dimensions and resize proportionally for delivery. Examples: default `800x600` source becomes `2048x1536`; requested `1000x1000` generates at `1008x1008` and delivers at `1000x1000`; 2K `16:9` is `2048x1152`.

Retain the reviewed 1K/2K generation scope. Do not promise 4K generation unless the current Accio tool explicitly supports it. Native upscaling is not native 4K generation.

## Prompt string compatibility

Use the existing English labels, in this order, as a string rather than a new nested prompt object:

`Asset type:` → `Input images:` → `Primary request:` → `Canvas and composition:` → `Camera:` → `Scene/backdrop:` → `Lighting and grounding:` → `Materials, color and style:` → `Typography:` → `Graphics and callouts:` → `Product invariants:` → `Allowed changes:` → `Avoid:`

These labels organize the existing prompt string; they are not additional tool fields or a requirement to fill every block. Retain the established label order when using them. For an edit, make `Primary request` state the actual target and transformation. Use `Input images` to identify source roles when needed, `Product invariants` for protected content and `Allowed changes` for scope and necessary consequences. Add other blocks only if they carry relevant information; an `Avoid` clause is useful for a specific likely failure, not mandatory boilerplate.

Preserve a specific user request without adding creative requirements. Add source-grounded disambiguation where needed to execute it. For a broad generation request, add only useful composition, lighting or style choices consistent with the merchant's goal. Do not import sample props, slogans, brands, palettes or numerical claims. Do not add arbitrary left/right placement unless supported by the request or visual evidence.

Before submitting, check that the actual prompt retains the user's decisive requirement, references the intended images and includes the visual findings needed to execute the change. Generic instructions such as "understand the structure" or "move accurately" do not substitute for the resolved target. Keep analysis, acceptance checklists and success claims out of the model prompt. Use [image-edits.md](image-edits.md) for edit-specific grounding and inspection.

Include exact destination strings for text work; translate instructions into English without changing literal display text. Canvas overlays belong in graphics; on-product marks belong in product invariants unless targeted. A user-confirmed keep is written once per output with its position zone, relative size and a count of exactly one, so duplicating the product does not duplicate the mark. Prompt labels and instructions are not text to render. Quality, masks, fidelity and model selectors are tool parameters only if the actual Accio schema exposes them; do not copy controls from another runtime.

If the live interface exposes `must_change` or `must_keep`, fill them only as required or useful under that schema. They must agree with `prompt`; retain every decisive instruction in the prompt itself because downstream merging is not established by this Skill. Do not invent these fields on interfaces that do not expose them. A diagnostic specification or review table is never an extra tool argument.

For explicit prompt-only review, follow [prompt-review.md](prompt-review.md). Show the exact proposed prompt and supported call fields, clearly separating known values from unresolved bindings. A proposed payload is not evidence of what a downstream service will receive.

## Call examples

Substitute real inspected assets and task-specific prompts; example asset placeholders are not callable URLs.

Auto edit:

```json
{
  "reference_images": ["<existing HTTPS source image URL>"],
  "task_type": "auto_generation",
  "size": "2048x1536",
  "aspect_ratio": "4:3",
  "prompt": "Asset type: Product photo edit.\nPrimary request: Recolor the jacket green.\nProduct invariants: Preserve the person, watch, jacket structure and background.\nAllowed changes: Jacket fabric color only.\nAvoid: Color spill onto accessories or skin."
}
```

Standard fallback edit uses the same real references and prompt with `task_type: "simple_generation"`, `aspect_ratio: "4:3"`, `resolution: "2K"`, and no `size`. Dense fallback uses `complex_generation` with the same parameter shape, only when the task needs it.

New-image auto generation uses `image_generate` with `task_type: "auto"`, `size`, supported ratio and `prompt`; no `reference_images`. Its fallbacks are `simple`/`complex` with ratio and supported resolution, without raw `size`.

For multiple requested outputs, read [parallel-generation.md](parallel-generation.md) before submission. Prepare complete per-output prompts and arguments together; dispatch the ready group through the exposed batch/concurrent/async mechanism before collecting individual images. Keep this single-call parameter shape unless the live host exposes a batch schema. Multiple prompt strings in prose or a candidate count do not execute distinct tasks. If only a blocking single-call host exists, retain sequential execution and state that limitation when relevant.

## Results, failures and delivery

Keep actual returned asset URLs/handles and their output associations. Submission acknowledgements and task IDs are not completed images. Use only Accio's exposed status/result handling; do not invent polling endpoints, cron jobs or canvas APIs. For pending or dependent outputs, follow [accio-orchestration.md](accio-orchestration.md).

Classify failures before retrying. Unsupported fields/modes require a parameter correction, not a visually more complex mode. If auto is explicitly rejected as unsupported, choose the documented fallback and rebuild its size fields. A timeout may leave a request running: resolve the known task through host facilities before duplicating submission. For an unusable returned image, make one targeted repair and retain successful siblings.

Native resizing, compression, format conversion, segmentation and code stitching remain supporting operations. Pure resizing without content changes should not redraw a product; new surrounding content requires an edit. Verify requested dimensions, file size and format. Transparency requires actual alpha and intact foreground edges, not a checkerboard or globally deleting near-white pixels. Use available native tools or permitted local image libraries. Report missing capabilities without fictional calls.
