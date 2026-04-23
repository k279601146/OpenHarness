---
name: social-media-visuals
description: 社交媒体视觉素材设计技能，封装了 Instagram、TikTok、小红书、微信公众号各平台的视觉决策规则。
version: "1.0.0"
domain: content
triggers:
  - 社媒
  - 社交媒体
  - 小红书
  - Instagram
  - TikTok
  - 公众号
  - 微信
  - 帖子
  - 封面
  - 素材
  - social media
  - post
  - reel
  - story
---

# Social Media Visual Assets
> 不同平台有不同的视觉语法。这个技能的核心价值是：在生成前就知道"这张图要发哪里"，然后用对应平台的审美逻辑来构建 Prompt。

## 1. 核心原则
- 平台决定构图：每个平台的用户滑动习惯和停留时长不同，视觉冲击点的位置也不同。
- 前 0.5 秒决定一切：图像必须在缩略图状态下就能抓住注意力。
- 留白给文字：社媒素材通常需要叠加文案，Prompt 中必须预留文字区域。
- 真实感 > 精致感：过度精修的图在社媒上反而降低互动率，适度的生活感更有传播力。
- 竖版优先：移动端竖屏是主战场，横版是例外。

## 2. 视觉决策树 (Visual Decision Rules)

### 按平台决策
| 平台 | 尺寸比例 | 视觉风格 | 构图重点 | 颜色倾向 |
|------|---------|---------|---------|---------|
| Instagram Feed | 1:1 / 4:5 | 精致、统一色调、品牌感 | 主体居中或三分法，大量留白 | 莫兰迪、低饱和、品牌色系 |
| Instagram Story / Reels | 9:16 | 动感、沉浸式、全屏 | 主体在上 1/3，底部留文字区 | 高对比、鲜艳或深色背景 |
| TikTok 封面 | 9:16 | 强冲击、悬念感、情绪化 | 人物/主体大特写，表情夸张 | 高饱和、强对比 |
| 小红书封面 | 3:4 | 生活感、种草感、真实 | 场景化，产品融入生活场景 | 暖色、奶油白、马卡龙 |
| 小红书详情图 | 3:4 | 信息清晰、步骤感 | 分区布局，留大量文字区 | 清爽、白底为主 |
| 微信公众号封面 | 900×383 (横版) | 专业、媒体感、权威 | 主体偏左，右侧留标题区 | 稳重色调，蓝/深色系 |
| 微信朋友圈广告 | 1:1 / 16:9 | 生活化、场景化 | 产品在使用中，真实场景 | 自然光、暖色调 |

### 按内容类型决策
| 内容类型 | 视觉策略 | 关键 Prompt 元素 |
|---------|---------|----------------|
| 产品种草 | 产品 + 使用场景 + 真实感 | `lifestyle product shot`, `natural setting`, `authentic feel` |
| 活动促销 | 强视觉冲击 + 紧迫感 | `bold composition`, `high contrast`, `dynamic energy` |
| 品牌故事 | 情绪化 + 叙事感 | `cinematic mood`, `storytelling composition`, `emotional depth` |
| 教程/攻略 | 清晰 + 步骤感 | `clean layout`, `step-by-step visual`, `informational design` |
| 节日营销 | 节日氛围 + 品牌融合 | `festive atmosphere`, `seasonal colors`, `celebratory mood` |

### 按视觉风格决策
| 风格 | 适用品牌 | 核心关键词 |
|------|---------|-----------|
| 极简白 | 科技、护肤、轻奢 | `minimalist`, `white space`, `clean aesthetic`, `airy` |
| 暗黑高级 | 奢侈品、潮牌、夜场 | `dark moody`, `dramatic lighting`, `luxury dark` |
| 奶油生活 | 家居、食品、母婴 | `creamy tones`, `cozy lifestyle`, `warm natural light` |
| 赛博霓虹 | 游戏、电子、潮流 | `neon glow`, `cyberpunk aesthetic`, `vibrant contrast` |
| 胶片复古 | 咖啡、文创、旅行 | `film grain`, `vintage tones`, `nostalgic mood` |

## 3. Prompt 关键词库

**构图 (Composition)**
`vertical 9:16 format`, `subject in upper third`, `centered hero shot`, `rule of thirds`, `text-safe bottom area`, `breathing room around subject`, `full-bleed background`

**光线 (Lighting)**
`soft natural window light`, `golden hour glow`, `ring light catchlight`, `diffused studio light`, `dramatic side lighting`, `backlit silhouette`, `warm ambient light`

**材质/质感 (Material & Texture)**
`skin texture detail`, `fabric softness`, `product surface clarity`, `bokeh background`, `shallow depth of field`, `crisp product edges`

**氛围/风格 (Atmosphere & Style)**
`lifestyle photography`, `authentic candid moment`, `editorial fashion`, `commercial social ad`, `influencer aesthetic`, `scroll-stopping visual`, `thumb-stopping composition`

**动态效果 (Motion)** ← 视频/Reels 专用
`smooth slow motion`, `dynamic zoom in`, `parallax scroll effect`, `kinetic energy`, `fluid transition`, `loopable motion`

## 4. 执行规则
1. 首先确认目标平台（Instagram / TikTok / 小红书 / 公众号）。
2. 查询平台决策表，确定尺寸比例和视觉风格方向。
3. 确认内容类型（种草/促销/故事/教程），选择对应视觉策略。
4. 调用 `build_prompt()`，在 scene 中描述平台场景，style_notes 中写入平台专属关键词。
5. 视频类内容（Reels/TikTok）使用 `gen_creative_video()`，静态图使用 `gen_creative_image()`。

## 5. 工具路由建议
- 使用 `build_prompt()` 构建 Prompt，scene 填平台名称和使用场景
- 静态素材使用 `gen_creative_image()`
- 动态素材/短视频使用 `gen_creative_video()`

## 6. 输出格式规范
- [📱 平台适配方案]：说明针对该平台的尺寸和视觉策略
- [🎨 风格决策]：选择该视觉风格的理由
- [📸 生成结果]：素材图像/视频链接
- [💡 发布建议]：最佳发布时间、配文方向、话题标签建议

## 7. 禁止事项
- ❌ 禁止在 Prompt 中描述文字内容（平台文案应由用户自行叠加）
- ❌ 禁止忽略平台尺寸差异，用同一 Prompt 生成所有平台素材
- ❌ 禁止使用过度精修、假感强的视觉风格（尤其是小红书场景）
- ❌ 禁止在 TikTok/Reels 封面 Prompt 中使用横版构图描述
