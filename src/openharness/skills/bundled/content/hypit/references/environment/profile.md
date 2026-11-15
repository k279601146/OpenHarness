# Runtime Profile in OpenHarness SaaS

OpenHarness automatically provisions both `.hypit/saas-runtime.profile.json` and (when `hypit` is enabled) `hypit.runtime.json` in the task workspace.

## Pre-Configured Endpoints

- `saas.gateway` (`@openharness/provider-saas`): Handles image, video, speech synthesis, voice cloning, hosted WhisperX speech alignment, and live SaaS credit pricing queries using the scoped workspace credential file `.hypit/saas-gateway.json`.
- `media.local` (`@hypit/media-local`): Runs FFmpeg/FFprobe media inspection, audio mixing, normalization, trims, and video assembly locally.
- `html.local` (`@hypit/provider-html-local`): Renders HTML/CSS motion graphics frames via headless Chromium.
- `image.opencv.local` (`@hypit/provider-image-opencv-local`): Runs local image transforms and processing.
- `@hypit/whisperx@1#whisperx-alignment`: Pre-bound in `bindings` to `saas.gateway` by default so `hypit transcribe` and `<whisperx:Alignment>` work immediately without downloading local WhisperX model weights; `whisperx.local` remains opt-in for local CPU/GPU runs.

## Operational Guidance

- Prefer running commands from the task workspace root so relative paths to `hypit.runtime.json` and `.hypit/saas-gateway.json` resolve cleanly.
- If `hypit.runtime.json` is absent in the current workspace, either pass `--profile .hypit/saas-runtime.profile.json` or copy `.hypit/saas-runtime.profile.json` to `hypit.runtime.json`.
- Do not hardcode upstream API keys, external gateway domains, or manual environment tokens in `hypit.runtime.json`.
- Keep `.hypit/` unedited for credentials and runtime state; place authored `.svml`, `.svs`, `.svrun`, and final exported `.mp4` files in the normal workspace directory.
