# Nano Banana / Gemini Provider Notes

Nano Banana 系列通过 Gemini 原生图片 API 执行：

- `nano-banana`
- `nano-banana-2`
- `nano-banana-pro`

官方参考：Google Gemini API image generation 文档。

## 何时选择

- 用户明确要求 Nano Banana、Gemini 图片模型或 Google 图片生成。
- 需要自然语言迭代、参考图扩展、轻量编辑、强语义理解或多轮视觉创作。
- 适合创意草图、广告图、社媒图、参考图风格延展和图片条件生成。

## API 字段

Gemini 图片生成使用原生 `generationConfig.imageConfig`：

- `aspectRatio`: 例如 `1:1`、`16:9`、`9:16`、`4:3`、`3:4`
- `imageSize`: 分辨率档位，例如 `1K`、`2K`、`4K`

Google 文档要求 K 值使用大写，例如 `1K`、`2K`、`4K`；不要传 `1k`、`2k`、`4k`。

`imagegen_cli` 参数映射：

- `resolution="1K" | "2K" | "4K"` -> Gemini `imageSize`
- `aspect_ratio="9:16"` -> Gemini `aspectRatio`
- `size="2K"` 也会作为 resolution 档位处理

## 参数选择

- 用户只说“高清”：优先 `resolution="2K"`。
- 用户只说“4K”：使用 `resolution="4K"`。
- 用户要求竖版 9:16：使用 `aspect_ratio="9:16"`，不要只在 prompt 里描述“竖图”。
- 老模型或 lite 模型可能只支持 1K；如果上游拒绝高分辨率，保留比例并降到 `1K` 或 `2K` 重试。

## 编辑与参考图

- 参考图或编辑使用 `command="edit"` 并传 `images=[...]`。
- 在 prompt 中标明每张图的角色：主体参考、风格参考、编辑目标或构图参考。

## 失败处理

- 如果 Gemini 返回比例或分辨率不支持，保留用户意图，换成相近比例或降低分辨率后重试。
- 不要为了计费预检删除用户需要的比例或参考图。
