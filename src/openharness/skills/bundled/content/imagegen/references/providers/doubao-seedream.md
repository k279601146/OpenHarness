# Doubao Seedream Provider Notes

Doubao Seedream 系列通过火山方舟 / BytePlus ModelArk 图片生成 API 执行：

- `doubao-seedream-5-0-260128`
- `doubao-seedream-5-0-lite-260128`
- `doubao-seedream-4-5-251128`
- `doubao-seedream-4-0-250828`

官方参考：BytePlus / 火山方舟 Image generation API。

## 何时选择

- 用户明确要求豆包、Seedream、火山方舟或中文市场图片生成。
- 适合中文电商图、小红书/短视频封面、商品场景图、中文审美风格图。
- 需要多张连续产出时可设置 `n`，但不同提示词仍应分多次调用。

## API 字段

Seedream 使用 provider 原生字段，不新增跨 provider 的伪枚举：

- `model`
- `prompt`
- `size`
- `stream`
- `response_format`
- `sequential_image_generation`
- `sequential_image_generation_options`
- 参考图/图生图时使用 `image`

OpenHarness runtime 当前使用：

- `size`: 明确像素尺寸或上游接受的尺寸表达
- `stream=true`
- `response_format="b64_json"`
- `sequential_image_generation="auto"` 当 `n > 1`
- `sequential_image_generation="disabled"` 当 `n == 1`
- `sequential_image_generation_options.max_images=n`

## 参数选择

Seedream 更适合使用明确尺寸。常用 2K 尺寸：

- `1:1` -> `2048x2048`
- `4:3` -> `2304x1728`
- `3:4` -> `1728x2304`
- `16:9` -> `2848x1600`
- `9:16` -> `1600x2848`

如果用户要求 9:16 竖版，优先传 `size="1600x2848"` 并保留 `aspect_ratio="9:16"` 作为执行意图。若用户明确给出其他官方允许尺寸，按用户尺寸传递。

## 编辑与参考图

- 文生图使用 `command="generate"`。
- 图生图、参考图或局部风格延展使用 `command="edit"` 并传 `images=[...]`。
- 电商图应在 prompt 中明确主体、背景、材质、光线、构图和禁用项。

## 失败处理

- 如果上游对某个尺寸拒绝，换成同一比例的邻近官方尺寸后重试。
- 不要把上游尝试次数转化为用户额外扣费；同一次工具调用应共享服务端 reservation。
