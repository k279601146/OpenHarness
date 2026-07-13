# Kolors Provider Notes

Kolors 通过 SiliconFlow 风格的图片生成接口执行，工具模型 ID 为 `kolors`，上游模型通常为 `Kwai-Kolors/Kolors`。

官方参考：SiliconFlow image generation API, `POST /v1/images/generations`。

## 何时选择

- 用户明确要求 Kolors、Kwai-Kolors、开源风格模型或轻量快速文生图。
- 适合社媒封面、小红书图、中文提示词、快速草图和固定比例出图。
- 不建议用于需要稳定文字排版、复杂局部编辑、mask、强身份保持或多参考图融合的任务。

## API 字段

Kolors 使用 provider 原生字段，不使用通用 OpenAI 图片字段：

- `model`: `Kwai-Kolors/Kolors`
- `prompt`: 生成提示词
- `image_size`: 官方尺寸字符串
- `batch_size`: 生成张数
- 可选：`negative_prompt`
- 可选：`seed`
- 可选：`num_inference_steps`
- 可选：`guidance_scale`

不要为 Kolors payload 使用 `size` 或 `n`。`imagegen_cli` 可以接收通用 `size` / `n`，runtime 会翻译成 `image_size` / `batch_size`。

## 官方尺寸

Kolors 当前按官方尺寸表选择明确像素尺寸：

- `1:1` -> `1024x1024`
- `3:4` -> `960x1280`
- `3:4` 低一档 -> `768x1024`
- `1:2` -> `720x1440`
- `9:16` -> `720x1280`

如果用户要求“生成 1 张 9:16”，调用 `imagegen_cli` 时优先传：

```json
{
  "model": "kolors",
  "n": 1,
  "size": "720x1280",
  "aspect_ratio": "9:16"
}
```

也可以只传 `aspect_ratio="9:16"`，runtime 会派生 `image_size="720x1280"`。显式 `size` 优先级最高。

## 失败处理

- 如果上游返回尺寸不支持，按官方表选择最接近用户比例的尺寸后重试。
- 不要把 registry 的 `default_size="1024x1024"` 当作用户比例请求的硬约束；它只用于用户没有给出尺寸或比例时的兜底。
- 生成后 runtime 会读取真实图片尺寸；如果用户明确要求比例但实际比例不匹配，工具调用必须失败，而不是交付错误图。

## 计费与执行边界

- 必须通过 `imagegen_cli` 调用，不要用 `bash`、自写脚本或直接 HTTP 请求 SiliconFlow/Kolors API。
- 多图请求使用 `n` 或 `num_images` 表达；runtime 会把 reservation 张数翻译成 Kolors `batch_size`。
- 不要直接传隐藏的 `batch_size` 来提高返回张数；后端会把 `batch_size` 纳入 `output_count` 计费。
- provider 返回图片数超过 reservation 张数时，工具调用会失败，不发布 artifact，不提交扣费。
