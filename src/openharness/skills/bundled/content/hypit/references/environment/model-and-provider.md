# Model and Provider Connection in OpenHarness SaaS

All paid media generation in Hypit is routed through the OpenHarness SaaS model gateway via the `saas.gateway` Endpoint (`@openharness/provider-saas`). Local composition, HTML rendering, OpenCV image transforms, FFmpeg operations, and WhisperX speech alignment run locally in the workspace runtime.

## Supported SaaS Capabilities

| Media Type | Hypit Package / Capability | Routed SaaS Behavior |
| --- | --- | --- |
| Image | `@hypit/gpt-image` (`gpt-image-2`) | Image generation and reference edits; excludes `5:4`/`4:5`/`3:1`/`1:3`/`9:21` at `2K` and `3:1`/`1:3`/`9:21` at `4K` |
| Image | `@hypit/nano-banana` (`nano-banana-2`, `nano-banana-pro`) | High-detail image generation and editing |
| Image | `@hypit/seedream` (`seedream-5-lite`) | Seedream image generation and editing |
| Video | `@hypit/seedance` (`seedance-2`, `seedance-2-fast`, `seedance-2-mini`, `seedance-2.5`) | Text-to-video, first/last frame, and image references (`referenceVideo` and `referenceAudio` are unsupported) |
| Video | `@hypit/grok-imagine` (`grok-imagine-video`, `grok-imagine-video-1.5-preview`) | Grok video generation |
| Speech | `@hypit/fishaudio-speech` (`voice-design-1`), `@hypit/mimo-speech` (`mimo-v2.5-tts-voicedesign`), `@hypit/elevenlabs-speech` (`eleven_ttv_v3`) | Speech synthesis routed through the SaaS audio gateway |

## Rules for Model Execution

1. **No external provider logins**: Do not prompt for HypiHub accounts, OAuth logins, or third-party API keys (`provider-hypihub`, `provider-tokendance`, `provider-hiapi`, `provider-pollo`, `provider-beatapi`, `provider-sume`, `provider-monid`).
2. **Task-scoped authorization**: The backend automatically provisions task-scoped gateway credentials in `.hypit/` for the active task thread.
3. **Billing & balance**: Every `saas.gateway` request reserves and settles user credits through the platform billing engine. Video models require purchased credit balance; if `hypit build` reports insufficient purchased credits or balance exhaustion, stop and report the error clearly to the user.
4. **Preflight checks**: Run `hypit plan` / `hypit doctor --runtime .hypit/saas-runtime.profile.json` (or `hypit.runtime.json`) before executing expensive video batches. `hypit pricing` queries the SaaS estimate endpoint directly.
