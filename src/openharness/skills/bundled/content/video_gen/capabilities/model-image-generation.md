# Model Image Generation

Read this only when calling an image model to generate or edit a still image. Reuse existing images directly; use image processing for cropping and format conversion, and drawing tools for SVG geometry

Use the currently available Manus image tools. First establish the purpose, subject, aspect ratio, reference images, and content to preserve; fill in nonessential details yourself. For an image-only task, deliver the image directly

## Model and output choices

Prefer GPT Image 2 for the first text-to-image master reference of a character or person, using the model identifier exposed by the current image tool schema

Select the model, resolution, reference inputs, and editing parameters from the actual tool schema. Choose enough resolution for the intended video framing and reuse, without increasing it merely as a substitute for a clear prompt or good source reference. If a preferred model or mode is unavailable, choose among the currently exposed options according to identity consistency, edit fidelity, quality, latency, and cost

## References and Consistency

Before preparing, generating, or editing reference images for video, read [asset design](../workflows/creative-shorts/02-asset-design.md). This applies to ads, UGC, product videos, and narrative shorts; reuse that guidance if already read for the same task. Asset design covers reference design and consistency methods; this page covers image-tool calls and parameters

1. **One master reference per person.** Reuse the approved master image for the same character. Derive face details, full-body supplements, and outfit changes from it through image-to-image or variation. When additional angles or details are needed, prefer combining the main view and supplemental views in one reference image, with every view inheriting the same identity. Product references follow the same [asset-design method](../workflows/creative-shorts/02-asset-design.md#combine-supplemental-views-and-details-in-one-reference-sheet)
2. **Assign each reference a role.** Specify which reference supplies character identity, composition, setting, style, or product appearance, and what the current image should inherit. Take only identity and clothing from a character image; let the current scene and storyboard determine the background and pose. Take only space, materials, and light from a location image; take only appearance and structure from a product image. Defining these boundaries lets you combine people, locations, and objects in a new frame
3. **Use accurate sources for accurate content.** For products, logos, webpages, phones, application UI, packaging, devices, and brand typefaces, use user-provided, official, or approved design images
4. **Edit only the target.** Specify the target region, person, or object while preserving all other identity, proportions, materials, background, and lighting

## Prompt Writing and Review

Write all prompt instructions in English, retaining the requested language for text that must appear verbatim. Organize the prompt as “purpose and subject → appearance or materials → setting, lighting, and composition → style → elements to preserve.” Describe visible details such as key-light direction, camera distance, skin texture, and material texture concretely

Check subject and reference consistency, product shape and markings, aspect ratio, and required text; check that transparent assets have a genuinely transparent background. Address critical issues together, then deliver once the image meets its intended purpose

Deliver an accessible image file. Reuse approved images as shot references for later video work and preserve their paths in the production manifest when assembly is needed
