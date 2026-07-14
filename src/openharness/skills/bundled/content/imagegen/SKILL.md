---
name: "imagegen"
description: "Generate or edit raster images for OpenHarness SaaS through imagegen_cli. Use when an agent should create a bitmap asset such as a photo, illustration, texture, sprite, product mockup, UI mockup, infographic, or transparent-background cutout. Do not use when the task is better solved by editing existing SVG/vector/code-native assets or building deterministic HTML/CSS/canvas output."
---

# Image Generation Skill

本技能用于在 OpenHarness SaaS 中生成或编辑位图资产。所有实际生成都必须通过 `imagegen_cli` 完成。

## SaaS 运行规则

- 读取本技能不等于生成图片。只有 `imagegen_cli` 成功返回 artifact 路径后，才可以声明图片已生成。
- `imagegen_cli` 是 SaaS 中唯一允许的图片生成/编辑入口。它通过后端媒体模型网关路由 GPT Image、Nano Banana/Gemini、Doubao Seedream 和 Kolors，并负责 artifact 发布。
- 不要调用 Codex 内置 `image_gen`，不要用 `bash` 直接运行 `scripts/image_gen.py`，不要写一次性 SDK 脚本，也不要直接请求第三方图片 API。
- 不要调用旧媒体工具，例如 `gen_creative_image`、`edit_image`、`image_from_reference`。
- 媒体密钥、base URL、上游模型映射由 SaaS 后台媒体模型网关注入。不要要求用户在聊天中粘贴密钥，也不要新增 provider 专用环境变量路径。
- 计费由服务端在 `imagegen_cli` 执行前后按可信输出张数和尺寸档位处理。不要为了绕开预检而降低输出张数、隐藏 provider 字段或把 provider request body 塞进 prompt/metadata。
- 如果 `imagegen_cli` 失败或缺少依赖、密钥、输出文件，直接说明精确失败原因。不要切换到其他生成路径。
- `imagegen_cli` 成功后，不要额外生成沙箱链接、下载链接或“生成文件”章节。SaaS UI 会通过 artifact 事件渲染图片。
- 如果 `imagegen_cli` 返回 `delivery_required=false` 或 `do_not_deliver_artifact=true`，不要再把同一路径作为独立文件调用 `deliver_artifact`。
- SaaS 中生成媒体不会自动复制进 E2B。只有工具或 runtime 明确物化了当前任务可访问的沙箱路径时，才使用该路径继续处理。

## Provider 选择

- 用户显式指定模型时，把该模型 ID 原样传给 `imagegen_cli.model`，并读取对应 provider 文档。
- UI 已选择图片模型且 `is_model_auto_mode=false` 时，可以省略 `model`，让 runtime 使用 UI 偏好；仍应按该 provider 文档选择参数。
- 只有用户未指定模型，且 UI 没有明确非自动模型偏好时，才读取 `references/providers/capability-matrix.md` 辅助选型。
- 已知 provider 时，只读取需要的 provider 文件：
  - `gpt-image-2`、`gpt-image-*`：`references/providers/gpt-image.md`
  - `nano-banana`、`nano-banana-pro`、Gemini 图片模型：`references/providers/nano-banana.md`
  - `doubao-seedream-*`、Seedream 图片模型：`references/providers/doubao-seedream.md`
  - `kolors`、Kwai-Kolors：`references/providers/kolors.md`
- 不要把 capability matrix 当尺寸白名单。具体 `size`、`aspect_ratio`、`resolution`、`image_size` 等字段以 provider 文档和 runtime spec 为准。

## 何时使用

- 生成新图片：概念图、产品图、封面、网站 hero、插画、贴图、sprite、广告图、信息图。
- 用一张或多张参考图生成新图片，参考风格、构图、情绪、主体或品牌感。
- 编辑现有图片：替换背景、移除/替换物体、局部修改、合成、多图融合、透明背景。
- 为同一任务生成多张资产或多个变体。

## 何时不用

- 扩展或匹配仓库中的 SVG/vector 图标、logo 系统或代码原生插画。
- 生成简单图形、流程图、线框图、UI 占位图，且用 SVG、HTML/CSS 或 canvas 更确定。
- 源文件已经是可编辑的原生格式，且只需要小范围确定性修改。
- 用户明确要求矢量、代码或可复现结构化输出。

