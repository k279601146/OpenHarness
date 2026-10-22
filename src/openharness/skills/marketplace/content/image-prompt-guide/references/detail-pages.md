# Detail Pages and Information-Dense Images

Choose modules that answer actual buyer questions using available content: product introduction, benefit, detail, use, specifications or included items. Add brand story, comparisons, guarantees and testimonials only when relevant and supported. Do not fill a required module quota with invented information.

For translation of existing images/modules, follow [image-translation.md](image-translation.md) directly: preserve source organization and output dimensions. The new-page defaults below do not authorize new modules, restyling or an extra assembled long image for an existing A+ translation task.

## Module planning and prompt decisions

For each requested module, retain one primary question, its supporting asset/fact, exact copy and layout. A supplied A+ module specification controls its dimensions and role; do not force it into a generic long-page design. A module can contain related supporting facts, but it needs a clear reading order.

| Module job | Reusable composition | Prompt instruction to resolve |
|---|---|---|
| Recognition/introduction | Image-led hero or split introduction | Which actual product view identifies the item, and where can the name/short message remain readable? |
| Benefit explanation | Supported scene plus concise claim; optional linked detail | What action/detail shows the benefit, and which visible part does the text describe? |
| Workmanship/material | Overall product plus traceable surface close-up | Which supplied surface is enlarged, and how does the reader locate it on the product? |
| Operation/setup | Ordered states, each with its own instruction | What changes between states, what stays fixed, and where is the contact or interface? |
| Fit/specifications | Product/measurement view plus aligned label-value rows | Which verified value belongs to which endpoint, variant or row? |
| Options/contents | Aligned verified options or grouped included items | Which quantity/attribute belongs to each item, and what is merely a scene prop? |
| Brand story | Actual brand asset and supported statement, with relevant imagery | What supplied story is being communicated, without inventing credentials or endorsements? |

Select only modules supported by content and the requested scope. Preserve page-level palette roles, type hierarchy, spacing and photographic treatment. Alternate scene, detail and information views when their jobs differ; do not mandate a background-color alternation or a new layout for its own sake.

## Accio default delivery

Retain the original production path: generate complete numbered screen images through `image_generate`/`image_edit`, then assemble the long image with code using an available local image library. Use 2K generation for PDP screens by default, subject to the runtime contract and explicit caller/user dimensions. Pass-through merchant graphics need no image call. Keep listing/main images separate from the PDP column.

Deliver the numbered screens and the assembled long image unless the caller/user excludes the long image or there is only one screen. Platform slices are produced when requested. Retain the existing output organization: `screens/`, `long/`, optional `slices/`, and per-screen generation prompt logs in `prompts/`. Follow an explicit caller output schema or location when supplied. Publish local outputs through Accio's available asset/file mechanism so the caller can access them. If assembly is unavailable, return the screens as a clearly partial result; do not substitute an HTML draft or promise the missing image.

Scale sections proportionally to the target column, preserve their order, and avoid product stretching or cropping. If a source is too small for the target column, resolve that output quality issue rather than silently upscaling it as a high-resolution original. Verify current destination constraints when claiming upload compliance.

Prepare independent section prompts together and use [parallel-generation.md](parallel-generation.md) where supported; stitching remains dependent on completed sections. Reuse [design-patterns.md](design-patterns.md) for layout mechanisms rather than fixed templates.

## Optional production methods

1. **Complete section images:** Generate each section with its own exact copy when the text volume and precision requirements are suitable for the available model. Inspect the text. Assemble sections with native layout/stitching for a requested long image.
2. **Visual assets plus typography:** Generate or edit the required scenes/product assets, then compose the copy, tables and branding using available native layout tools. This is useful for dense multilingual text, frequently revised offers or exact specification tables.
3. **Mixed sections:** Use either method per section while sharing the page's visual system.

Use native typography/HTML only when Accio already exposes the required composition, rendering and asset-delivery capabilities, and the result preserves the caller's expected image outputs, or the user explicitly requests that alternate deliverable. Do not make these capabilities a new dependency of the default path. The user may specify the method or editable deliverable. Do not require HTML, generate every existing product photo again, or remove every background automatically. Reuse trustworthy source images when they already serve the module. If native composition is unavailable, adapt to supported generation and disclose material limitations.

## Layout patterns

- **Split:** Prefer for longer or precise copy, or when the image has no quiet text area. Fit the whole required product view without distortion; size columns or stacked regions for the actual canvas and copy. A square image region is optional. Prompt: "Pair [product/detail view] with a separate [text region]. Keep [essential features] fully visible. Set '[headline]' above '[body copy]' in the text region; preserve the relationship to [feature]."
- **Overlay:** Prefer for short copy and a scene with usable quiet space. Prompt: "Show [supported scene/action], keeping [product feature] unobscured. Put '[exact short copy]' in [quiet area]. Use [contrast treatment only if needed] without obscuring the product or producing a hard seam." If no readable region exists, use split rather than increasingly opaque overlays. A gradient is a local option, not compulsory.
- **Specifications:** Prefer aligned labels and values for exact dense facts. Prompt: "Show [product view] beside the following rows: [exact label-value-unit mapping]. Keep each value with its label and variant, with readable footnotes [exact strings if supplied]." Use available native typography when exact tables exceed reliable image text rendering; never invent data to fill a row.
- **Linked detail:** Prompt: "Pair [overall view] with [supported close-up], connected to [actual location]. Place '[exact feature copy]' beside the detail." Do not imply hidden internals from an exterior reference.
- **Ordered states:** Prompt: "Show [verified states] in [reading order], keeping [identity and comparison conditions] consistent. Match [literal instructions] to their respective state." Counts come from real steps, not a template.

Place these clauses into the existing prompt labels with the actual input roles and product invariants. For each section, include its own text and shared style; do not give the image model the full page's copy and ask it to choose. For example, a supplied folding mechanism needs supported folded/open states with correct hinges, not an attractive but mechanically unrelated exploded view.

Define shared width, palette, spacing and type hierarchy. Preserve individual product proportions. Section heights may vary with content unless the destination requires fixed modules. For long outputs, assemble manageable sections rather than redrawing the whole page through an image model.

For HTML or canvas delivery, follow the actual host's import constraints and bind real assets. Do not ship temporary placeholders as complete output. Inspect the rendered result for clipping, overflow, missing glyphs, seams and unintended cropping; verify final image dimensions when exporting. An HTML draft is not a delivered PNG unless the PNG was actually rendered and provided.

Inspect modules individually and after assembly: exact text, claim-to-feature mapping, product identity, consistent style, correct order and complete seams. A visually polished assembled page still fails if a required module or qualifier is missing.
