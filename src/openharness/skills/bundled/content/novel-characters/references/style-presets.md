# 画风预设

出图风格可选。**默认 `realistic`**。除两个结构范本外，当前内置 `ink`、`cyberpunk`、`comic`、`anime`、`watercolor`、`wuxia`、`noir`、`3d`；新增风格必须在本文件、脚本 `STYLE_PRESETS` 与角色/场景/分镜三套校验器中同步定义。

预设定义在 `scripts/novel-characters.mjs` 的 `STYLE_PRESETS` 里，跑
`node scripts/novel-characters.mjs styles` 可以把整段打出来直接用。

首页风格库的 94 个模板 ID 全部登记在同目录的 `style-catalog.json`；每个条目都独立提供 `render`、`surface`、`lighting`、`negative` 和 `phrase`，并原样作为五阶段产物的 `style` 字段。下表列出内置兼容预设：

| id | 说明 |
| --- | --- |
| `realistic` | 半写实厚涂。默认 |
| `ghibli` | 吉卜力式手绘赛璐璐动画 |
| `custom` | 用户自定义 brief，保持原文并使用通用结构约束 |
| `ink` | 东方水墨、宣纸与笔触 |
| `cyberpunk` | 霓虹赛博朋克、工业材质 |
| `comic` | 美漫线稿、网点与图形阴影 |
| `anime` | 美型二次元、精致赛璐璐 |
| `watercolor` | 水彩插画、透明叠染 |
| `wuxia` | 武侠国风、工笔水墨 |
| `noir` | 黑白电影、硬朗明暗 |
| `3d` | 风格化三维、PBR 材质 |

## ⚠️ 换风格是整套换，不是只换一句「画风」

每个预设自带五块，**必须整块取用，不要混搭**。新增预设也必须为角色、场景和分镜提供语义一致的整套定义：

| 块 | 作用 |
| --- | --- |
| `render` | 渲染方式那句 |
| `surface` | 皮肤、眼睛、头发、布料怎么处理 |
| `lighting` | 光照 |
| `negative` | 反向提示词 |
| `tags` | 风格标签 |

**两个预设的 `negative` 几乎是相反的**：

- `realistic` **绝不能**禁 `photorealistic` / `3d render`——一边要真实感一边禁真实感是自相矛盾的，它禁的是「假」（塑料皮肤、无毛孔娃娃脸、完全对称的脸）
- `ghibli` **必须**禁 `photorealistic` / `3d render` / `visible pores`——写实的那些细节在这里全是反效果

`surface` 同理。写实要毛孔、皮下散射、根根分明的碎发、布料织纹；吉卜力明确要
**无毛孔、无皮肤纹理、成簇的发丝、平涂无织纹的布料**。把写实那段带进吉卜力，
出来就是个四不像。

`validate` 会检查这一条：风格与反向提示词搞反了直接报错。

## 光照的差别

- `realistic` **分区打光**：左栏半身像给方向主光 + 环境遮蔽（要体积），右侧三视图
  和细节条平光正交（要抠图和量比例）
- `ghibli` **全图平光**：均匀日光 + 单层柔和阴影。平光本来就是这个风格的一部分，
  不需要分区

## 版面不随风格变

16:9 三区、34%/66% 比例、人物比例协调、细节让位不是人物让位——这些是**版面规则**，
两个风格都一样。变的只有渲染质感。

## 加新预设

往 `STYLE_PRESETS` 里加一个键，五块写全，`label` 给齐三语；若来自首页模板，必须在 `style-catalog.json` 中直接填写五个独立字段，不得依赖 `family` 或其他预设继承。自测会检查完整性。