## 执行决策

先判断两个问题：

1. 意图：是生成新图，还是编辑现有图？
2. 数量：是一张资产，还是多张资产/变体？

意图判断：

- 用户要求修改现有图片并保留其中一部分时，使用 `command="edit"`。
- 用户给图只是作为风格、构图、情绪或主体参考，且没有要求修改原图时，使用 `command="generate"` 并把图片作为参考输入。
- 没有输入图片时，使用 `command="generate"`。

数量判断：

- 多个不同资产应分别调用 `imagegen_cli`，每个资产使用自己的 prompt 和语义化输出名。
- `n` / `num_images` 只用于同一 prompt 的多个变体，不要用它替代不同资产的独立 prompt。
- 如果工具 schema 暴露批处理能力，只有在用户明确需要批量 API/JSONL 风格控制时才使用；普通“批量生成几张图”不等于必须走批处理。

## 工作流

1. 选择 provider 或确认 UI 模型偏好。
2. 读取对应 provider 文档；只有需要选型时才读取 capability matrix。
3. 判断 `generate` 或 `edit`。
4. 收集 prompt、精确文字、约束、避免项、输入图片和每张图片的角色。
5. 按 provider 文档选择 `model`、`size`、`aspect_ratio`、`resolution`、`quality`、`background`、`output_format`、`n` 等参数。
6. 文生图调用 `imagegen_cli`，传 `command="generate"`、`prompt` 和 `out`。
7. 编辑或参考图调用 `imagegen_cli`，传 `command="edit"`、`images=[...]`、`prompt` 和 `out`。
8. 输出路径默认放在 `output/imagegen/`，除非用户指定目标位置。
9. 不覆盖已有资产，除非用户明确要求替换；否则使用 `hero-v2.png`、`icon-edited.png` 这类版本化文件名。
10. 检查返回结果是否满足主体、风格、构图、文字准确性、编辑不变量和避免项。
11. 需要迭代时只做一个针对性变化，并重新强调关键约束。
12. 项目会引用的最终资产必须落在工作区可引用位置，不能只停留在临时 artifact 路径。
13. 最终回复简要说明生成/编辑结果和关键参数；不要重复发送 UI 已经接收的 artifact 链接。

## `imagegen_cli` 常用参数

参数名以实际工具 schema 为准；以下是 agent 选择参数时的语义边界。

- `command`：`generate` 或 `edit`。
- `prompt`：完整图片需求。把视觉背景、主体、风格、构图、文字和约束写在这里。
- `images`：编辑目标或参考图列表。每张图在 prompt 中标明角色，例如 `Image 1: edit target`。
- `model`：用户显式指定模型时原样传入；UI 已有非自动模型偏好时通常省略。
- `out`：最终输出路径，默认使用 `output/imagegen/<semantic-name>.png`。
- `size` / `aspect_ratio` / `resolution`：按 provider 文档选择。用户明确要求比例或尺寸时，优先转成 provider 推荐的显式参数。
- `n` / `num_images`：同一 prompt 的变体数量，必须与计费 reservation 意图一致。
- `quality`、`input_fidelity`、`mask`、`background`、`output_format`：只在所选 provider 支持时传入。不要把不支持的参数硬塞给 provider。
- `background` 只表示输出透明行为，可用值是 `transparent`、`opaque`、`auto`。视觉场景背景应写进 prompt 的 `Scene/backdrop`，不要写进 `background`。

GPT Image 细节见 `references/image-api.md`；非 GPT provider 细节见各自 provider 文档。


## Scenario Classification

Assign one primary scenario and any secondary scenario before prompting or editing.

