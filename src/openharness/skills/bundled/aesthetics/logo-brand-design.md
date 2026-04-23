---
name: logo-brand-design
description: Logo 与品牌标识设计专用技能，封装了标志设计的视觉决策逻辑，适用于生成 LOGO、品牌 VI 系统、标志变体。
version: "1.0.0"
domain: branding
triggers:
  - logo
  - LOGO
  - 标志
  - 品牌
  - brand
  - 商标
  - 图标
  - icon
  - 徽标
  - VI
---

# Logo & Brand Design
> 将品牌定位转化为视觉标志的设计决策系统。核心任务：让一个图形承载品牌的性格、行业属性和记忆点。

## 1. 核心原则
- 标志必须在 16px 和 1000px 两种尺寸下都清晰可辨——复杂度是敌人。
- 颜色传递情绪，形状传递性格，字体传递调性，三者必须统一。
- 好的 Logo 在黑白状态下依然成立，颜色是加分项而非依赖项。
- 避免流行趋势，追求 10 年后依然不过时的视觉语言。
- 负空间（留白）是设计的一部分，不是空白。

## 2. 视觉决策树 (Visual Decision Rules)

### 按行业性格决策
| 行业 | 形状语言 | 颜色方向 | 字体风格 | 代表关键词 |
|------|---------|---------|---------|-----------|
| 科技 / SaaS | 几何形、圆角矩形、模块化 | 蓝色系、深色背景 | 无衬线、等宽 | `geometric`, `modular`, `tech-minimal` |
| 奢侈品 / 高端 | 细线条、对称、徽章形 | 金色、黑白、深酒红 | 衬线、细体 | `serif`, `luxury crest`, `gold foil` |
| 食品 / 餐饮 | 圆形、有机曲线、手绘感 | 暖色、橙红、奶油白 | 圆润无衬线、手写体 | `organic shape`, `warm palette`, `handcrafted` |
| 医疗 / 健康 | 十字、圆形、流线型 | 蓝绿、白色、浅灰 | 清晰无衬线 | `clean`, `trustworthy`, `medical blue` |
| 创意 / 文化 | 不规则、解构、拼贴 | 高饱和、撞色 | 展示字体、实验性 | `bold`, `expressive`, `avant-garde` |
| 环保 / 自然 | 叶形、波浪、有机轮廓 | 绿色系、大地色 | 手写、圆润 | `earthy`, `organic`, `sustainable` |

### 按 Logo 类型决策
| 类型 | 适用场景 | Prompt 构建重点 |
|------|---------|---------------|
| 图形标志 (Pictorial) | 品牌已知名，图形独立传播 | 聚焦图形本身，极简轮廓，单色可识别 |
| 文字标志 (Wordmark) | 品牌名本身有记忆点 | 字体选择、字距、独特字形改造 |
| 组合标志 (Combination) | 新品牌，需要图文并存 | 图形与文字的比例关系、对齐方式 |
| 徽章标志 (Emblem) | 传统、机构、高端品牌 | 封闭轮廓、内部层次、印章感 |
| 抽象标志 (Abstract) | 多元业务，难以具象化 | 几何抽象、动态感、可延展性 |

### 按输出用途决策
| 用途 | 背景 | 尺寸比例 | 特殊要求 |
|------|------|---------|---------|
| 主版本 | 白色/透明 | 1:1 或 4:3 | 最高精度，含安全区 |
| 深色背景版 | 深色 | 同主版本 | 反白/浅色版本 |
| App 图标 | 品牌色 | 1:1 | 圆角裁切友好，无细节 |
| 横版 Banner | 透明 | 3:1 | 图文横排，留右侧空间 |

## 3. Prompt 关键词库

**构图 (Composition)**
`centered composition`, `negative space utilization`, `balanced symmetry`, `icon on white background`, `isolated logo mark`, `clean vector aesthetic`

**风格 (Style)**
`flat design`, `minimalist logo`, `vector illustration`, `bold geometric`, `hand-crafted feel`, `timeless design`, `scalable mark`

**材质/质感 (Material & Texture)**
`smooth vector`, `clean edges`, `no gradients`, `solid color fill`, `monochrome version`, `crisp lines`

**氛围/调性 (Atmosphere & Tone)**
`professional`, `trustworthy`, `innovative`, `premium brand identity`, `memorable`, `distinctive`, `versatile`

## 4. 执行规则
1. 从用户描述中提取：行业类型、品牌性格词（3个以内）、Logo 类型偏好。
2. 查询上方决策树，确定形状语言、颜色方向、字体风格。
3. 调用 `build_prompt()`，task_type="logo design"，将决策树结论写入 style_notes。
4. 生成时优先输出白色背景版本，再输出深色背景版本。
5. 如用户未指定颜色，根据行业决策树自动推荐，并告知用户推荐理由。

## 5. 工具路由建议
- 使用 `build_prompt()` 构建 Logo 生成 Prompt，task_type 填 "logo design"
- 使用 `gen_creative_image()` 生成标志图像，建议 model 选择支持矢量风格的模型
- 多版本生成：主版本 → 深色版 → 图标版，三次调用

## 6. 输出格式规范
- [🎨 品牌定位解读]：基于用户描述，说明选择该视觉方向的理由
- [📐 设计决策]：形状语言 / 颜色方案 / 字体风格的选择依据
- [📸 生成结果]：Logo 图像链接（主版本 + 深色版）
- [💡 延伸建议]：1~2 条品牌 VI 延伸方向

## 7. 禁止事项
- ❌ 禁止在 Logo Prompt 中描述复杂场景或背景故事（会导致生成插画而非标志）
- ❌ 禁止使用超过 3 种颜色（除非用户明确要求彩虹/渐变风格）
- ❌ 禁止在 Prompt 中加入文字内容（模型无法准确渲染文字）
- ❌ 禁止生成与知名品牌视觉高度相似的设计
