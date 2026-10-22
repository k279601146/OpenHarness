# Shared Commerce Design Decisions

Use when a set crosses scene types or its visual system is unresolved. For a specific image, go directly to [product-images.md](product-images.md), [detail-pages.md](detail-pages.md), [marketing-images.md](marketing-images.md) or [brand-assets.md](brand-assets.md). Existing-image localization uses [image-translation.md](image-translation.md), not new design.

## Turn a message into something visible

Fill only these internal decisions for the current output:

| Decision | Useful answer | Insufficient answer |
|---|---|---|
| Buyer question | Whether the connector fits a supplied port | High conversion |
| Evidence | The actual connector photo and confirmed compatible port | A category template's specifications |
| Visual relationship | Connector aligned with the port, with its identifying shape visible | Show convenience |
| Layout | Product view beside a linked connector detail | Premium layout |
| Copy | Exact approved compatibility string, placed beside that pair | Professional text |
| Shared style | Named background treatment, light direction, type hierarchy and accent role | Same style |

Copy the concrete answers into the existing prompt labels. Do not pass this planning table as API fields or ask the image model to decide what the product supports.

Choose the evidence form first: a visible feature uses a traceable close-up; operation uses contact or ordered states; fit uses confirmed dimensions/interfaces; inclusion uses an item-and-quantity layout. An abstract effect can communicate mood but cannot establish performance. Missing evidence calls for a simpler truthful view or a focused question, not an invented cutaway.

## Layout selection

Use a split image/text layout for precise or longer copy. Use overlay only when a short message fits a genuinely quiet region. Use a detail inset when buyers must see a small feature and keep it linked to the right area. Use aligned rows or columns for comparable facts, ordered modules for steps, and an image-led scene for context.

Keep the claim, label, feature and evidence together. Decorative panels, arrows and typography serve those associations. Do not force every page into product-left/text-right, or vary layouts merely to look different.

## Share a visual system, vary the communication job

Keep approved product identity, logo asset, palette roles, type hierarchy, light treatment and callout language consistent. Write one short shared style clause and reuse it in every applicable prompt. Then vary framing, scene and layout according to the output's buyer question. Sharing a palette does not authorize recoloring the product.

Resolve the set's type system once, inside the shared style clause: name the headline class and its companion class concretely — a Didone/transitional serif, humanist or geometric sans, condensed grotesk, slab, engraved small caps, script or mono; never "modern clean font" or an unqualified heavy sans — and reuse the clause verbatim in every text-bearing prompt. A different font class in a later output breaks the set; vary block placement, relative size, contrast direction and supporting devices instead.

A text-bearing output carries a real text block, not a stray mark: a headline plus a second level drawn from the same verified facts — a supporting line or a short feature strip. A lone enlarged headline reads as a watermark, not a designed block. Reserve the block's zone as negative space in the composition wording before placing copy. Only a standalone photographic image may omit copy entirely.

A source/reference has one stated role: identity, exact brand artwork, pose, attribute, or visual style/layout. A style reference supplies hierarchy, spacing or treatment; it does not supply its sample brand, people, copy, dates or product specifications. An existing accepted reference or textual style clause is enough unless a real new asset is needed. See [parallel-generation.md](parallel-generation.md) before dispatching a set.

## Design acceptance

Inspect at intended viewing size: can the buyer recognize the item, read the decisive message, and connect each claim to its feature? Then check set-level coverage and consistency. A beautiful picture with false mechanics, unreadable terms or repeated non-informative pages fails. Use available native text/asset composition for exact dense information when useful, keeping Accio's expected image deliverables and existing tool chain.
