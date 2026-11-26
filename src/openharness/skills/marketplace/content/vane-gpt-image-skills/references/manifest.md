# 图集导出清单

`export_pack.py` 需要 Python 3、Pillow；视频预览需要 FFmpeg。指定包含中文的字体，例如 macOS 的中文字体。路径相对于 JSON 清单。使用 `--preview` 生成 MP4，输出目录应为空。

```json
{
  "title": "我的 AI 搭子",
  "count": 2,
  "groups": [{
    "name": "日常",
    "atlas": "atlas.png",
    "grid": [2, 1],
    "ink": "#36435B",
    "tint": "#8FE2F0",
    "background": "#F7FAFB",
    "entries": [
      {"text":"灵感来了", "cell":[0,0], "motion":"jump", "icon":"spark"},
      {"text":"晚安", "cell":[1,0], "motion":"breathe", "icon":"sleep"}
    ]
  }]
}
```

`cell` 是从零开始的列、行。格子不均匀时可在单个 entry 中添加 `crop: [left, top, right, bottom]`（图集像素坐标），确保裁切完整且不包含邻居。文案必须唯一；`count` 必须与总条数一致。

动作：`nod`, `jump`, `sway`, `startle`, `tremble`, `ponder`, `breathe`, `stomp`, `rush`, `peek`, `pulse`, `pop`, `offer`, `lean`, `droop`, `dance`。

动态符号：`spark`, `heart`, `tear`, `check`, `question`, `alert`, `sleep`, `steam`, `note`, `cross`, `bubble`, `dots`, `bolt`, `arrow`, `petal`, `none`。

```sh
python3 scripts/export_pack.py manifest.json output --font /path/to/chinese-font.ttf --preview
```

每张 GIF 24 帧、80ms/帧、透明背景、无限循环；导出器检查动帧数量、边距、压缩包完整性和条数。大系列预览按每页最多 16 张分页。视频由已编码的 GIF 解码后生成。使用 `--jobs 2` 降低并发；TTC 指定 `--font-index`。
