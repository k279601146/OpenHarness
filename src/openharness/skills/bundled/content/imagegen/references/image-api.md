# GPT Image parameter quick reference for `imagegen_cli`

本文件只描述 GPT Image provider 在 `imagegen_cli` 下的参数语义。不要用它绕过 SaaS 媒体模型网关，也不要直接调用 OpenAI SDK 或 HTTP API。

## Scope

- 适用模型：`gpt-image-2`、`gpt-image-1.5`、`gpt-image-1`、`gpt-image-1-mini`。
- 实际调用必须通过 `imagegen_cli`，由 runtime 注入媒体网关凭据并执行计费 reservation。
- 只传 provider 支持且当前任务确实需要的参数；失败后按错误原因调整参数，不要改走其他生成路径。

## Model summary

| Model | Quality | Input fidelity | Resolutions | Recommended use |
| --- | --- | --- | --- | --- |
| `gpt-image-2` | `low`, `medium`, `high`, `auto` | Image inputs always use high fidelity; do not set `input_fidelity` | `auto` or constrained `WIDTHxHEIGHT` | 默认 GPT Image 路径：高保真生成和编辑、文字密集图、复杂构图、身份敏感编辑 |
| `gpt-image-1.5` | `low`, `medium`, `high`, `auto` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | 需要原生透明背景且用户确认切换时使用 |
| `gpt-image-1` | `low`, `medium`, `high`, `auto` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | 历史兼容 |
| `gpt-image-1-mini` | `low`, `medium`, `high`, `auto` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | 低风险草稿和轻量预览 |

## `gpt-image-2` size rules

`gpt-image-2` 的 `size` 可以是 `auto` 或满足约束的 `WIDTHxHEIGHT`：

- 最大边不超过 `3840px`。
- 宽和高都是 `16px` 的倍数。
- 长边与短边比例不超过 `3:1`。
- 总像素数在 `655,360` 到 `8,294,400` 之间。

常用尺寸：

| Label | Size | Notes |
| --- | --- | --- |
| Square | `1024x1024` | 快速方图 |
| Landscape | `1536x1024` | 标准横图 |
| Portrait | `1024x1536` | 标准竖图 |
| 2K square | `2048x2048` | 较大方图 |
| 2K landscape | `2048x1152` | 宽屏输出 |
| 9:16 2K portrait | `1152x2048` | 常用竖屏输出 |
| 4K landscape | `3840x2160` | 4K 横图 |
| 4K portrait | `2160x3840` | 4K 竖图 |
| Auto | `auto` | 默认自动尺寸 |

如果用户只给比例，先按 provider 文档推导有效尺寸，再传 `size` 或 `aspect_ratio`。UI 层应把比例和分辨率分开处理。

## Core parameters

- `prompt`：图片需求。
- `model`：GPT Image 模型 ID。
- `n` / `num_images`：同一 prompt 的变体数量，必须与计费 reservation 意图一致。
- `size`：`auto` 或有效尺寸。`gpt-image-2` 支持灵活尺寸；旧模型只使用 `1024x1024`、`1536x1024`、`1024x1536` 或 `auto`。
- `quality`：`low`、`medium`、`high`、`auto`。
- `background`：输出透明行为，值为 `transparent`、`opaque`、`auto`。它不是视觉场景背景。
- `output_format`：`png`、`jpeg`、`webp`。
- `output_compression`：0-100，仅适用于 jpeg/webp。
- `moderation`：`auto` 或 provider 支持的其他值。

## Edit parameters

- `images`：一张或多张输入图片。GPT Image 通常最多支持 16 张，具体以上游返回为准。
- `mask`：可选蒙版。蒙版只适用于第一张输入图。
- `input_fidelity`：仅对支持的模型传 `low` 或 `high`；不要给 `gpt-image-2` 传该字段。

编辑 prompt 必须重复不变量，例如 `change only the background; keep the product and its edges unchanged`。

## Transparent backgrounds

`gpt-image-2` 不支持 `background=transparent`。默认策略是通过 `imagegen_cli` 生成纯色 chroma-key 背景，再用 `scripts/remove_chroma_key.py` 本地转 alpha。

只有在以下情况下，才询问用户是否切换到支持原生透明的模型，例如 `gpt-image-1.5`：

- 用户明确要求 true/native transparency。
- chroma-key 本地去底失败。
- 主体边缘过于复杂，例如头发、烟雾、玻璃、液体、半透明材质、反光物体或柔阴影。

切换前必须确认用户接受模型变化，并确认后台媒体网关已启用该模型。

## Output and safety

- `imagegen_cli` 负责解码、写文件、校验输出并发布 artifact。
- 输入图片和 mask 应小于 provider 限制；GPT Image 常见限制是单文件 50MB 以内。
- 大尺寸和高质量会增加延迟和成本，但 agent 不应通过隐藏参数绕过计费。
- 如果 provider 因不支持某个可选参数而失败，只有当该参数不是用户硬性要求时，才去掉该参数重试。
- 任何重试都仍必须通过 `imagegen_cli`。
