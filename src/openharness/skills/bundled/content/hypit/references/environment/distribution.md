# Hypit Distribution & Workspace Delivery in OpenHarness SaaS

Hypit commands (`hypit doctor`, `hypit plan`, `hypit pricing`, `hypit build`, `hypit run`, `hypit check`) run via the pre-installed Node.js (>= 22.15) runtime in the host or sandbox environment.

## Checking Environment Readiness

1. Verify `node --version` is `>= 22.15` and `hypit --version` succeeds.
2. Inspect `.hypit/saas-runtime.profile.json` or `hypit.runtime.json` in the workspace before rewriting any runtime configuration.
3. Run `hypit doctor --runtime hypit.runtime.json` (or `--runtime .hypit/saas-runtime.profile.json`) when diagnosing local tools such as Chromium or FFmpeg.
4. Keep all intermediate runtime cache files inside `.hypit/` so workspace artifact synchronization only captures your final video deliverables (`.mp4`, preview stills, or requested project bundles).
