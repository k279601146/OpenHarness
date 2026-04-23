---
name: amazon-product-listing
description: 亚马逊商品列表图设计技能，封装了亚马逊平台主图、副图、A+页面的视觉决策规则，专为电商转化率优化。
version: "1.0.0"
domain: ecommerce
triggers:
  - 亚马逊
  - Amazon
  - 电商主图
  - 商品图
  - 产品图
  - listing
  - 主图
  - 副图
  - A+
  - 详情页
  - 电商素材
  - product listing
  - ecommerce
---

# Amazon Product Listing Kit
> 亚马逊的图片不是"好看"就够了，它是一个销售工具。每张图都有明确的转化任务：主图抢点击，副图消疑虑，A+ 页面促决策。

## 1. 核心原则
- 主图的唯一任务是在搜索结果页抢到点击——白底、主体大、清晰无杂。
- 副图的任务是消除购买疑虑——尺寸、材质、使用场景、细节特写，逐一击破。
- 亚马逊规则优先于美学：主图必须白底，主体占比 85% 以上，无水印无文字。
- 移动端优先：超过 60% 的亚马逊购物在手机上完成，图像在小屏上必须清晰。
- 竞品对比意识：同类目的视觉风格要差异化，在搜索结果页中脱颖而出。

## 2. 视觉决策树 (Visual Decision Rules)

### 按图片位置决策（最核心的决策）
| 图片位置 | 亚马逊规则 | 视觉任务 | 构图策略 | 禁止事项 |
|---------|---------|---------|---------|---------|
| 主图 (Main Image) | 纯白背景 (#FFFFFF)，主体占 85%+ | 搜索页抢点击 | 产品正面/3/4角度，无阴影 | 无文字、无水印、无道具 |
| 副图 1 (尺寸/规格) | 白底或浅色背景 | 消除尺寸疑虑 | 产品+尺寸标注线，比例参照物 | 文字可以有，但需清晰 |
| 副图 2 (使用场景) | 生活场景背景 | 建立使用想象 | 产品在真实环境中被使用 | 场景不能喧宾夺主 |
| 副图 3 (细节特写) | 白底或深色背景 | 展示材质/工艺 | 极端特写，材质纹理清晰 | 不能模糊 |
| 副图 4 (功能说明) | 简洁背景 | 传递核心卖点 | 产品+功能图标/箭头指示 | 文字不超过 5 个词/条 |
| 副图 5 (对比/证明) | 白底或对比背景 | 建立信任/差异化 | Before/After 或竞品对比 | 不能出现竞品品牌名 |
| A+ 模块图 | 品牌自定义 | 品牌故事+深度说服 | 全宽大图+文字区域 | 需符合亚马逊 A+ 规范 |

### 按产品类目决策
| 类目 | 主图风格 | 场景图风格 | 核心卖点展示方式 |
|------|---------|---------|---------------|
| 3C 电子 | 冷调白底，科技感 | 办公/家居使用场景 | 接口特写、屏幕显示效果 |
| 家居/家具 | 白底干净，多角度 | 真实家居环境搭配 | 材质纹理、尺寸标注 |
| 服装/鞋包 | 白底平铺或模特 | 穿搭场景、生活方式 | 面料特写、版型展示 |
| 美妆/护肤 | 白底+产品组合 | 使用前后对比 | 成分特写、质地展示 |
| 运动/户外 | 白底+动态场景 | 户外真实使用 | 功能细节、防水/耐用测试 |
| 食品/保健 | 白底+食材场景 | 餐桌/厨房场景 | 成分展示、份量参照 |
| 工具/五金 | 白底，多角度 | 工作场景使用 | 尺寸标注、材质特写 |
| 玩具/母婴 | 白底+彩色背景 | 亲子互动场景 | 安全材质、尺寸安全性 |

### 按竞争策略决策
| 竞争环境 | 视觉策略 | 差异化方向 |
|---------|---------|-----------|
| 同类产品多为白底平铺 | 加入轻微阴影或3/4角度 | 立体感差异化 |
| 同类产品多为深色背景 | 用纯白背景 | 干净清爽差异化 |
| 同类产品图片质量低 | 超高清细节特写 | 品质感差异化 |
| 同类产品无场景图 | 强化生活场景 | 使用想象差异化 |

## 3. Prompt 关键词库

**构图 (Composition)**
`pure white background`, `product centered`, `85% frame fill`, `3/4 angle view`, `front-facing product`, `multiple angle spread`, `flat lay top-down`, `scale reference included`

**光线 (Lighting)**
`even studio lighting`, `no harsh shadows`, `soft box illumination`, `clean product photography`, `no reflections on background`, `subtle drop shadow`, `professional e-commerce lighting`

**材质/质感 (Material & Texture)**
`crisp product edges`, `material texture visible`, `surface detail clarity`, `high resolution product shot`, `no motion blur`, `sharp focus throughout`

**氛围/风格 (Atmosphere & Style)**
`amazon product photography`, `commercial ecommerce style`, `clean professional`, `conversion-optimized`, `mobile-friendly clarity`, `retail-ready image`

## 4. 执行规则
1. 确认产品类目和需要生成的图片位置（主图/副图/A+）。
2. 查询图片位置决策表，明确亚马逊规则约束和视觉任务。
3. 查询产品类目决策表，确定风格方向。
4. 主图严格遵守：纯白背景、主体 85%+、无文字无水印。
5. 副图按"消疑虑"逻辑规划：尺寸 → 场景 → 细节 → 功能 → 信任。
6. 每张图单独调用 `build_prompt()`，task_type 填对应图片位置名称。

## 5. 工具路由建议
- 使用 `build_prompt()` 为每张图构建 Prompt，task_type 填 "amazon product image"
- 使用 `gen_creative_image()` 生成产品图，优先选择高精度模型
- 主图和副图分开生成，参数不同

## 6. 输出格式规范
- [🛒 Listing 图片规划]：图片数量、每张图的视觉任务说明
- [📐 主图方案]：构图角度、背景处理、主体占比说明
- [📸 生成结果]：各图片链接，标注图片位置和转化任务
- [⚠️ 合规检查]：主图是否符合亚马逊白底规则，是否有违规元素

## 7. 禁止事项
- ❌ 禁止主图使用非纯白背景（亚马逊会下架 listing）
- ❌ 禁止主图中出现任何文字、水印、边框、装饰元素
- ❌ 禁止主图中产品占比低于 85%（会降低搜索排名）
- ❌ 禁止在场景图中让背景比产品更抢眼
- ❌ 禁止使用过度 PS 的图像（亚马逊有真实性审核）
- ❌ 禁止在对比图中出现竞品品牌名称或 Logo
