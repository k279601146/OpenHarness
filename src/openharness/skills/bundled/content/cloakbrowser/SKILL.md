---
name: cloakbrowser
description: Use for stealth browser automation with CloakBrowser when Codex needs a Playwright/Puppeteer-compatible browser for bot-detection-sensitive sites, Cloudflare or Turnstile checks, browser fingerprint consistency, anti-bot testing, session persistence, proxy geo behavior, or when normal Chromium/Playwright is blocked or scored as automation.
---

# CloakBrowser

Use CloakBrowser as a Playwright/Puppeteer drop-in replacement when normal browser automation is blocked, fingerprinted, or needs a stable returning-visitor identity. For ordinary local web app testing, prefer `$webapp-testing` and standard Playwright.

## Core Rules

- Use CloakBrowser only for authorized testing, account access, research, scraping, or automation. Do not use it to bypass access controls, violate site terms, or automate abuse.
- Keep the shared binary cache separate from browser identity. `/opt/cloakbrowser-cache` can be shared; profiles, cookies, localStorage, proxies, and fingerprint seeds must not be shared across users.
- Never write proxy credentials, license keys, cookies, localStorage dumps, or site credentials into this skill, the template, or source files. Inject them only at runtime.
- Prefer a temporary profile for one-off browsing. Use a persistent profile only when the user asks to keep login/session state or the task requires a stable returning identity.

## Get An Isolated Scope

Before launching a persistent CloakBrowser session, run the helper script to derive the profile path and fingerprint seed:

```bash
python /home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py --site https://example.com --user-id "$USER_ID"
```

If a task needs thread-level isolation, include `--thread-id` and `--mode thread`. For one-off browsing, use `--mode temporary`.

The script prints JSON with `profile_dir`, `fingerprint_seed`, `cache_dir`, `mode`, `site_key`, and `launch_args`. Use `launch_args` directly with CloakBrowser.

## Example Selection

- One-off visit or quick check: use `launch(...)` with `--mode temporary`.
- Need cookies/localStorage or a returning identity: use `cloak_scope.py` default `mode=user` and `launch_persistent_context(...)`.
- Need task/workspace isolation: use `--mode thread --thread-id <thread>`.
- Proxy location, timezone, or locale matters: pass proxy credentials only at runtime and set `geoip=True`.
- Need anti-bot diagnostics: run a fingerprint/stealth/score check and save screenshots or text output for the user.

For complete Bahew-safe examples adapted from the official CloakBrowser examples, read `references/examples.md`.

## Python Pattern

```python
import json
import subprocess
from cloakbrowser import launch

scope = json.loads(subprocess.check_output([
    "python",
    "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
    "--site",
    "https://example.com",
    "--user-id",
    "123",
], text=True))

browser = launch(
    headless=True,
    args=scope["launch_args"],
)
page = browser.new_page()
page.goto("https://example.com")
browser.close()
```

For proxy-derived timezone and locale, pass runtime proxy credentials and `geoip=True`:

```python
browser = launch(
    proxy="http://user:pass@proxy-host:8080",
    geoip=True,
    args=scope["launch_args"],
)
```

## Node Pattern

```js
import { execFileSync } from "node:child_process";
import { launch } from "cloakbrowser";

const scope = JSON.parse(execFileSync("python", [
  "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
  "--site",
  "https://example.com",
  "--user-id",
  "123",
], { encoding: "utf8" }));

const browser = await launch({
  headless: true,
  args: scope.launch_args,
});
const page = await browser.newPage();
await page.goto("https://example.com");
await browser.close();
```

## Persistent Profile Boundary

The helper's default `mode=user` supports per-user, per-site persistence:

```text
/home/user/.cache/openharness/cloakbrowser/profiles/users/<user_hash>/<site_hash>
```

Use this only for state that belongs to the current SaaS user. Do not copy a profile between users. Use `mode=thread` when the user wants a separate identity for a workspace/thread, and `mode=temporary` when persistence is not needed.

When launching with the raw CloakBrowser binary or a framework that accepts Chrome args, pass:

```text
--fingerprint=<fingerprint_seed>
```

Use the exact seed from `cloak_scope.py` for repeat visits to the same site.
