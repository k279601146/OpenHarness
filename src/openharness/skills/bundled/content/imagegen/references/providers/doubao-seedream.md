# Doubao Seedream Provider Notes

Doubao Seedream model ids route through the Doubao streaming image API adapter:

- `doubao-seedream-5-0-260128`
- `doubao-seedream-5-0-lite-260128`
- `doubao-seedream-4-5-251128`
- `doubao-seedream-4-0-250828`

Use these models when the user explicitly asks for Doubao, Seedream, Volcengine image generation, or Chinese-market image generation. They support text-to-image and image-conditioned generation/editing through `imagegen_cli command="generate"` or `command="edit"` with `images=[...]`.

Aspect ratio hints map to Doubao-friendly sizes:

- `1:1` -> `2048x2048`
- `4:3` -> `2304x1728`
- `3:4` -> `1728x2304`
- `16:9` -> `2848x1600`
- `9:16` -> `1600x2848`
