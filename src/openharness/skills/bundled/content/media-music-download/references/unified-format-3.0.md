# 视频解析统一 JSON 格式 3.0 规范契约

> 本规范为 `short_videos` 源码与部署在 `https://api.bugpk.com` 各平台解析接口（抖音、快手、小红书、哔哩哔哩、微博、今日头条、皮皮虾、皮皮搞笑、最右、即梦AI、豆包AI等）统一遵循的对外数据契约。

## 通用响应结构

| 字段 | JSON 类型 | 说明 |
| --- | --- | --- |
| `code` | integer | 业务状态码；200 表示成功，400 参数错误，404 不存在，500 异常 |
| `msg` | string | 可读状态说明，仅用于展示 |
| `data` | object / array | 成功时为数据对象；失败时固定为 `[]` |

## 媒体解析接口的 data 基础结构 (16 个标准字段)

| 字段 | JSON 类型 | 含义与无数据时的约定 |
| --- | --- | --- |
| `type` | string | `video`、`image` 或 `live` |
| `title` | string | 作品标题；未知时为 `""` |
| `desc` | string | 作品描述；未知时为 `""` |
| `author` | object | 作者信息，包含 `name`、`id`、`avatar` 三个字符串字段；未知字段为 `""` |
| `cover` | string | 封面 URL；未知时为 `""` |
| `url` | string / null | 主视频 URL；图集、实况为 `null` |
| `quality` | string | 视频画质描述；抖音原画为 `original`，其他为码率档位名 |
| `duration` | number / null | 视频时长，单位秒，允许小数；未知或不适用时为 `null` |
| `size` | integer | 主视频文件大小，单位字节；未知或不适用时为 0 |
| `size_label` | string | 文件大小的可读说明（如 `"1.74MB"`）；`size` 为 0 时为 `""` |
| `create_time` | integer | 作品发布时间的 Unix 秒数；未知时为 0 |
| `publish_time` | string | 对应的 `YYYY-MM-DD HH:mm:ss` 时间文本（UTC+8）；未知时为 `""` |
| `images` | array[string] | 按顺序排列的图片 URL；无图片时为 `[]` |
| `live_photo` | array[object] | 实况图片与视频配对列表，每项含 `{"image": "...", "video": "..."}`；无实况时为 `[]` |
| `music` | object | 音乐信息，包含 `{"title": "...", "author": "...", "url": "...", "cover": "..."}`；无音乐时为 `{}` |
| `extra` | object | 附加公开信息（如 `aweme_id`, `statistics` 等）；无附加信息时为 `{}` |

## 1. 视频类型 (video)
主视频直链存储于 `data.url`，`images` 和 `live_photo` 为 `[]`。
可选返回 `video_backup`（备选多码率流数组）。

### quality_type 码率等级对照表
- `1`: 360p
- `2`: 480p
- `4`: 720p
- `8`: 1080p
- `16`: 2K
- `32`: 4K
- `64`: 原画 (original)
- `72`: 4K+

## 2. 图集类型 (image)
`data.url: null`，`quality: ""`，`images` 为原图 URL 列表。

## 3. 实况类型 (live)
`data.url: null`，`images` 存放预览图列表，`live_photo` 存放图片与微视频配对：
```json
[
  {
    "image": "https://.../photo.jpg",
    "video": "https://.../video.mp4"
  }
]
```
