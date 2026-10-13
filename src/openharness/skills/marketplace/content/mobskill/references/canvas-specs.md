# Canvas and Export Specs

Store requirements change. Use this table for production planning, then verify exact current requirements in App Store Connect or Play Console immediately before upload.

## Apple

| Asset | Working/accepted sizes | Notes |
| --- | --- | --- |
| iPhone 6.9-inch | 1260×2736, 1320×2868, or 1290×2796 portrait; transpose for landscape | Pick the size matching the represented generation and keep it across the set. Default 1320×2868 when appropriate. |
| iPhone legacy buckets | 6.5: 1284×2778 or 1242×2688; 6.3: 1179×2556 or 1206×2622; 6.1: 1170×2532, 1125×2436, or 1080×2340 | Usually optional when the largest supported set allows scaling; verify current console behavior. |
| iPad 13-inch | 2064×2752 or 2048×2732; transpose for landscape | Default 2064×2752 if generation is unspecified; re-layout from phone. |
| macOS | 1280×800, 1440×900, 2560×1600, or 2880×1800 | 16:10; default largest; real window on backdrop. |
| tvOS | 1920×1080 or 3840×2160 | 16:9, full-bleed authentic TV UI. |
| watchOS | Ultra 3 422×514; Ultra/Ultra 2 410×502; Series 10/11 416×496; Series 7–9 396×484; Series 4–6/SE 368×448; Series 3 312×390 | UI only; use one supported generation consistently per localization. |
| visionOS | 3840×2160 | Flat rectangular app capture. |
| App icon | Square source | Platform applies mask; no baked corner radius. |

Do not place a fake iOS status bar on the outer marketing canvas. A status bar may exist only inside authentic device-screen content.

## Google Play

General screenshot constraint: each side 320–3840px and longest side no more than 2× shortest. Use one orientation per set.

| Asset | Size/count | Format |
| --- | --- | --- |
| Phone screenshots | 2–8; useful defaults 1080×1920 or 1920×1080 | JPEG or 24-bit PNG, no alpha |
| 7/10-inch tablet | Up to 8 per class; use authentic large-screen resolution | JPEG or 24-bit PNG, no alpha |
| Feature Graphic | Exactly 1024×500 | JPEG or 24-bit PNG, no alpha |
| Hi-res icon | 512×512 | 32-bit PNG with alpha; verify current icon rules |
| Android TV banner | 1280×720 | JPEG or 24-bit PNG, no alpha |
| Wear OS | 1:1, minimum 384×384 | JPEG or 24-bit PNG, no alpha |
| Chromebook | Landscape | JPEG or 24-bit PNG, no alpha |
| Automotive | If required: 2 portrait 800×1280 and 2 landscape 1024×768 | Verify by category |
| Android XR | 4–8, 8:5; recommended 3840×2400, minimum 1920×1200, up to 8 MB | PNG or JPEG; verify current rules |

For large-format discovery, plan at least four strong 1080px-or-larger phone/large-screen screenshots where applicable (games may use platform-specific minimums). Treat this as recommendation guidance, not a substitute for current console validation.
