# Imagegen Provider Capability Matrix

`imagegen_cli` is the single OpenHarness image tool. Model ids are routed by the bundled Python registry in `scripts/imagegen_runtime/registry.py`.

| Model family | Provider | Tool model ids | Generate | Edit/reference | Pricing units |
| --- | --- | --- | --- | --- | --- |
| GPT Image | `gpt_image` | `gpt-image-2`, other `gpt-image-*` | Yes | Yes | 4.0 per output |
| Nano Banana / Gemini | `gemini` | `nano-banana`, `nano-banana-2`, `nano-banana-pro` | Yes | Yes | 3.0 per output |
| Doubao Seedream | `doubao` | `doubao-seedream-5-0-260128`, `doubao-seedream-5-0-lite-260128`, `doubao-seedream-4-5-251128`, `doubao-seedream-4-0-250828` | Yes | Yes | 2.0 per output |
| Kolors | `openai_compatible` | `kolors` | Yes | No guaranteed edit support | 1.0 per output |

Credentials are provider-specific environment variables:

- GPT Image: `GPT_IMAGEGEN_API_KEY`, optional `GPT_IMAGEGEN_BASE_URL`
- Nano Banana / Gemini: `NANO_BANANA_API_KEY`, optional `NANO_BANANA_BASE_URL`
- Doubao Seedream: `DOUBAO_IMAGE_API_KEY`, optional `DOUBAO_IMAGE_BASE_URL`
- Kolors: `KOLORS_IMAGE_API_KEY`, optional `KOLORS_IMAGE_BASE_URL`

`IMAGE_GEN_API_KEY` and `IMAGE_GEN_BASE_URL` are accepted as compatibility fallbacks for non-GPT providers.
