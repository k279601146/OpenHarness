# generate_image

Generate images from text descriptions using the `generate_image` tool.

## When to use

Use when the user asks to:
- Draw, paint, or illustrate something
- Create, generate, or produce an image or picture
- Visualize a concept, scene, character, or object
- Make any kind of visual content

## Workflow

1. Understand the user's visual intent — ask for clarification if the description is vague
2. Craft a detailed, descriptive prompt in English for best results
3. Call `generate_image` with the crafted prompt
4. Report the saved file path to the user
5. If the result is not satisfactory, refine the prompt and try again

## Rules

- Always write prompts in English for maximum model compatibility
- Be specific: include style, lighting, composition, colors when relevant
- Do not attempt to generate images using bash or web_fetch — use `generate_image` only
- If IMAGE_GEN_API_KEY is missing, inform the user and explain how to set it up
