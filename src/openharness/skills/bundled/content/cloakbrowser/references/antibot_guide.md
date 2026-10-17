# CloakBrowser Anti-Bot & Bypass Guide

This reference provides actionable strategies for defeating complex anti-bot, behavioral detection, and CAPTCHA systems when scraping or automating with CloakBrowser.

---

## 1. Cloudflare Turnstile

Cloudflare Turnstile evaluates browser fingerprinting (C++ patches handle this), network timing, and interaction behavior.

### Challenge Types
1. **Non-interactive / Invisible**:
   - CloakBrowser automatically resolves invisible Turnstile challenges without user interaction because the TLS and C++ fingerprint matches genuine Chromium.
   - Best practice: Always wait for `networkidle` or wait 3–5 seconds after `page.goto()`.
2. **Managed Challenges (Checkbox)**:
   - When a Turnstile iframe appears with an interactive checkbox:
     ```python
     # Wait for challenge iframe if present
     turnstile_frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
     box = turnstile_frame.locator("input[type='checkbox'], #challenge-stage")
     if box.is_visible(timeout=5000):
         # humanize=True moves the cursor along a natural Bézier curve
         box.click()
         page.wait_for_load_state("networkidle", timeout=15000)
     ```
   - **Crucial**: Ensure `humanize=True` is active when launching the browser or context.

---

## 2. reCAPTCHA v3 & Behavioral Scoring

reCAPTCHA v3 does not display a puzzle; it assigns a risk score between `0.0` (bot) and `1.0` (human).
- Stock Playwright typically scores `0.1`.
- CloakBrowser achieves `0.9` on standard benchmarks.

### Key Factors for High Scores:
- **Avoid Instant CDP Input**: Automated `page.click()` or `page.fill()` without delay can degrade the score. Use `humanize=True` which automatically injects natural jitter, typing delays, and curved mouse paths.
- **Warm Profiles**: A persistent profile (`launch_persistent_context`) with accumulated browsing cache, local storage, and history scores significantly higher than ephemeral blank profiles.

---

## 3. Fingerprint & Profile Persistence

CloakBrowser saves a persistent fingerprint seed in `.cloakbrowser-seed` within the profile directory.

- Profile location:
  `$CLOAKBROWSER_PROFILE_ROOT/<profile_name>`
  (e.g., `/home/user/.cache/openharness/cloakbrowser/profiles/my_profile`)
- When reusing this directory with `launch_persistent_context()`, the browser presents the **exact same hardware & browser identity** to target servers.
- To reset or rotate identity for a new clean persona, simply delete `.cloakbrowser-seed` or create a new profile subfolder.

---

## 4. Proxies and GeoIP Alignment

Anti-bot systems compare the TCP/IP exit IP with the browser's reported timezone, locale, and WebRTC candidate IP. A mismatch (e.g. US IP with Shanghai timezone) is an immediate bot red flag.

### Automatic Alignment with `geoip=True`:
```python
browser = launch(
    proxy="http://user:pass@residential-proxy:port",
    geoip=True,    # Auto-resolves timezone and locale to match proxy IP
    humanize=True,
    headless=True,
)
```
- CloakBrowser automatically sets internal C++ timezone and locale flags matching the exit IP.
- CloakBrowser automatically spoofs WebRTC ICE candidates matching the proxy exit IP.

---

## 5. Sandbox Resource Management (2GB E2B Container)

Chromium processes are memory-intensive. To prevent out-of-memory (OOM) kills inside the E2B sandbox:
1. **Single Browser Instance**: Do not run multiple concurrent browser instances unless strictly necessary.
2. **Page Lifecycle**: Close pages (`page.close()`) immediately after extracting content.
3. **Explicit Cleanup**: Always enclose browser operations inside a `try ... finally` block:
   ```python
   browser = launch(headless=True)
   try:
       ...
   finally:
       browser.close()
   ```
4. **Disable Image Loading (Optional for pure text/data extraction)**:
   If you only need HTML/text and want to save memory and bandwidth:
   ```python
   context = browser.new_context()
   page = context.new_page()
   page.route("**/*.{png,jpg,jpeg,webp,svg,gif}", lambda route: route.abort())
   ```
