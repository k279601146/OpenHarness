---
name: cloakbrowser
description: "Use this skill whenever the user wants to scrape websites, fetch dynamic web pages, bypass anti-bot protections (Cloudflare Turnstile, reCAPTCHA v3, FingerprintJS, Kasada, 403 Forbidden), automate browser workflows, take web screenshots, or maintain persistent browser sessions with cookies. Covers pre-cached stealth Chromium execution via Python (from cloakbrowser import launch) or Node.js, CLI helper scripts, humanized cursor/typing behavior, and profile management under CLOAKBROWSER_PROFILE_ROOT. Do NOT use for simple REST API calls where plain curl or requests succeeds without bot detection."
category: browser-automation
aliases:
  - browser
  - web-scraping
  - stealth-browser
  - cloudflare-bypass
  - web-automation
user-invocable: true
---

# CloakBrowser: Stealth Web Automation and Scraping

## Overview

CloakBrowser is a stealth Chromium browser patched at the C++ source level (87+ stealth patches) to defeat anti-bot and fingerprint detection systems (Cloudflare Turnstile, reCAPTCHA v3, FingerprintJS, BrowserScan, etc.). It acts as a drop-in replacement for Playwright / Puppeteer with identical APIs.

In the execution sandbox:
- **Binaries pre-cached**: `/opt/cloakbrowser-cache` (no initial download cost).
- **Profile root**: `$CLOAKBROWSER_PROFILE_ROOT` (`/home/user/.cache/openharness/cloakbrowser/profiles`).
- **Python package**: `cloakbrowser[geoip]` is pre-installed.
- **Node.js package**: `cloakbrowser` is pre-installed globally.

---

## When to Use This Skill

- **Anti-bot & CAPTCHA Challenges**: The target site blocks simple HTTP clients (`curl`, `requests`, `httpx`), returns HTTP 403/503, or presents Cloudflare Turnstile, reCAPTCHA v3, or JavaScript challenges.
- **Dynamic Single Page Applications (SPA)**: The page requires client-side JavaScript execution (React, Vue, Angular), client-side hydration, or infinite scrolling to render content.
- **Form Automation & Interactions**: Filling out forms, clicking buttons, submitting data, or navigating multi-step web flows.
- **Visual Capture**: Taking full-page or element-specific screenshots of rendered web pages.
- **Persistent Sessions & Auth**: Maintaining login states, cookies, localStorage, or fingerprint seeds across multiple task steps using persistent contexts.

## When NOT to Use

- **Plain REST/JSON APIs**: If an API endpoint returns raw JSON without bot protection, use `curl`, `httpx`, or `requests` instead for lower latency and resource usage.
- **Static HTML Pages**: If `curl -sL <URL>` or `requests.get` already returns the complete readable HTML without blocking.

---

## Quick Reference: CLI Helper Scripts

For common tasks, use the bundled scripts directly instead of writing standalone code:

### 1. Fetch Page Content (HTML or Clean Text)
```bash
# Extract rendered HTML from a protected URL
python3 /home/user/.agents/skills/cloakbrowser/scripts/fetch_page.py --url "https://example.com" -o page.html

# Extract visible text only (strips scripts/styles for LLM processing)
python3 /home/user/.agents/skills/cloakbrowser/scripts/fetch_page.py --url "https://example.com" --text -o content.txt

# Wait for a specific DOM selector before extracting
python3 /home/user/.agents/skills/cloakbrowser/scripts/fetch_page.py --url "https://example.com" --wait-selector "div.results" -o page.html

# Enable humanized behavior (recommended for Cloudflare Turnstile)
python3 /home/user/.agents/skills/cloakbrowser/scripts/fetch_page.py --url "https://example.com" --humanize -o page.html
```

### 2. Capture Screenshot
```bash
# Full page screenshot
python3 /home/user/.agents/skills/cloakbrowser/scripts/screenshot.py --url "https://example.com" --full-page -o /home/user/artifacts/screenshot.png

# Capture a specific element
python3 /home/user/.agents/skills/cloakbrowser/scripts/screenshot.py --url "https://example.com" --selector "#main-content" -o element.png
```

