# Model and Provider Connection in OpenHarness SaaS

All paid media generation, voice cloning, and hosted speech alignment in Hypit route through the OpenHarness SaaS model gateway via the `saas.gateway` Endpoint (`@openharness/provider-saas`). Local composition, HTML rendering, OpenCV image transforms, and FFmpeg operations run locally in the workspace runtime.

## Supported SaaS Capabilities

| Media Type | Hypit Package / Capability | Routed SaaS Behavior |
| --- | --- | --- |
| Image | `@hypit/gpt-image` (`gpt-image-2`) | Image generation and reference edits; excludes `5:4`/`4:5`/`3:1`/`1:3`/`9:21` at `2K` and `3:1`/`1:3`/`9:21` at `4K` |
| Image | `@hypit/nano-banana` (`nano-banana-2`, `nano-banana-pro`) | High-detail image generation and editing |
| Image | `@hypit/seedream` (`seedream-5-lite`) | Seedream image generation and editing |
| Video | `@hypit/seedance` (`seedance-2`, `seedance-2-fast`, `seedance-2-mini`, `seedance-2.5`) | Text-to-video, first/last frame, `referenceImage`, `referenceVideo`, `referenceAudio`, and `generateAudio` |
| Video | `@hypit/minimax-h3` (`minimax-h3`) | MiniMax H3 video generation (`768p` / `2k`, reference images/videos/audios, first/last frame) |
| Video | `@hypit/grok-imagine` (`grok-imagine-video`, `grok-imagine-video-1.5-preview`) | Grok video generation |
| Speech | `@hypit/fishaudio-speech` (`voice-design-1`, `voice-clone`), `@hypit/mimo-speech` (`mimo-v2.5-tts-voicedesign`, `mimo-v2.5-tts-voiceclone`), `@hypit/elevenlabs-speech` (`eleven_ttv_v3`) | Speech synthesis and zero-shot voice cloning routed through the SaaS audio gateway |
| Transcription | `@hypit/whisperx` (`whisperx-alignment`) | Hosted ASR alignment via SaaS `POST /api/v1/hypit/audio/transcriptions` (no local PyTorch/WhisperX download required) |

## Rules for Model Execution

1. **No external provider logins**: Do not prompt for HypiHub accounts, OAuth logins, or third-party API keys (`provider-hypihub`, `provider-tokendance`, `provider-hiapi`, `provider-pollo`, `provider-beatapi`, `provider-sume`, `provider-monid`).
2. **Task-scoped authorization**: The backend automatically provisions task-scoped gateway credentials in `.hypit/` for the active task thread.
3. **Billing & balance**: Every `saas.gateway` request reserves and settles user credits through the platform billing engine. Video models require purchased credit balance; if `hypit build` reports insufficient purchased credits or balance exhaustion, stop and report the error clearly to the user.
4. **Preflight checks**: Run `hypit plan` / `hypit doctor --runtime .hypit/saas-runtime.profile.json` (or `hypit.runtime.json`) before executing expensive video batches. `hypit pricing` queries the SaaS estimate endpoint directly.
