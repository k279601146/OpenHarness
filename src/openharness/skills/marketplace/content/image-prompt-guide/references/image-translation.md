# Ecommerce Image Localization

Use for translating existing main images, listing graphics, detail-page sections or A+ modules into one or more languages. This specializes the shared edit workflow. Preserve the product and the source's communication structure; do not turn translation into a redesign or a new listing strategy.

## 1. Inspect and bind text to meaning

Resolve target language/locale and image scope from the request. Keep conversation language separate. Use the requested regional variant; if none is specified, choose a standard form and state the assumption only when material. Reuse a supplied glossary. Ask only about consequential ambiguity, illegible source copy or a conflict with the requested deliverable.

For each source, record compact text-region entries: `region ID | source text | role | linked product feature/module | translate or protect`. A bounding box is optional; a clear location and anchor suffice. Read small copy at adequate resolution. OCR may assist but is not authoritative; do not guess a number, qualifier or hidden sentence. If a region remains unreadable, request that text or a clearer source. Independent readable regions may be prepared or tested while waiting, but retain unresolved regions and label the output partial; never replace unreadable copy with generic filler.

Separate editable marketing overlays from physical product/packaging text, logos, model codes, barcodes and certifications. Preserve physical printing and identifiers by default: translating a label on the photographed item changes the depicted product. If the user explicitly includes packaging/label localization, treat it as an authorized separate surface edit while retaining structure; clarify only a real conflict with product immutability. A text-free main image may need no edit. A protected brand in its original script is not a missed translation; distinguish it from an unresolved editable region in the report. Do not add translated captions to an image that has none. Preserve supplied format rules; verify live platform policy only when claiming compliance.

## 2. Translate the message before rendering

For each editable region, produce one final target string, tied to its region ID. Use idiomatic retail language while preserving the original meaning, tone and claim strength. Keep qualifications such as "up to", "resistant", conditions, negations and footnotes. Do not turn resistance into proof, a benefit into a certification, or a suggestion into a guarantee. Do not invent sales claims or improve product specifications while translating.

Preserve numerical value, unit meaning, model names and compatibility. Localize number typography only without ambiguity; unit conversion, currency conversion, price changes and localization of legal facts need explicit scope and reliable information. Do not silently convert them to fit a market. Repeated terms use the same per-locale glossary. Literal replacements supplied by the user remain verbatim, including unusual spelling.

If the faithful translation is longer, prefer a concise natural equivalent that retains all content; otherwise use local reflow. Never drop a condition or a selling point to make a box fit. Once selected, pass exact destination strings to the image tool; do not ask it to independently retranslate. For uncertainty in market-specific terminology, report it rather than asserting professional linguistic validation.

## 3. Preserve relationships and permit local adaptation

Keep the product's identity, geometry, material, color, pose, location and scale; also preserve physical markings. Lock the canvas, section order and major product/text regions unless the user permits a larger layout change. Associate each claim with its original feature, diagram, photo or table row. Keep callout endpoints fixed; text-side line starts may move with their label. Do not swap claims or move the product to make room.

Fit each translation in this order:

1. Use natural word boundaries and line breaks within the original region, with script-appropriate font/glyph support and a similar visual hierarchy.
2. Adjust line spacing and local padding; use a modest font adjustment if still readable at the intended viewing size. Do not horizontally compress letters or uniformly shrink the entire page.
3. Expand or reshape the immediate text container, badge, background panel or decorative element into available whitespace. Move only local decoration and the text-side connector segment; preserve the associated feature and endpoint.
4. If fixed module dimensions still cannot fit the complete readable copy, use available native typography/composition or ask about a material layout change. Do not silently enlarge an A+ module, crop the product, discard a footnote or reorder the page.

For RTL scripts, apply correct shaping, bidi handling and local text alignment. Do not mirror the product, reverse Latin identifiers/numerals or automatically exchange the left/right page layout. For CJK and mixed scripts, respect appropriate punctuation and line breaking. Similar hierarchy does not require identical point sizes across scripts.

## 4. Choose the least disruptive supported method

With editable text/layers, replace text in those layers using existing host capabilities. With a flattened image, prefer available text-region editing or native composition that retains original product pixels, especially when product immutability is strict. Erase/reconstruct only text backgrounds where supported; never cover product details with a flat patch. A mask is not itself a guarantee of unchanged pixels outside it; inspect the result.

If only whole-image generation/editing is available, use the original as the identity/layout reference and give explicit preservation constraints. Inspect for product drift. Do not promise pixel identity from generative instructions; if strict preservation cannot be achieved, retain the source and report the limitation or request editable assets. Do not install a new renderer or change Accio's tool chain as an implicit requirement.

For existing long images, split only at natural module boundaries when needed, maintain context for edge-crossing features, and reassemble in original order with no missing seams. For existing listing or A+ modules, deliver localized versions of those modules in their original organization; do not apply the new-PDP long-image default. Multiple locales use the original source independently, not another translated image.

## 5. Prompt assembly

Fill this scaffold with the actual region map. Omit irrelevant labels and all placeholders:

"Asset type: Localization of [image role] into [locale]. Input images: [original source and roles]. Primary request: Replace only these marketing regions: [region/location: source -> exact destination; repeat for each region]. Canvas and composition: Preserve [canvas, module order, product/text placement, claim-to-feature relations]. Typography: Render destination strings verbatim with [script direction/glyph needs] and preserve hierarchy; wrap naturally instead of compressing letters or using unreadably narrow type. Product invariants: Preserve [product identity, pose, scale, position, markings] and [protected identifiers/values]. Allowed changes: Local line breaks, spacing and text-container/decoration adjustments within [available region]; preserve [callout endpoints] and keep the product unobscured. Avoid: New claims, untranslated editable text, changed product details, cropped copy or global redesign."

The critical map and constraints belong in the actual `prompt`, even when supported auxiliary fields repeat them. For a set, combine a shared glossary/style brief with each image's own mapping; follow [parallel-generation.md](parallel-generation.md). Prompt-only review shows source, destination and region correspondence; it cannot certify final image fidelity.

## 6. Acceptance and repair

Check three independent results: **language** (meaning, qualifiers, exact rendered strings, no omissions), **product** (structure, markings, pose/material/color, no redraw drift), and **layout** (same claim-to-feature association, fixed endpoints, readable copy, permitted local changes only). A fluent translation fails if the product changed. Inspect actual returned assets, not just a supplied translation table. Use OCR or source-region comparison only when available; unresolved text or geometry is unverified, not passed.

If whole-image generation changes protected product details or protected text, do not keep rerolling the entire composition. Prefer a supported local/native repair that retains original pixels; if that capability is absent, mark the preservation failure and retain the original asset. Repair only the affected text region or module, retaining the original identity source and correct siblings. Follow the existing repair budget. Deliver each source/locale pair with a stable association and report partial results. When no editable text exists, preserve the original and identify that no localization was needed.

## Small contrastive example

Source overlay: "Up to 12 hours". Target: German. Faithful concise copy: "Bis zu 12 Stunden". Preserve the qualification; "12 Stunden garantiert" invents a guarantee. If the line wraps, grow the existing label into spare space and adjust its leader start, while keeping the product and leader endpoint fixed. A physical "MODEL A12" mark remains unchanged. Never import this duration or model name into another product.
