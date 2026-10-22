---
name: image-prompt-guide
description: Accio 电商商品图片提示词生成与白底图/场景图工作流指南。覆盖商品抠图、场景融合、多国多语言主图套图、细节特写与光影控制。
metadata:
  display_name: 电商商品图提示词指南
  category: commercial_ads
  summary: 电商商品主图、场景融合与多国本地化视觉提示词指南
  version: 1.0.0
  triggers:
  - 电商商品图
  - 白底换场景
  - 主图提示词
  - 商品细节图
  - 亚马逊主图
  locales:
    en:
      display_name: E-Commerce Product Image Guide
      summary: Prompt guidelines for e-commerce product photos, background blend,
        and localized listings
    zh-Hant:
      display_name: 電商商品圖提示詞指南
      summary: 電商商品主圖、場景融合與多國本地化視覺提示詞指南
---

# Accio Ecommerce Image Generation

Produce usable merchant assets with accurate products, clear information, and the requested deliverables. Editing and creating images share one generation workflow. Select the supported Accio generation/edit mode, reference inputs, and parameters for the task; do not treat recoloring or text replacement as a separate business workflow.

## Accio Integration

Keep the installed identity `image-prompt-guide` and resolve resources relative to this Skill directory. Use Accio's existing `image_generate` and `image_edit` tools; this Skill supplies instructions, not a new service, model endpoint, SDK or agent framework. Preserve caller-supplied plans, source roles, image order and accepted decisions. The caller owns the larger marketing, product or video workflow. For a delegated step or dependent image set, read [accio-orchestration.md](references/accio-orchestration.md); do not restart its upstream planning.

## Language

- Write user-facing questions, progress, explanations, and delivery notes in the user's current conversation language. Follow an explicit response-language preference; otherwise follow their latest substantive message. An image-only message, quoted copy, brand name, or target market does not switch the conversation language.
- Image copy has its own language: use the requested output language; preserve supplied exact copy in its original script. If creating copy without a specified language, use the conversation language unless the destination makes another language unambiguous. Ask only when that choice materially changes the deliverable and remains unclear.
- Write model instructions in English while preserving literal display strings, names, units, and required punctuation. Do not translate those strings merely because these instructions are English. Keep right-to-left direction and script-specific typography when applicable.

## Working Method

1. **Resolve intent and inputs.** Distinguish editing an existing asset from creating a new composition with references, then choose single-output or set execution. These are intent decisions; Accio tool routing follows [generation-runtime.md](references/generation-runtime.md). Inspect actual source images and assign roles: base canvas, identity, attribute donor, style/layout, person or brand asset. Reuse caller decisions, exact copy, dimensions and output order.
2. **Read only relevant guidance.** Translation uses [image-translation.md](references/image-translation.md); other edits use [image-edits.md](references/image-edits.md). For a new commerce composition, select the matching scene reference in the table below and use its design-to-prompt pattern. A narrow edit does not need new design planning. Reuse guidance across a set; ask only for missing evidence or conflicting requirements that block a faithful result.
3. **Build the prompt from a short specification.** For image localization, build the text-region translation map and use its specialized prompt scaffold. For other edits, follow the operation table in [image-edits.md](references/image-edits.md), then read only the matching section in [edit-patterns.md](references/edit-patterns.md). Answer its short questions from the image and request; these are internal slots, not a questionnaire for the user. Build the prompt from those answers using the supplied sentence pattern. Keep decisive details through this conversion instead of summarizing them again. For new images, use the generation recipe below. Combine patterns only for changes the user actually requested.
4. **Check the prompt, then execute or preview.** Apply the pre-call check. Explicit prompt review follows [prompt-review.md](references/prompt-review.md) and stops before image calls; otherwise execute without extra approval. Read [generation-runtime.md](references/generation-runtime.md) for the full tool contract, and apply the Output size contract below to every call before the first generation. For multiple outputs, also read [parallel-generation.md](references/parallel-generation.md) before the first call: draft distinct complete prompts together, bind each to its sources, then submit the ready group through the supported dispatch mechanism before waiting on individual results. Do not repeat a plan-one/generate-one/wait-one loop for independent outputs. Keep actual dependencies and caller limits.
5. **Inspect, repair and deliver.** Compare the actual result with the requested change and protected content before judging polish. Check exact text, physical relationships, output count and required file properties. For commercial layouts, check readability at intended viewing size. Correct one diagnosed issue at a time while restating critical invariants. After one targeted repair fails, disclose the remaining limitation and offer a concrete alternative unless further iteration is authorized. Deliver actual assets with concise verified status in the user's language. An inaccessible result is unverified; a tool success or intended prompt is not proof of visual correctness.

## Output size contract

This contract decides the dimensions of every image call. Apply it proactively before the first generation, without waiting for the user to mention size.

- **Explicit user or destination pixels always win.** If the user requests `1024x1024`, generate and deliver exactly that.
- **Otherwise the default long edge is 2048 (2K quality), even for source-following edits.** Write the derived dimensions into the call itself: `size` in auto modes, `resolution: "2K"` in fallback modes.
- **Never inherit a low-resolution source as the call size.** A `1024x1024` source still generates at `2048x2048`, not `size: "1024x1024"`. Measuring the source extracts only its aspect ratio.
- **Omitting the size fields is a failure, not a neutral choice**: the runtime then silently applies its own 1K default.

