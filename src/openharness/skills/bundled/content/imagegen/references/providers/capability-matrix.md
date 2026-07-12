# Imagegen Provider Capability Matrix

本目录说明 `imagegen_cli` 的执行能力和 Agent 参数选择方式，不是服务端计费准入规则。SaaS 计费只由后端在请求上游前按可信的输出张数和 `billing_size_tier` 预检、预占，并在成功后提交扣费。

| Model family | Provider | Tool model ids | Generate | Edit/reference | Notes |
| --- | --- | --- | --- | --- | --- |
| GPT Image | `gpt_image` | `gpt-image-2`, other `gpt-image-*` | Yes | Yes | 最适合高保真、文字密集、复杂编辑；详见 `gpt-image.md`。 |
| Nano Banana / Gemini | `gemini` | `nano-banana`, `nano-banana-2`, `nano-banana-pro` | Yes | Yes | 使用 Gemini image API 风格的 `resolution + aspect_ratio`；详见 `nano-banana.md`。 |
| Doubao Seedream | `doubao` | `doubao-seedream-5-0-260128`, `doubao-seedream-5-0-lite-260128`, `doubao-seedream-4-5-251128`, `doubao-seedream-4-0-250828` | Yes | Yes | 适合中文语境、电商和社媒图；详见 `doubao-seedream.md`。 |
| Kolors | `openai_compatible` | `kolors` | Yes | No guaranteed edit support | 适合轻量开放模型和固定比例生成；详见 `kolors.md`。 |

Credentials come from the SaaS media model gateway:

- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_API_KEY`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_BASE_URL`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_MODEL_ID`.
- Do not use provider-specific environment variables for SaaS media generation.

Agent 执行规则：

- 用户指定模型时，将该模型 ID 原样传给 `imagegen_cli.model`。
- 用户没有指定模型时，省略 `model`，由运行时使用 UI 或线程偏好。
- 需要具体尺寸、比例、质量或参考图时，先读取本文件，再按 provider 文件选择参数。
- 如果 provider 返回参数错误，不要改写计费；根据错误调整 `imagegen_cli` 参数后重试。
