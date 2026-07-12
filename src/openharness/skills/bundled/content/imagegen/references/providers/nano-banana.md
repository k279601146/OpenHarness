# Nano Banana / Gemini Provider Notes

Nano Banana 系列通过 Gemini 风格图片 API 适配器执行：

- `nano-banana`
- `nano-banana-2`
- `nano-banana-pro`

## 何时选择

- 用户明确要求 Nano Banana、Gemini 图片模型或 Google 图片生成。
- 需要快速生成、参考图风格延展、自然语言理解较强的图片任务。
- 适合创意草图、广告图、社媒图、轻量编辑和图片条件生成。

## 参数选择

- 优先使用 `resolution` 与 `aspect_ratio`，例如 `resolution="2K"`、`aspect_ratio="16:9"`。
- 常用比例：`1:1`、`16:9`、`9:16`、`4:3`、`3:4`。
- `nano-banana` 旧模型通常按 1K 使用；`nano-banana-2` 和 `nano-banana-pro` 可根据模型能力尝试 2K/4K。
- 如果用户只说“高清”“2K”“4K”，把它放入 `resolution`，不要在 prompt 中只用自然语言表达。

## 编辑与参考图

- 参考图或编辑使用 `command="edit"` 并传 `images=[...]`。
- 在 prompt 中明确每张图的角色：主体参考、风格参考、编辑目标或构图参考。

## 失败处理

- 如果 Gemini 返回比例或分辨率不支持，保持用户意图，换成相近比例或降低分辨率后重试。
- 计费不依赖 provider 参数白名单；不要为了计费预检删除用户需要的比例或参考图。