Full dimension constraints (supported ratios, 16-multiple edges, area bounds, resize-on-delivery) remain in [generation-runtime.md](references/generation-runtime.md).

## New-image prompt recipe

For each output, resolve **buyer question, evidence, visual relationship, layout, copy, shared style**. The scene reference supplies choices and sentence patterns; use only the matching one. For example, a material benefit needs a supported surface detail and its association with the product, not just "premium quality". Copy these concrete decisions into the prompt without summarizing them back into adjectives.

Fill relevant existing labels: `Asset type: [purpose]. Input images: [actual source roles]. Primary request: Show [supported feature/action]. Canvas and composition: [selected layout and relationships]. Materials, color and style: [shared treatment]. Typography: Render [exact copy] at [location]. Product invariants: [verified identity/facts].` Omit unused labels and placeholders. A supplied product still requires reference-capable routing. Examples supply expression methods, not current product facts. For a specific composition, preserve the user's choices instead of applying a different recipe.

## Pre-call check

For an edit, resolve a compact specification: target and source role, desired end state, protected properties, and necessary dependent changes. Ground it in the actual image and user request. Keep only relevant facts; no reasoning transcript or exhaustive scene inventory.

Before submission, compare the exact final `prompt` string with that specification:

- **Coverage:** Each decisive user requirement and execution-critical visual finding has an explicit clause. Do not replace a resolved region, relation, orientation or exact string with "accurately" or "preserve structure".
- **Consistency:** No preservation clause forbids the requested change or its necessary consequences. Protect product identity without freezing a projection or pose that must change.
- **Binding:** Reference roles and order match actual inputs. Any coordinates describe the supplied source and its verified dimensions. Critical content is present in `prompt`, even when supported auxiliary fields repeat it. The size fields (`size` or `resolution`) are present in the actual call per [generation-runtime.md](references/generation-runtime.md); omitting them silently yields the runtime 1K default.
- **Fidelity:** No unsupported product facts or new creative requirements were introduced. Correct omissions or contradictions before calling; ask only for an unresolved material ambiguity.

This is an agent-side check, not a new API schema. In normal generation keep it internal. In explicit prompt review, expose the short specification and clause mapping so the user can distinguish source-understanding errors from prompt-construction errors.

## Facts and Scope

User-provided or verified product information establishes facts. Reference examples suggest expression, not specifications. Do not import sample brands, performance numbers, certifications, testimonials, accessories, or hidden components. Visual choices may be inferred when they do not change product meaning. Explicitly requested concept variants may change the designated attributes; do not present them as verified inventory.

For existing assets, preserve content outside the requested scope, including on-product labels and unrelated overlays. Allow consequences necessary to realize an authorized change; preserving identity does not require preserving its original pixel projection. Do not ask about every visible mark. Ask only if the request requires resolving a real conflict. One standing exception: if an edit source carries a canvas-overlay logo, watermark or QR code that the request never mentions, ask keep-or-remove before editing, then follow the answer literally (see [image-edits.md](references/image-edits.md)). If the user requests a change incompatible with a verified destination requirement, explain the conflict without silently changing their design or claiming compliance.

Keep planning proportional. For a set, a short internal output list with one purpose per image is usually sufficient. Distinguish a set of separate files from a collage. Count tool results and delivered assets, not just planned prompts. A follow-up normally edits the selected result and preserves accepted work.

## Reference Selection

| Need | Read |
|---|---|
| Accio tool/mode mapping, prompt assembly, supported parameters, size or delivery handling | [generation-runtime.md](references/generation-runtime.md) before the first image call; reuse while the contract is unchanged |
| Handoff from another Accio Skill, dependent outputs, partial results or resuming a run | [accio-orchestration.md](references/accio-orchestration.md) |
| Translate existing main/listing/detail/A+ images; preserve products and adapt local text layout | [image-translation.md](references/image-translation.md) |
| Multiple prompts, locales, dependencies and concurrent generation | [parallel-generation.md](references/parallel-generation.md) |
| Shared evidence-to-layout decisions or consistency across different scene types | [design-patterns.md](references/design-patterns.md); scene-specific patterns below remain the direct entry points |
| Explicit prompt-only preview, diagnostic clause mapping and later execution | [prompt-review.md](references/prompt-review.md) |
| Selected edit operation: short questions, sentence pattern and contrastive examples | [edit-patterns.md](references/edit-patterns.md), matching section only |
| All edits: source understanding, constraint priority, proportional structural checks and repair | [image-edits.md](references/image-edits.md) |
| Main/hero, feature, detail, fit, contents, comparison or product image set | [product-images.md](references/product-images.md): select a buyer question and its prompt pattern |
| Category-specific visual explanation or wearing/use relationships | Relevant entry in [commerce-recipes.md](references/commerce-recipes.md) |
| Promotional poster, launch, banner or social carousel | [marketing-images.md](references/marketing-images.md): message hierarchy and page roles |
| Detail page, A+, or information-dense long image | [detail-pages.md](references/detail-pages.md): module selection, split/overlay/table patterns and assembly |
| Typography, composition or material treatment needs a concrete direction | Relevant entry in [visual-recipes.md](references/visual-recipes.md) |
| New logo, mascot, brand mockup or reuse of an existing brand asset | [brand-assets.md](references/brand-assets.md) |
| Technical illustration, tech pack or process diagram | [technical-visuals.md](references/technical-visuals.md) |

These references are conditional guidance, not a checklist to load in full. They cannot expand the user's scope or override their explicit requirements.