---

## Python API (Recommended)

CloakBrowser mirrors the Playwright API. Import from `cloakbrowser` instead of `playwright`.

### Basic Fetch / Automation
```python
from cloakbrowser import launch

# Launch headless browser (default in sandbox)
browser = launch(headless=True)
try:
    page = browser.new_page()
    page.goto("https://example.com", wait_until="networkidle", timeout=30000)
    print("Page Title:", page.title())
    html = page.content()
finally:
    browser.close()
```

### Passing Cloudflare Turnstile & Aggressive Bot Detection
When dealing with Cloudflare Turnstile or behavioral analysis:
1. Enable `humanize=True` to simulate human mouse curves, scroll physics, and typing intervals.
2. Set a realistic viewport size.
3. Wait for network idle or challenge completion.

```python
from cloakbrowser import launch_context

context = launch_context(
    headless=True,
    humanize=True,
    viewport={"width": 1920, "height": 1080},
    locale="en-US",
    timezone="America/New_York",
)
try:
    page = context.new_page()
    page.goto("https://protected-site.com", wait_until="networkidle", timeout=45000)
    
    # If a Turnstile checkbox/challenge exists, humanize will move naturally
    turnstile = page.locator("iframe[src*='challenges.cloudflare.com']")
    if turnstile.count() > 0:
        page.wait_for_timeout(3000)
        
    html = page.content()
finally:
    context.close()
```

### Persistent Profiles (Cookies, Login, Sessions)
Store persistent user profiles under `$CLOAKBROWSER_PROFILE_ROOT` to keep cookies and localStorage between runs without incognito detection:

```python
import os
from cloakbrowser import launch_persistent_context

profile_root = os.environ.get(
    "CLOAKBROWSER_PROFILE_ROOT", 
    "/home/user/.cache/openharness/cloakbrowser/profiles"
)
profile_dir = os.path.join(profile_root, "site_session")
os.makedirs(profile_dir, exist_ok=True)

context = launch_persistent_context(
    user_data_dir=profile_dir,
    headless=True,
    humanize=True,
)
try:
    page = context.new_page()
    page.goto("https://example.com")
    # Cookies & localStorage will persist in profile_dir
finally:
    context.close()
```

### Working with Proxies & GeoIP
If a proxy is provided:
```python
from cloakbrowser import launch

# geoip=True automatically aligns timezone and locale with the proxy exit IP
browser = launch(
    proxy="http://user:pass@residential-proxy:port",
    geoip=True,
    humanize=True,
    headless=True,
)
```

---

## Node.js / TypeScript API

You can also run Node scripts via `tsx` or `node`:

```javascript
import { launch } from 'cloakbrowser';

const browser = await launch({
  headless: true,
  humanize: true,
});

try {
  const page = await browser.newPage();
  await page.goto('https://example.com', { waitUntil: 'networkidle' });
  console.log(await page.title());
} finally {
  await browser.close();
}
```

---

## Best Practices & Operational Rules

1. **Always wrap in `try ... finally`**: Always call `browser.close()` or `context.close()` in a `finally` block to prevent orphaned Chromium processes from consuming sandbox memory.
2. **Explicit Timeouts**: Set `timeout=30000` (30 seconds) on navigation and locator actions to prevent hanging indefinitely on slow or stuck challenges.
3. **Selector Waiting**: Prefer `page.wait_for_selector("...")` or `locator.wait_for()` over hardcoded `sleep()`.
4. **Artifact Storage**: Save user-facing outputs (downloaded files, screenshots) into `/home/user/artifacts/` or the current task directory.
5. **No Credential Leaks**: Never print raw passwords, cookies, or authorization tokens into logs or user-facing messages.
6. **Detailed Anti-Bot Troubleshooting**: Read `references/antibot_guide.md` when confronting Kasada, reCAPTCHA enterprise, or tricky Cloudflare managed challenges.
