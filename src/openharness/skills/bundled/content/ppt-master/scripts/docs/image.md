# Image Tools

> Architecture rationale (why provider-specific config keys instead of a generic `IMAGE_API_KEY`, why permissive license filter with strict-mode escape hatch, why external refs in dev but two divergent embedding strategies for delivery): see [docs/technical-design.md "Image Acquisition & Embedding"](../../../../docs/technical-design.md#image-acquisition--embedding).

Image tools cover formula rendering, SaaS prompt-based AI generation, web image search, image inspection, and Gemini watermark removal.

## `latex_render.py`

Manifest-driven LaTeX formula renderer. Strategist writes `images/formula_manifest.json` after the Typography confirmation; this script renders only those declared formulas to transparent PNGs and writes dimensions back into the manifest.

```bash
python3 scripts/latex_render.py <project_path>
python3 scripts/latex_render.py <project_path> --dry-run
python3 scripts/latex_render.py <project_path> --providers codecogs,quicklatex,mathpad,wikimedia
```

Manifest shape:

```json
{
  "providers": ["codecogs", "quicklatex", "mathpad", "wikimedia"],
  "items": [
    {
      "id": "formula_001",
      "latex": "E = mc^2",
      "display": "block",
      "color": "#1D1D1F",
      "background": "#FFFFFF",
      "transparent": true,
      "dpi": 300,
      "filename": "formula_001.png"
    }
  ]
}
```

Output files land directly under `project/images/`. Formula filenames should use a shared `formula_` prefix, e.g. `formula_001.png`. The default provider chain is `codecogs,quicklatex,mathpad,wikimedia`; each provider is tried automatically until one succeeds, and the winning provider is recorded back into the manifest. `--providers` or manifest-level `providers` may override the order, but all four are available as no-key fallbacks. Formula PNGs are transparent by default. `background` is the temporary render matte and local background-removal reference; set `transparent: false` only when an opaque final formula asset is intentional. The script does not scan `spec_lock.md` or source documents for `$...$`; formula selection is a Strategist decision.

## SaaS `generate_image`

Prompt-based AI images are generated through the SaaS `generate_image` service. The PPT skill writes prompt manifests and submits structured requests; the SaaS backend handles model routing, billing reservation, media gateway execution, image validation, artifact publication, and any provider credentials.

Do not configure provider API keys, provider base URLs, image backend names, or model-specific provider knobs in this skill. If SaaS image generation is unavailable, keep the prompt manifest and mark affected rows `Needs-Manual`.

## `analyze_images.py`

Analyze images in a project directory before writing the design spec or composing slide layouts.

```bash
python3 scripts/analyze_images.py <project_path>/images
```

Use this instead of opening image files directly when following the project workflow.

## `image_search.py`

Zero-config web image search across openly-licensed providers. Used when the resource list row has `Acquire Via: web`.

```bash
python3 scripts/image_search.py "offshore wind farm" \
  --filename cover_bg.jpg --slide 01_cover \
  --orientation landscape -o projects/demo/images
```

Providers (Openverse and Wikimedia work with no key; configure Pexels / Pixabay for better stock-photo quality):

| Provider | Config | Strength |
|---|---|---|
| `openverse` | zero-config | fallback aggregator: Wikimedia + Flickr + museums + rawpixel |
| `wikimedia` | zero-config | educational, scientific, geographic, historical |
| `pexels` | recommended: `PEXELS_API_KEY` | modern stock photography, people, workplace, lifestyle |
| `pixabay` | recommended: `PIXABAY_API_KEY` | broad type coverage including photos and illustrations |

Default search chain (when `--provider` is unset): zero-config providers first, then keyed providers whose API key is set in the environment. Keyed providers without a key are silently skipped. For polished visual decks, configure at least one keyed provider.

`image_search.py` uses the shared PPT Master `.env` lookup order, so skill installs can keep `PEXELS_API_KEY` / `PIXABAY_API_KEY` in `~/.ppt-master/.env`.

Query guidance:

| Case | Pattern |
|---|---|
| Generic stock concept | `boardroom meeting, professional editorial photography, natural light` |
| China-specific landmark | Official Chinese place name + concrete scene |
| Avoid | Negative prompt wording such as `not tourist snapshot` |

License filter:

- **Default**: search all providers with `cc0,pdm,pexels,pixabay,cc by,cc by-sa` allowed together. The chosen image may be `no-attribution` or `attribution-required`; Executor adds an inline credit only when needed.
- `--strict-no-attribution` restricts the search to `cc0,pdm,pexels,pixabay` — useful for full-bleed hero images or templates that cannot host a credit element.

Pin a provider, refuse attribution, or override the manifest path:

```bash
# Pin Wikimedia
python3 scripts/image_search.py "Olympics opening ceremony" \
  --filename event.jpg --provider wikimedia \
  --orientation landscape -o projects/demo/images

# Strict mode — refuse CC BY / CC BY-SA
python3 scripts/image_search.py "abstract gradient" \
  --filename hero.jpg --strict-no-attribution \
  -o projects/demo/images
```

Output:

- Image saved to the specified output directory (auto-converts webp → jpg via Pillow when the filename extension demands)
- `image_sources.json` manifest with full provenance (provider, license, license_tier, author, source URL, dimensions, attribution_text)
- Manifest is idempotent on `filename` — rerunning replaces that entry only

Allowed licenses (default): CC0, Public Domain, Pexels License, Pixabay Content License, CC BY, CC BY-SA. Auto-rejected: CC BY-NC, CC BY-ND, CC BY-NC-SA, CC BY-NC-ND, all rights reserved, unknown.

The full role-level reference (intent → query translation, on-slide attribution visual specification) is in [`references/image-searcher.md`](../../references/image-searcher.md).

## `gemini_watermark_remover.py`

Remove Gemini watermark assets after manual download.

```bash
python3 scripts/gemini_watermark_remover.py <image_path>
python3 scripts/gemini_watermark_remover.py <image_path> -o output_path.png
python3 scripts/gemini_watermark_remover.py <image_path> -q
```

Notes:
- Requires `scripts/assets/bg_48.png` and `scripts/assets/bg_96.png`
- Best used after downloading “full size” Gemini images

Dependencies:

```bash
pip install Pillow numpy
```