| Scenario | Use when the visual is for | Success criterion |
| --- | --- | --- |
| Website or landing page | Hero images, section visuals, blog covers, page visuals | Layout fit, whitespace, brand tone, text-safe area |
| Product or commerce | Product renders, packaging shots, marketplace images | Product accuracy, material credibility, clean presentation |
| Marketing or social | Ads, posters, campaign visuals, thumbnails | Strong focal point, emotional clarity, readable hierarchy |
| UI or app mockup | App screens, dashboards, interface concepts | Plausible layout, consistent controls, legible structure |
| Logo or icon | Brand marks, app icons, favicons, symbolic assets | Simplicity, recognizability, scalability |
| Game or asset pack | Sprites, props, tiles, characters, backgrounds | Reusable silhouette, consistent perspective, clean edges |
| Character or portrait | People, mascots, avatars, recurring characters | Identity consistency, natural anatomy, intended mood |
| Diagram or infographic | Explainers, conceptual visuals, structured visuals | Correct structure, readable labels, low ambiguity |
| Transparent asset | Cutouts, stickers, overlays, compositing assets | Clean alpha, complete subject, no unwanted background |
| Precise image edit | Modification of an existing image | Change only requested regions; preserve everything else |
| Image upscale or restore | Upscaling, restoring, or enhancing resolution of an existing image | Higher resolution and clarity while strictly preserving original content, style, and identity |

Read `references/scene-decision-matrix.md` when scenario tradeoffs are unclear or when a request spans multiple media.

## Cross-Cutting Policies

### UI images

Default UI-related image requests to direct image generation as visual mockups. Do not create HTML/CSS/React, render a webpage, and screenshot it merely because the image resembles an interface. Use code, web/app development, or screenshot workflows only when the user explicitly asks for source code, editable front-end files, interactivity, deployment, a working prototype, or deterministic layout output.

When prompting UI images, specify screen type, navigation, information architecture, component hierarchy, realistic spacing, device or browser frame, light/dark mode, brand palette, and exact UI labels or sample data. Describe the output as a visual mockup; do not imply functional software.

### Text-bearing visuals

Default text-bearing visual image requests to direct generation of the complete final image, with the text rendered by the image generation model itself. Treat Chinese, English, Japanese, Korean, Arabic, and other writing systems as first-class generation targets; do not assume non-English or dense copy requires a separate text overlay workflow. Text presence, language, or amount of copy is never a reason to generate a blank/background-only image and then add text with Python, scripts, canvas, HTML, SVG, PIL, or manual compositing.

Strictly forbidden: do not create a poster, menu, infographic, UI mockup, card, flyer, banner, or other text-bearing image by first generating an empty background and then overlaying the required text programmatically. This prohibition applies especially to Chinese text and multilingual layouts. Use deterministic layout or post-processing only when the user explicitly asks for editable source/layout files, pixel-perfect corporate typography, print-production files, legally exact fine print, exact long tables, machine-readable diagrams, or source-controlled design assets; even then, do not present that route as a workaround for Chinese or non-English text generation.

Before prompting, organize meaningful copy into title, subtitle, sections, labels, callouts, CTA, footnotes, and UI labels as appropriate. Preserve exact proper nouns, prices, dates, numbers, Chinese characters, punctuation, and required terminology. Reduce redundant wording only when it harms visual readability and is not user-required.

Verify generated text against the user-stated requirements: required wording, language, hierarchy, placement, omissions, duplications, and critical numbers/dates/names. Do not run a separate generic garbled-text audit. If one or two targeted generations still fail critical text accuracy and exactness is required, regenerate with a narrower text block, reduce visual density, or ask the user whether exact editable layout/source files are required; do not fall back to Python/scripted text overlay as the default correction path.

### Static layout/code screenshot

Use a static layout or code screenshot workflow only when the user explicitly needs deterministic static visual layout, exact typography or placement, reproducible image composition, editable layout/source files, or source-controlled design assets, but does not need functional software, deployment, data interactivity, or editable application source. Do not use this route merely because the visual resembles a UI, contains Chinese/non-English text, or contains a lot of text.

### Multi-item visual sets

For card decks, icon packs, sticker packs, poster sets, product image sets, game asset packs, or similar requests, deliver **one standalone final image per requested item** by default. Do not deliver process images, raw subject-only illustrations, contact sheets, stitched previews, A4 sheets, PDFs, or combined boards unless explicitly requested. Archives may supplement many files, but must not replace direct access to final individual images when the user asked for images.

### Image edits and references

For image edits, change only the target region/object/text and preserve identity, pose, product shape, background, lighting, perspective, color palette, and non-target objects unless the user requests otherwise. When the user says “use this as reference,” match only the relevant dimension: identity, style, composition, color, or product form.

### Scenario-specific guardrails

