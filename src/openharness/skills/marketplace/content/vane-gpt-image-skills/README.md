# 🎨 Vane GPT Image Skills

**GPT Image 2.6 好玩又能用的开源玩法合集，持续更新**

𝕏 [关注我的 X 主页 · @VaneAILab](https://x.com/VaneAILab)

这里收集可以直接上手的 AI 生图 Skill。每个玩法都有自己的效果展示和使用说明，从角色表情包开始，以后也会逐步收录封面、配图和其他创意玩法。

## 📚 6 个 Skill 一览

| Skill | 能做什么 | 入口 |
| --- | --- | --- |
| 🎭 [照片转动态表情包](#照片转动态表情包) | 照片变成会动的专属表情包 | [查看效果与教程](docs/portrait-gif-stickers.md) |
| 🎬 [电影级海报设计](#电影级海报设计) | 用 36 种构图制作电影海报 | [查看效果与教程](docs/vane-cinematic-poster.md) |
| 📚 [书页里的电影](#书页里的电影) | 把书中的故事变成海报 | [查看效果与教程](docs/vane-book-cinema.md) |
| 🧧 [微信红包封面制作](#微信红包封面制作) | 设计自己的微信红包封面 | [查看效果与教程](docs/wechat-red-packet-cover.md) |
| 🐾 [宠物新年写真](#宠物新年写真) | 为宠物制作一套新年写真 | [查看效果与教程](docs/vane-pet-new-year-portrait.md) |
| 📕 [小红书图文设计](#小红书图文设计) | 选择风格，制作小红书封面和正文图 | [查看效果与教程](docs/vane-xhs-design.md) |

## 🚀 开始使用

先克隆合集，再安装全部 Skill：

```bash
git clone https://github.com/VaneAi888/vane-gpt-image-skills.git
cd vane-gpt-image-skills
python3 scripts/install_skills.py --all
```

如果只想安装其中一个，或已有同名 Skill，请查看[统一安装教程](docs/installation.md)。安装完成后开启新的 Codex 对话，再使用对应的 `$Skill` 名称。

🔄 **已经安装过？** [查看一键更新教程](docs/updating.md)：以后只需运行一次更新脚本，也可以直接让 Codex 帮你更新。

使用前请确认环境支持读取参考图和图像生成；GIF 动作、图片文字和透明背景的效果取决于实际素材与可用工具。也可以查看[效果与安装测试记录](docs/testing.md)。

---

## 🖼️ 效果展示

### 🎭 角色与表情包

#### [照片转动态表情包](docs/portrait-gif-stickers.md)

上传人物照片、宠物照片或已有角色，选择喜欢的画风和聊天主题，让专属形象用表情和动作说话。

**12 种画风** · **6 个主题** · **默认一套 16 张**

**12 种画风 · 12 组动态演示**

下面展示 4 种画风，每组包含 4 个动作小样。点击动图可放大查看。

| **Q 版萌系** | **手绘涂鸦风** |
| :---: | :---: |
| [![Q 版萌系四动作动态演示](previews/style-01-chibi.gif)](previews/style-01-chibi.gif) | [![手绘涂鸦风四动作动态演示](previews/style-06-doodle.gif)](previews/style-06-doodle.gif) |
| **毛绒布偶风** | **复古漫画风** |
| [![毛绒布偶风四动作动态演示](previews/style-09-plush.gif)](previews/style-09-plush.gif) | [![复古漫画风四动作动态演示](previews/style-12-comic.gif)](previews/style-12-comic.gif) |

👉 **[查看全部 12 种画风、6 个主题与使用教程](docs/portrait-gif-stickers.md)**

### 🎬 电影海报与视觉设计

#### [电影级海报设计](docs/vane-cinematic-poster.md)

根据影片故事和素材，选择构图、设计文字层级，制作中文或英文电影海报方案、提示词或实际图片。

**36 种版式** · **中英文各 4 组预览** · **默认竖版 2:3**

**英文海报预览**

| **01—09 · 人物主导** | **10—18 · 字体主导** |
| :---: | :---: |
| [![电影海报版式 01 至 09 人物主导](skills/vane-cinematic-poster/assets/poster-layouts-01-09.png)](skills/vane-cinematic-poster/assets/poster-layouts-01-09.png) | [![电影海报版式 10 至 18 字体主导](skills/vane-cinematic-poster/assets/poster-layouts-10-18.png)](skills/vane-cinematic-poster/assets/poster-layouts-10-18.png) |
| **19—27 · 场景与空间** | **28—36 · 概念与图形** |
| [![电影海报版式 19 至 27 场景与空间](skills/vane-cinematic-poster/assets/poster-layouts-19-27.png)](skills/vane-cinematic-poster/assets/poster-layouts-19-27.png) | [![电影海报版式 28 至 36 概念与图形](skills/vane-cinematic-poster/assets/poster-layouts-28-36.png)](skills/vane-cinematic-poster/assets/poster-layouts-28-36.png) |

**中文海报预览**

| **01—09 · 人物主导** | **10—18 · 字体主导** |
| :---: | :---: |
| [![中文电影海报版式 01 至 09](skills/vane-cinematic-poster/assets/poster-layouts-zh-01-09.png)](skills/vane-cinematic-poster/assets/poster-layouts-zh-01-09.png) | [![中文电影海报版式 10 至 18](skills/vane-cinematic-poster/assets/poster-layouts-zh-10-18.png)](skills/vane-cinematic-poster/assets/poster-layouts-zh-10-18.png) |
| **19—27 · 场景与空间** | **28—36 · 概念与图形** |
| [![中文电影海报版式 19 至 27](skills/vane-cinematic-poster/assets/poster-layouts-zh-19-27.png)](skills/vane-cinematic-poster/assets/poster-layouts-zh-19-27.png) | [![中文电影海报版式 28 至 36](skills/vane-cinematic-poster/assets/poster-layouts-zh-28-36.png)](skills/vane-cinematic-poster/assets/poster-layouts-zh-28-36.png) |

中英文预览分别设计，并非逐字翻译。图片为构图示例，其中的人物姓名、片方及荣誉文字不代表真实影片信息或授权背书。

👉 **[查看 36 种版式介绍与完整使用教程](docs/vane-cinematic-poster.md)**

#### [书页里的电影](docs/vane-book-cinema.md)

从书中的人物、故事或意象出发，把阅读时的想象变成电影感海报。小说和非虚构作品都可以尝试。

**36 本书籍效果示例** · **4 组完整预览** · **默认竖版 2:3**

| **01—09** | **10—18** |
| :---: | :---: |
| [![书页里的电影示例 01 至 09](skills/vane-book-cinema/assets/books-01-09.jpg)](skills/vane-book-cinema/assets/books-01-09.jpg) | [![书页里的电影示例 10 至 18](skills/vane-book-cinema/assets/books-10-18.jpg)](skills/vane-book-cinema/assets/books-10-18.jpg) |
| **19—27** | **28—36** |
| [![书页里的电影示例 19 至 27](skills/vane-book-cinema/assets/books-19-27.jpg)](skills/vane-book-cinema/assets/books-19-27.jpg) | [![书页里的电影示例 28 至 36](skills/vane-book-cinema/assets/books-28-36.jpg)](skills/vane-book-cinema/assets/books-28-36.jpg) |

以上是书籍海报的创意展示，非官方改编或授权海报。

👉 **[查看全部书籍示例与使用教程](docs/vane-book-cinema.md)**

### 🧧 节日与生活创意

#### [微信红包封面制作](docs/wechat-red-packet-cover.md)

用文字或参考图设计专属微信红包封面，先确认原图，再查看模拟效果并导出上传图片。

**36 种风格参考** · **4 组完整预览** · **单张封面设计**

| **01—09 · 传统艺术** | **10—18 · 趣味角色** |
| :---: | :---: |
| [![红包封面风格 01 至 09 传统艺术](skills/wechat-red-packet-cover/assets/style-gallery/01-09-传统艺术.png)](skills/wechat-red-packet-cover/assets/style-gallery/01-09-传统艺术.png) | [![红包封面风格 10 至 18 趣味角色](skills/wechat-red-packet-cover/assets/style-gallery/10-18-趣味角色.png)](skills/wechat-red-packet-cover/assets/style-gallery/10-18-趣味角色.png) |
| **19—27 · 现代设计** | **28—36 · 自然艺术** |
| [![红包封面风格 19 至 27 现代设计](skills/wechat-red-packet-cover/assets/style-gallery/19-27-现代设计.png)](skills/wechat-red-packet-cover/assets/style-gallery/19-27-现代设计.png) | [![红包封面风格 28 至 36 自然艺术](skills/wechat-red-packet-cover/assets/style-gallery/28-36-自然艺术.png)](skills/wechat-red-packet-cover/assets/style-gallery/28-36-自然艺术.png) |

这些是风格模拟预览，不是可直接上传的封面原图，也不是微信官方模板。

👉 **[查看 36 种风格与完整使用教程](docs/wechat-red-packet-cover.md)**

#### [宠物新年写真](docs/vane-pet-new-year-portrait.md)

上传宠物照片，制作风格统一、姿势多样的新年写真。可以先看九宫格预览，再逐张生成独立照片。

**默认 9 张独立写真** · **3 种影棚背景参考** · **可先看九宫格**

| **多样姿势 · 羊年棚拍** | **中国红影棚** |
| :---: | :---: |
| [![宠物新年写真多样姿势预览](skills/vane-pet-new-year-portrait/assets/01-varied-poses.png)](skills/vane-pet-new-year-portrait/assets/01-varied-poses.png) | [![宠物新年写真中国红影棚预览](skills/vane-pet-new-year-portrait/assets/02-red-studio.png)](skills/vane-pet-new-year-portrait/assets/02-red-studio.png) |
| **黑金影棚** | **纯白影棚** |
| [![宠物新年写真黑金影棚预览](skills/vane-pet-new-year-portrait/assets/03-black-gold-studio.png)](skills/vane-pet-new-year-portrait/assets/03-black-gold-studio.png) | [![宠物新年写真纯白影棚预览](skills/vane-pet-new-year-portrait/assets/04-white-studio.png)](skills/vane-pet-new-year-portrait/assets/04-white-studio.png) |

图中为九宫格预览，独立写真需逐张生成；羊年元素是展示示例，也可指定其他生肖或主题。

👉 **[查看预览与完整使用教程](docs/vane-pet-new-year-portrait.md)**

### 📕 小红书图文

#### [小红书图文设计](docs/vane-xhs-design.md)

把文字和图片制作成小红书封面与正文图，选择喜欢的视觉风格，先预览再逐张生成。

**已收录 3 种风格** · **封面与正文图** · **更多风格持续更新**

<table>
  <tr>
    <td width="50%" align="center"><strong>手帐拼贴风</strong><br><a href="previews/xhs-scrapbook/overview-grid.png"><img src="previews/xhs-scrapbook/overview-grid.png" alt="手帐拼贴风九宫格整体预览"></a></td>
    <td width="50%" align="center"><strong>极简产品风</strong><br><a href="previews/xhs-minimal-product/overview-grid.png"><img src="previews/xhs-minimal-product/overview-grid.png" alt="极简产品风九宫格整体预览"></a></td>
  </tr>
  <tr>
    <td width="50%" align="center"><strong>撞色大字风</strong><br><a href="skills/vane-xhs-design/styles/bold-color/assets/approved-color-reference.png"><img src="skills/vane-xhs-design/styles/bold-color/assets/approved-color-reference.png" alt="撞色大字风九宫格整体预览"></a></td>
    <td width="50%"></td>
  </tr>
</table>

手帐拼贴风适合生活记录和兴趣分享；极简产品风适合产品、AI 工具和生活方式内容；撞色大字风适合创作灵感、活动与潮流内容。

👉 **[查看九页完整效果与使用教程](docs/vane-xhs-design.md)**

## ✨ 持续更新

未来计划按用途整理更多生图玩法，例如封面与社交媒体、文章与知识配图、照片与生活创意，以及趣味视觉实验。新 Skill 完成并具备使用说明后，会加入对应分区。

## 👋 关于作者

我是 **韦恩 Vane**，一名关注 AI 创作与品牌视觉设计的设计师。我分享 AI 工具、视觉创意和实用工作流，也会把有趣的实践整理成开源 Skill。

欢迎关注我的 [X 主页 @VaneAILab](https://x.com/VaneAILab)，一起交流 AI 工具与创作玩法。

## 📄 许可证

项目代码采用 [MIT License](LICENSE)。示例中涉及的第三方角色仅用于非官方风格演示；使用照片或角色素材时，请确认自己有相应使用权。
