# Imagegen Provider Capability Matrix

本文件只用于“需要选择模型”时的快速概览，不是每次生成都要读取的参数表。

如果用户已经显式指定图片模型，或 UI 已选择图片模型且 `is_model_auto_mode=false`，不要先读本矩阵。直接使用该模型，并读取对应 provider 文档：

- `gpt-image-2` / `gpt-image-*` -> `gpt-image.md`
- `nano-banana` / `nano-banana-2` / `nano-banana-pro` -> `nano-banana.md`
- `doubao-seedream-*` -> `doubao-seedream.md`
- `kolors` -> `kolors.md`

| Model family | Provider | Tool model ids | Generate | Edit/reference | Best fit |
| --- | --- | --- | --- | --- | --- |
| GPT Image | `gpt_image` | `gpt-image-2`, other `gpt-image-*` | Yes | Yes | 高保真、文字密集、复杂编辑、参考图保持、灵活尺寸 |
| Nano Banana / Gemini | `gemini` | `nano-banana`, `nano-banana-2`, `nano-banana-pro` | Yes | Yes | Gemini 原生图像生成/编辑、自然语言迭代、参考图扩展 |
| Doubao Seedream | `doubao` | `doubao-seedream-5-0-260128`, `doubao-seedream-5-0-lite-260128`, `doubao-seedream-4-5-251128`, `doubao-seedream-4-0-250828` | Yes | Yes | 中文市场、电商图、社媒封面、多图参考、组图生成 |
| Kolors | `kolors` | `kolors` | Yes | No guaranteed edit support | 快速文生图、固定官方尺寸、中文语义、轻量生成 |

Credentials come from the SaaS media model gateway:

- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_API_KEY`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_BASE_URL`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_MODEL_ID`.
- Do not use provider-specific environment variables for SaaS media generation.

Agent 执行规则：

- 用户指定模型时，把该模型 ID 原样传给 `imagegen_cli.model`。
- UI 已选模型且非自动模式时，可以省略 `model`，由 runtime 使用 UI 偏好；但参数选择仍按该 provider 文档执行。
- 只有用户没有指定模型，且 UI 没有明确非自动偏好时，才使用本矩阵帮助选型。
- 不要把本矩阵当作尺寸白名单。具体 `size`、`aspect_ratio`、`resolution`、`image_size` 等字段以 provider 文档和官方 API 语义为准。
