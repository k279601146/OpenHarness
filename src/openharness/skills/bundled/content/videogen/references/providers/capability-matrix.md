# Videogen Provider Capability Matrix

`videogen_cli` is the single OpenHarness video tool. Model ids are routed by `scripts/videogen_runtime/registry.py`.

| Model family | Provider | Model ids and aliases | Generate | Image-to-video | First/last frame | References | Audio | Billing scheme |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Seedance | `seedance` | `seedance-*`, `doubao-seedance-*`, `seedance-1.5-pro` | Yes | Yes | Yes | Yes | Yes, when exposed by surface | Official Seedance dimensions: model, mode/input type, duration, resolution/ratio, provider usage when returned |
| Veo / video3 | `veo` | `veo-*`, `video3*` | Yes | Yes | Provider-specific | Limited references | Model-dependent audio | Official Google dimensions: model tier, resolution, duration seconds, provider usage when returned |
| Kling / keling | `kling` | `kling-*`, `keling-*` | Yes | Yes | Model/surface-specific | Model/surface-specific | Model/surface-specific | Official Kling dimensions: model, mode, resolution, duration, audio/voice options, provider usage when returned |

Do not use this v1 runtime for MiniMax Hailuo, Vidu, Wanxiang/Wan, Sora, Runway Gen, Luma, or Pika.

Credentials are provider-specific environment variables:

- Seedance: `SEEDANCE_VIDEO_API_KEY`, optional `SEEDANCE_VIDEO_BASE_URL`
- Veo/video3: `VEO_VIDEO_API_KEY`, optional `VEO_VIDEO_BASE_URL`
- Kling/keling: `KLING_VIDEO_API_KEY`, optional `KLING_VIDEO_BASE_URL`
