# GPT Image Provider Notes

GPT Image remains the most deeply tuned path in this skill. Existing files in `references/` and `scripts/image_gen.py` contain the authoritative prompt, size, transparency, and API behavior guidance for `gpt-image-*` models.

Use this provider when the user asks for `gpt-image-2`, another `gpt-image-*` model, text-heavy images, high-fidelity edits, or the existing GPT Image CLI controls.

Important constraints:

- `gpt-image-2` supports flexible sizes within its documented limits.
- Do not set `input_fidelity` with `gpt-image-2`.
- `gpt-image-2` does not support native `background=transparent`; use the chroma-key workflow unless the user confirms a fallback model that supports transparency.
