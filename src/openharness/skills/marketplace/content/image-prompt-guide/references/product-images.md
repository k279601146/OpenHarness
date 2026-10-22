# Product Images and Listing Sets

Use for main/hero, feature, material, fit, usage, contents and comparison images. Start from the requested count and buyer questions; a single image is not an invitation to create a whole listing. Existing translation goes directly to [image-translation.md](image-translation.md).

## Pick the visual job and fill its pattern

Select only the relevant row. Bracketed values must come from current sources; replace them before calling. Clauses below fill the normal prompt string, not extra API fields.

| Job and evidence | Design decision | Prompt clause |
|---|---|---|
| **Main/hero:** actual item and included configuration | Choose a view that makes the product's defining form visible. Keep required parts in frame and the background subordinate. Follow verified destination rules. | "Show [actual item/configuration] as the sole focal subject in [view]. Keep [identifying features] unobscured and the complete required silhouette inside the canvas. Use [requested/verified backdrop]." |
| **Single benefit:** confirmed feature and how it helps | Show the use/action that makes the benefit understandable. A support inset may reveal the feature; do not bury it behind decoration. | "Show [supported action/context], with [feature] visibly [relationship]. Place '[exact benefit]' beside [evidence area], leaving [functional contact] visible." |
| **Feature overview:** several confirmed features | Group labels around a readable product view. Each has a specific endpoint; combine related information rather than duplicating labels. | "Show [product view]. Connect '[copy A]' to [feature A] and '[copy B]' to [feature B], with separate readable labels and uncrossed leaders." |
| **Material/workmanship:** supplied or clearly visible surface detail | Use a traceable macro/inset and enough overall view to identify where it belongs. Lighting reveals the real texture. | "Pair [overall view] with a close-up of [evidenced area]. Show its actual [surface/edge/stitching] under [revealing light]; link the detail to [location]. Render '[exact material copy]' beside it." |
| **Fit/compatibility:** confirmed values or interfaces | Dimension lines end at the measured boundaries; connection views expose the actual mating surfaces. | "Show [product/interface] aligned with [verified counterpart]. Place '[value and unit]' between [measurement endpoints], or '[compatibility copy]' beside [matching interface]." |
| **How to use:** verified ordered steps | Use only necessary states with consistent orientation and a visible action/contact in each. | "Show [ordered supported states] in [reading direction]. In each state, expose [contact/action]. Associate each step with its own exact instruction: [mapping]." |
| **Contents:** confirmed items and quantities | Arrange distinct included items without implying scene props are bundled. Labels attach to the correct item. | "Arrange exactly [included items and quantities] in [grouping]. Show each item distinctly and pair it with [literal item label, if requested]. Do not add accessories." |
| **Comparison:** supported comparable attributes | Align scale, camera and conditions where they affect interpretation; keep options and their values together. | "Compare [verified options] using [same viewing conditions]. Associate each option with only these supplied values: [mapping]." |

Choose an image-led layout when the evidence is self-explanatory. Choose split text/image for longer explanations, or a compact label/inset when the relevant feature is small. Do not put text on every image, require a fixed feature count, or treat a category sample as product evidence. A new camera view cannot establish invisible construction; use supplied extra views or avoid claims about unseen features.

## Plan a set without repeating a template

Assign one primary purpose per requested output; supporting facts may share the same image. Merge redundant messages rather than filling a quota. Share product identity, brand assets, palette roles, type hierarchy and photographic treatment. Change framing and layout when the job changes: hero for recognition, macro for material, supported scene for use, aligned items for contents.

Prepare a complete prompt for each slot and use [parallel-generation.md](parallel-generation.md). Existing source photos can support all slots independently; a newly generated hero is not automatically required first. Pass each output only its own copy and needed references, along with the shared style clause. A text-bearing slot follows the set's text-block and type-lock requirements in [design-patterns.md](design-patterns.md): at least a headline plus one supporting level from verified facts, with the named type classes reused verbatim across slots.

## Worked example: feature, not adjective

Illustrative inputs only: the merchant supplies a photograph of a cable with a visibly braided sheath and asks for a detail graphic with the exact words "Braided outer sheath". No bend-life or strength test is supplied.

"Asset type: Listing detail image. Input images: Image 1 is the cable identity and surface reference. Primary request: Show the visible braided outer sheath. Canvas and composition: Pair the cable's overall view with an enlarged detail of its outer braid, connected to the corresponding cable segment; keep connectors recognizable. Typography: Place 'Braided outer sheath' beside the detail. Product invariants: Preserve the supplied cable, connector geometry, color and braid pattern. Avoid: Invented internal layers, test results or durability numbers."

Use this relation-building method for other products; do not transfer this cable's material claim.

## Platform and acceptance

When upload readiness is requested, check the destination's current authoritative requirements for the actual image role/category or use a verified specification supplied by the host. Separate mandatory rules from creative recommendations; do not adopt a sample's fixed dimensions, occupancy percentage or blanket ban on on-product branding.

Inspect identity, required count, distinct purposes, exact copy and label endpoints. Props must not imply inclusion; dimensions must not come from apparent pixel size. For physical contact/wearing/category context, use the matching section of [commerce-recipes.md](commerce-recipes.md). A contact sheet may supplement, not replace, individual files.