| Scenario | Guardrail |
| --- | --- |
| Logo/icon | Start with a simple symbol or mark. Do not rely on generated typography for precise brand wordmarks unless the user accepts concept-only output. |
| Product image | Preserve product shape, labels, proportions, materials, and legally sensitive marks. Do not invent branding unless requested. |
| Transparent asset | Require a true transparent background, complete subject, clean alpha, and no colored fringe or unwanted shadow. |
| Character | Define stable identity anchors: age, face shape, hair, outfit, silhouette, palette, and style. |
| Precise chart | Never use AI image generation for the quantitative plot itself. |

## Production Brief Workflow

Build a short internal brief before generating or editing.

| Brief field | Determine |
| --- | --- |
| Purpose | What the visual must accomplish |
| Medium | Website, app, ad, marketplace, slide, game, print, social, or asset library |
| Subject | Main object, person, environment, interface, product, or concept |
| Composition | Orientation, framing, whitespace, safe area, hierarchy, camera angle, screen/device context |
| Style | Photographic, vector, 3D, editorial, flat, pixel art, brand style, or reference-matched |
| Text/content | Exact wording, language, hierarchy, labels, UI copy, callouts, or “no text” |
| Constraints | Aspect ratio, dimensions, transparency, brand colors, preservation requirements, excluded objects |
| Acceptance risks | Errors that would make the result unusable |

Ask only for missing essential information. If nonessential details are unspecified, make a reasonable assumption and proceed.

Use this prompt structure for new visuals:

```text
Create [image type] for [use case and audience].
Subject: [specific subject, interface, product, scene, or concept].
Composition: [framing, orientation, focal point, safe area, background depth, screen/device layout if relevant].
Style: [visual style, lighting, material, color palette, brand tone].
Text/content to render: [organized exact content block, UI labels, section labels, CTA, or “no text”].
Constraints: [aspect ratio, transparency, text handling, elements to include/exclude].
Avoid: [scenario-specific failure modes].
```

Use this prompt structure for edits:

```text
Edit the provided image. Change only [target region/object/text].
Preserve [identity, pose, product shape, background, lighting, perspective, color palette, other objects].
New result should [desired outcome].
Text/content to render if relevant: [exact replacement text and location].
Avoid: [unwanted changes, artifacts, text errors, style drift].
```

Read `references/sample-prompts.md` for scenario-specific prompt structures.

## Lightweight Validation and Delivery

Do a **lightweight pass/fail check** before delivery, not an open-ended audit. Confirm only that the result satisfies the user's explicit request, the selected route is correct, and there is no obvious fatal defect that would make the artifact unusable. Do not perform forensic inspection, crop local regions for preview, run scripts to locate labels, search fonts, create masks, compare tiny details, or repeatedly re-open intermediate files unless the user requested that workflow or a visible critical failure blocks delivery.

If a critical requirement fails, correct only the single most important failure with one focused edit/regeneration or an appropriate route change. Do not keep refining for subjective polish, minor crop preferences, tiny spacing issues, uncertain text micro-errors, or speculative improvements. For text-bearing visuals, a quick visual check of requested headline/labels/numbers is enough; do not run a generic garbled-text audit or build a scripted correction pipeline.

Use deterministic image processing for operations where no new visual content is needed: downscaling, trimming, format conversion, or compression. When a resize or crop implies a new aspect ratio, default to preserving all content unless the user explicitly accepts edge loss; use AI editing to reconstruct or adapt the image when content must not be lost.

Deliver the artifact that matches the selected route: Mermaid source for Mermaid requests, chart image and source data/code as appropriate for Python plots, implementation files for code/demo/web/app requests, static layout images/source when requested, and final image files for AI generation or editing. Once the requested artifact has been delivered, **stop**. Do not continue generating extra variants, backup versions, additional fixes, or follow-up improvements after final delivery unless the user asks for them. Briefly state only essential scenario assumptions or known limitations that affect use.


## Reference map

- `references/providers/capability-matrix.md`：仅在需要选模型时读取。
- `references/quality-checklist.md`：lightweight pass/fail check。
- `references/providers/*.md`：provider-specific 参数、尺寸、失败重试和安全边界。
- `references/providers/specs/*.json`：runtime 使用的机器可读 provider spec，必须与 Markdown 同步。
- `references/image-api.md`：GPT Image 在 `imagegen_cli` 下的参数速查。
- `scripts/remove_chroma_key.py`：纯色背景转透明的本地后处理 helper。
