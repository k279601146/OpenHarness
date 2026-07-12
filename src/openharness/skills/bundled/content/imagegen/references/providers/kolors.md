# Kolors Provider Notes

Kolors 通过 OpenAI-compatible 图片接口适配器执行，工具模型 ID 为 `kolors`。

## 何时选择

- 用户明确要求 Kolors、开源风格模型或低成本轻量生成。
- 适合快速草图、社媒图、封面图和固定比例出图。
- 不建议用于需要稳定文字、复杂编辑、精确 mask 或强身份保持的任务。

## 参数选择

- 常用尺寸：
  - `1024x1024` 或 `aspect_ratio="1:1"`
  - `1792x1024` 或 `aspect_ratio="16:9"`
  - `1024x1792` 或 `aspect_ratio="9:16"`
- 如果用户要求 2K/4K，优先保留用户意图传给 `imagegen_cli`；如果 provider 拒绝，再降到最接近的支持尺寸。
- `quality` 对 Kolors 通常不是强控制项；可省略或使用默认 `medium`。

## 编辑与参考图

- Kolors 当前主要保证文生图。
- 参考图或编辑需求优先考虑 GPT Image、Nano Banana/Gemini 或 Doubao Seedream。

## 失败处理

- 如果 OpenAI-compatible 上游返回尺寸不支持，改用 `1024x1024`、`1792x1024` 或 `1024x1792` 中最接近的比例。
- 不要在服务端计费预检阶段拒绝用户的尺寸创意；参数兼容性由 `imagegen_cli` 和上游错误反馈决定。
