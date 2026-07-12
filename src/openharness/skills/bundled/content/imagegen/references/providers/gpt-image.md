# GPT Image Provider Notes

GPT Image 是 `imagegen_cli` 中能力最完整的图片路径，适合高保真图像、文字较多的海报/信息图、精细编辑、参考图保持和复杂构图。

## 何时选择

- 用户明确指定 `gpt-image-2` 或其他 `gpt-image-*` 模型。
- 需要较强文本准确性、复杂画面结构、UI/信息图、商品图精修。
- 需要图片编辑、参考图、mask 或更高稳定性。

## 参数选择

- 常规草图可用 `size="1024x1024"` 或省略尺寸。
- 2K 输出可用 `2048x2048`、`2048x1152`、`1152x2048`。
- 4K 横图用 `3840x2160`，4K 竖图用 `2160x3840`。
- 也可以传 `resolution="2K"` / `resolution="4K"` 与 `aspect_ratio`，让 CLI runtime 解析。
- `quality` 可用 `low`、`medium`、`high`、`auto`；快速草图用 `low`，正式输出用 `medium/high/auto`。

## 编辑与透明背景

- 编辑或参考图使用 `command="edit"` 并传 `images=[...]`。
- `gpt-image-2` 不支持原生 `background=transparent`。透明图默认使用纯色 chroma-key 生成后本地抠图。
- 只有用户明确接受模型降级时，才考虑支持原生透明背景的旧 GPT Image 路径。

## 失败处理

- 如果上游返回尺寸或参数错误，调整传给 `imagegen_cli` 的 `size/resolution/aspect_ratio/quality` 后重试。
- 不要为了通过计费预检降低画面需求；计费由服务端按输出数量和 K 档位处理。
