# CloakBrowser Examples For OpenHarness

These examples adapt official CloakBrowser usage patterns for the OpenHarness SaaS sandbox. Always keep binary cache, browser profile, credentials, and fingerprint seed separate.

## 1. One-Off Page Visit

Use this for a short visit that does not need cookies or localStorage persistence.

```python
import json
import subprocess
from cloakbrowser import launch

scope = json.loads(subprocess.check_output([
    "python",
    "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
    "--site", "https://example.com",
    "--user-id", "123",
    "--mode", "temporary",
], text=True))

browser = launch(headless=True, args=scope["launch_args"])
page = browser.new_page()
page.goto("https://example.com", wait_until="networkidle")
print(page.title())
browser.close()
```

## 2. Persistent Context For Login State

Use this only when the current user asks to preserve login/session state or the task needs a stable returning identity.

```python
import json
import subprocess
from cloakbrowser import launch_persistent_context

scope = json.loads(subprocess.check_output([
    "python",
    "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
    "--site", "https://example.com",
    "--user-id", "123",
], text=True))

context = launch_persistent_context(
    user_data_dir=scope["profile_dir"],
    headless=True,
    args=scope["launch_args"],
)
page = context.new_page()
page.goto("https://example.com/account", wait_until="networkidle")
print(page.title())
context.close()
```

Never reuse `scope["profile_dir"]` for a different SaaS user. For separate identities inside the same user account, rerun the helper with `--mode thread --thread-id <thread-id>`.

## 3. Proxy And Geo Behavior

Use this when the website expects timezone, locale, and IP geography to match. Proxy credentials must come from runtime input or environment variables, not from skill files.

```python
import json
import os
import subprocess
from cloakbrowser import launch

proxy_url = os.environ["CLOAK_PROXY_URL"]
scope = json.loads(subprocess.check_output([
    "python",
    "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
    "--site", "https://example.com",
    "--user-id", "123",
], text=True))

browser = launch(
    headless=True,
    proxy=proxy_url,
    geoip=True,
    args=scope["launch_args"],
)
page = browser.new_page()
page.goto("https://example.com", wait_until="networkidle")
browser.close()
```

## 4. Fingerprint Or Stealth Diagnostic

Use diagnostic pages when the user asks why a site blocks automation, or when you need evidence that the browser launch looks sane. Save screenshots or extracted summaries under `/home/user/artifacts`.

```python
import json
import subprocess
from pathlib import Path
from cloakbrowser import launch

artifact_dir = Path("/home/user/artifacts")
artifact_dir.mkdir(parents=True, exist_ok=True)

scope = json.loads(subprocess.check_output([
    "python",
    "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
    "--site", "https://browserleaks.com",
    "--user-id", "123",
    "--mode", "temporary",
], text=True))

browser = launch(headless=True, args=scope["launch_args"])
page = browser.new_page()
page.goto("https://browserleaks.com/canvas", wait_until="networkidle")
page.screenshot(path=str(artifact_dir / "cloakbrowser-canvas.png"), full_page=True)
print(page.title())
browser.close()
```

Examples of diagnostic targets from the official CloakBrowser examples include fingerprint scan, CreepJS, SannySoft, BrowserScan, and reCAPTCHA v3 score pages. Use them only for diagnostics and reporting, not for bypassing site restrictions.

## 5. Node Persistent Context

Use Node when the surrounding automation is already JavaScript.

```js
import { execFileSync } from "node:child_process";
import { launchPersistentContext } from "cloakbrowser";

const scope = JSON.parse(execFileSync("python", [
  "/home/user/.agents/skills/cloakbrowser/scripts/cloak_scope.py",
  "--site", "https://example.com",
  "--user-id", "123",
], { encoding: "utf8" }));

const context = await launchPersistentContext(scope.profile_dir, {
  headless: true,
  args: scope.launch_args,
});
const page = await context.newPage();
await page.goto("https://example.com", { waitUntil: "networkidle" });
console.log(await page.title());
await context.close();
```

If the installed Node API names differ, inspect the installed package with `node -e "console.log(Object.keys(require('cloakbrowser')))"` and adapt the import while preserving the same scope and profile boundary.
