# Nano Banana / Gemini Provider Notes

Nano Banana model ids route through the Gemini-style image API adapter:

- `nano-banana`
- `nano-banana-2`
- `nano-banana-pro`

Use these models when the user explicitly asks for Nano Banana, Gemini image generation, or a Google image model. They support text-to-image and image-conditioned generation/editing through `imagegen_cli command="generate"` or `command="edit"` with `images=[...]`.

Supported aspect ratio hints are `1:1`, `16:9`, `9:16`, `4:3`, and `3:4`. If no aspect ratio is supplied, the adapter defaults to square output.
