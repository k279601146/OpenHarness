---
name: marketing-brochures
description: 营销手册与宣传册设计技能，封装了可直接印刷的专业宣传物料的视觉决策逻辑，适用于产品手册、企业画册、活动折页、展会物料。
version: "1.0.0"
domain: branding
triggers:
  - 宣传册
  - 手册
  - 画册
  - 折页
  - brochure
  - 印刷
  - 物料
  - 展会
  - 企业画册
  - 产品手册
  - 营销手册
  - flyer
  - catalog
---

# Marketing Brochures
> 宣传册是品牌在物理世界的代言人。它必须在没有人解释的情况下，独立完成"吸引注意 → 传递价值 → 促成行动"的完整销售动作。

## 1. 核心原则
- 印刷物料的视觉层次必须在 3 秒内被读懂：标题 → 核心图像 → 支撑信息。
- 颜色必须考虑印刷色差：屏幕 RGB 颜色在印刷后会偏暗，设计时需预留补偿。
- 留白是奢侈品的语言：高端品牌用留白传递品质感，信息密度越低越显档次。
- 图像质量决定印刷质量：生成图像分辨率必须满足 300 DPI 印刷标准。
- 每一页都必须有视觉锚点：读者的眼睛需要一个"先看哪里"的引导。

## 2. 视觉决策树 (Visual Decision Rules)

### 按手册类型决策
| 类型 | 页数 | 版式风格 | 图文比例 | 核心目标 |
|------|------|---------|---------|---------|
| 单页传单 (Flyer) | 1页 | 强冲击，信息高度浓缩 | 图 60% / 文 40% | 一个核心信息，一个行动号召 |
| 三折页 (Trifold) | 6面 | 分区清晰，信息递进 | 图 50% / 文 50% | 封面吸引 → 内页说服 → 背面联系 |
| 产品手册 (4~8页) | 4~8页 | 专业，产品为主角 | 图 65% / 文 35% | 产品展示 + 规格参数 + 使用场景 |
| 企业画册 (12~24页) | 12~24页 | 品牌叙事，情感驱动 | 图 70% / 文 30% | 品牌故事 + 实力展示 + 信任建立 |
| 展会物料 | 1~2页 | 远距离可识别，信息极简 | 图 75% / 文 25% | 3 米外能看清核心信息 |

### 按行业风格决策
| 行业 | 版式风格 | 颜色方案 | 图像风格 | 字体方向 |
|------|---------|---------|---------|---------|
| 科技/SaaS | 网格化，模块清晰 | 深蓝/白/科技蓝 | 产品截图+场景图 | 无衬线，现代感 |
| 奢侈品/高端 | 大留白，极简 | 黑/金/白 | 大图全出血，极少文字 | 细衬线，优雅 |
| 医疗/健康 | 整洁，信息清晰 | 白/蓝绿/浅灰 | 真实场景，专业感 | 清晰无衬线 |
| 房地产 | 大图震撼，品质感 | 深色/金色/白 | 建筑全景+室内精修 | 衬线+无衬线混排 |
| 食品/餐饮 | 温暖，食欲感 | 暖色/橙/奶油 | 食物特写，蒸汽感 | 圆润字体 |
| 工业/制造 | 严谨，参数导向 | 深灰/橙/白 | 产品实拍+工厂场景 | 粗体无衬线 |

### 按页面功能决策
| 页面功能 | 视觉策略 | 构图重点 | Prompt 关键词 |
|---------|---------|---------|-------------|
| 封面 | 最强视觉冲击，品牌第一印象 | 全出血大图，品牌 Logo 显著 | `full-bleed hero image`, `brand cover`, `impactful` |
| 产品展示页 | 产品为绝对主角 | 白底或渐变背景，多角度 | `product hero shot`, `clean background`, `multiple angles` |
| 场景应用页 | 产品在真实使用中 | 生活场景，人与产品互动 | `lifestyle in-use`, `real environment`, `contextual` |
| 数据/成就页 | 信息可视化，建立信任 | 图表+数字+简洁背景 | `infographic style`, `data visualization`, `clean layout` |
| 封底/联系页 | 行动号召，联系信息 | 简洁，品牌色背景 | `call to action`, `contact page`, `brand color background` |

## 3. Prompt 关键词库

**构图 (Composition)**
`full-bleed layout`, `grid-based composition`, `generous white space`, `visual hierarchy`, `F-pattern reading flow`, `Z-pattern layout`, `centered focal point`, `asymmetric balance`

**光线 (Lighting)**
`professional studio lighting`, `clean product photography`, `soft box lighting`, `even illumination`, `no harsh shadows`, `print-ready quality`

**材质/质感 (Material & Texture)**
`high resolution 300dpi`, `crisp sharp details`, `premium paper texture feel`, `glossy finish aesthetic`, `matte sophisticated look`

**氛围/风格 (Atmosphere & Style)**
`corporate professional`, `luxury editorial`, `clean minimal design`, `bold commercial`, `trustworthy brand`, `premium quality feel`, `print-ready design`

## 4. 执行规则
1. 确认手册类型（传单/折页/产品手册/企业画册）和行业。
2. 查询类型决策表，确定页数、图文比例和版式风格。
3. 查询行业风格决策表，确定颜色方案和图像风格。
4. 按页面功能逐页规划视觉方案，每页调用一次 `build_prompt()`。
5. 封面页优先生成，作为整体视觉基调的锚点。
6. 提醒用户：生成图像用于印刷时需确认分辨率满足 300 DPI。

## 5. 工具路由建议
- 使用 `build_prompt()` 为每个页面构建 Prompt，task_type 填 "brochure page design"
- 使用 `gen_creative_image()` 生成各页面视觉稿
- 封面页单独生成，其余页面可批量生成

## 6. 输出格式规范
- [📋 手册规划]：类型、页数、整体视觉风格方向
- [🎨 视觉决策]：颜色方案、图像风格、版式逻辑的选择理由
- [📸 页面生成结果]：各页面图像链接，标注页面功能
- [🖨️ 印刷备注]：分辨率说明、出血线建议、色彩模式提醒（RGB→CMYK）

## 7. 禁止事项
- ❌ 禁止在 Prompt 中描述具体文字内容（文案由用户提供，不由 AI 生成）
- ❌ 禁止忽略印刷分辨率要求（屏幕 72dpi 的图像不能用于印刷）
- ❌ 禁止在单页传单中塞入超过 3 个核心信息点
- ❌ 禁止使用纯 RGB 荧光色（印刷后会严重偏色）
- ❌ 禁止忽略出血区域（印刷物四边需要 3mm 出血）
