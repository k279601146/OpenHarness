# Videogen Provider Capability Matrix

`videogen_cli` is the single Bahew video tool. Model ids are routed by `scripts/videogen_runtime/registry.py`.

| Model family | Provider | Model ids and aliases | Generate | Image-to-video | First/last frame | References | Audio | Billing scheme |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Seedance | `seedance` | `seedance-*`, `doubao-seedance-*`, `seedance-1.5-pro` | Yes | Yes | Yes | Yes | Yes, when exposed by surface | Official Seedance dimensions: model, mode/input type, duration, resolution/ratio, provider usage when returned |
| Veo / video3 | `veo` | `veo-*`, `video3*` | Yes | Yes | Provider-specific | Limited references | Model-dependent audio | Official Google dimensions: model tier, resolution, duration seconds, provider usage when returned |
| Kling / keling | `kling` | `kling-*`, `keling-*` | Yes | Yes | Model/surface-specific | Model/surface-specific | Model/surface-specific | Official Kling dimensions: model, mode, resolution, duration, audio/voice options, provider usage when returned |

Do not use this v1 runtime for MiniMax Hailuo, Vidu, Wanxiang/Wan, Sora, Runway Gen, Luma, or Pika.

Credentials come from the SaaS media model gateway:

- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_API_KEY`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_BASE_URL`.
- The runtime injects `OPENHARNESS_MEDIA_GATEWAY_MODEL_ID`.
- Do not use provider-specific environment variables for SaaS media generation.
