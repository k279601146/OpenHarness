# 核心工作流与图像生成工具规范 (Core Workflows & Tool Guide)

本模块收录 GPT Image 2.5 核心电商标杆案例——**一个产品，三种电商用法**，以及在 OpenHarness 中执行商业图片生成必须遵守的 **`generate_image` 标准工具契约与 GPT-Image 逻辑模型解耦规范**。

---

## ✨ GPT Image 2.5：一个产品，三种电商用法

围绕同一款黄色护肤品原图（白底产品图），展示三种高频电商应用路径：实拍换场景、UGC 推广图、多语言市场本地化。

### 案例 31：实拍换场景，产品不变 (Change the Scene, Keep the Product)

**应用场景**：替换实拍商品周围的杂乱背景或过时布景，保持商品形状、包装、瓶盖、品牌 Logo 和印刷标签绝对一致，并自然匹配新场景的定向光影与接触投影。

**提示词模板**：

```text
Edit the supplied real product photograph. Replace only the surrounding scene with {scene_description}. Keep the product itself unchanged: preserve its exact shape, proportions, yellow packaging, cap, logo, label text, material and visible details. Match the new background lighting and contact shadows naturally. Do not redesign, relabel, duplicate or obscure the product.
```

**关键执行规则**：
1. **产品冻结（Freeze Product）**：明确指定商品包装颜色（如 yellow packaging）、瓶盖、Logo、标签字体等关键视觉锚点，严禁模型重新设计或产生虚构文字。
2. **接触投影（Contact Shadows）**：要求模型根据新环境光源方向补充台面/地面的真实物理接触阴影与环境闭塞光（Ambient Occlusion），消除悬浮假感。
3. **输出场景参考**：
   - 场景 1：极简大理石洗手台，柔和侧逆光
   - 场景 2：晨光洒入的浴室窗台，带微湿水雾感
   - 场景 3：浅色木质托盘与自然绿植点缀
   - 场景 4：水光潋滟的清澈浅水景，波光倒影
   - 场景 5：高级水疗 SPA 氛围，暖调微光

---

### 案例 32：UGC 产品推广图 (UGC-Style Product Promotion)

**应用场景**：利用纯白底商品图，生成真实达人（KOL/KOC）风格的随手拍带货图，以及面向多个国家/地区的社交媒体拼图素材。

**提示词模板**：

```text
Using the supplied white-background product photo as the product reference, create a UGC-style skincare promotion image for {target_market}. Show an adult creator naturally holding the same product in a believable everyday setting. Preserve the exact product packaging, color, proportions, logo and label. Use a casual phone-camera composition and natural lighting. If text is needed, use only {approved_copy} in {language}. Do not invent testimonials, certifications or product benefits.
```

**关键执行规则**：
1. **达人真实感（Authentic Vibe）**：强调成年创作者（adult creator）、日常可信生活场景（believable everyday setting）、自然光（natural lighting）与手机镜头视角（phone-camera composition）。
2. **手持合理性**：握持手势不得遮挡商品核心 Logo 与关键品名。
3. **文本合规约束**：若需配文，必须使用品牌方已核准文案（`{approved_copy}`），严禁 AI 凭空编造用户评价、功效承诺或认证标识。
4. **多市场拼图扩展**：可将欧美、东亚、东南亚不同肤色与风格的达人图整合成 4 宫格或多图拼接，作为广告投放的多变体测试素材。

---

### 案例 33：不同语言市场的电商图 (Localized E-Commerce Visuals)

**应用场景**：使用单张产品参考图，针对日本、法国、西班牙、韩国、中国台湾、泰国等不同语言与消费习惯的市场，制作地道的电商详情套图与社交营销主图。

**提示词模板**：

```text
Create an e-commerce image for {target_market} in {language}, using the supplied white-background product photo as the reference. Preserve the product shape, color, packaging, logo and label. Build a clear {asset_type} layout with a prominent product, readable local-language typography and {approved_product_copy}. Adapt the composition to the target market. Use only supplied product facts; do not invent specifications, ingredient claims or endorsements.
```

**关键执行规则**：
1. **本土化设计范式**：
   - **日本市场**：注重细腻排版、多层次信息说明、高信任度小标签、柔和自然配色。
   - **欧美市场（法/西）**：注重留白艺术、极简现代感、高冲击力摄影光影。
   - **韩国市场**：强调水光清透感、精致极简字体、潮流美学构图。
   - **东南亚市场（泰/越/印尼）**：色彩明亮丰富、卖点突出、强调促销氛围与视觉抓人度。
2. **多语言字体可读性**：要求生成地道、清晰且无乱码的本地语言字符（Typography），严格杜绝拼写错误。
3. **事实边界（Facts Only）**：仅使用提供的商品事实，不得擅自补充成分浓度或权威认证。

---

## 🛠️ OpenHarness 图像生成工具链与 GPT-Image 规范

在 OpenHarness 体系中，生图执行严格遵循 **三层架构标准** 与 **逻辑模型与 Provider 解耦架构**。Agent 严禁调用外部第三方 API 或自行使用 curl 脚本绕过计费，所有图片生成与编辑必须通过系统的标准工具 `generate_image` 发起。

### 1. 三层架构职责分工与安全计费边界

```text
[ Skill 技能层 (本手册) ]
  • 思考与意图层：组织提示词模板、装配占位符、注入商品一致性锁、质检核对
  • 严禁行为：不得硬编码外部 Provider URL、第三方 API Key、curl 命令或绕过计费
             │
             ▼ 调用标准工具
[ Tool 工具契约层 (generate_image) ]
  • 标准协议输入：intent, scenario, prompt, brief, output, references, edit_policy
  • 严禁行为：不向 Agent 暴露任何 Provider 私有字段或技术端点
             │
             ▼ 后端统一网关调度
[ SaaS Backend 执行层 (媒体网关) ]
  • 核心职责：鉴权授权、计费预扣 (Billing Reservation)、模型健康路由、SSRF 安全出站、产物校验与 Artifact 注册
  • 渠道解耦：网关根据配置自动将逻辑模型转发至最优 Provider (如 gpt_image / apimart_image)，对上层透明
```

---

### 2. GPT-Image 逻辑模型选型指南

根据 `logical-model-provider-gpt-image-authority.md` 规范，Agent 在调用 `generate_image` 时，可根据电商生产需求在 `model_id` 中选择对应逻辑模型：

| 逻辑模型 ID | 默认分辨率 | 定位与推荐场景 | 支持画质档位 | 透明背景 | 参考图上限 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gpt-image-2.5-flare` | 1K | **速度优先（Speed-first）**。极低延迟、高吞吐量；适合整盘多 SKU 主图快速打样、社媒多变体 A/B 测试、草案验证。 | `auto`, `low`, `medium`, `high`, `xhigh`, `max` | **是（原生支持 `transparent`）** | 16 张 (20MB) |
| `gpt-image-2.5-sunburst` | 2K | **高精优先（Quality-first）**。极限细节与复杂语义渲染；适合 A+ 详情大图、包装微距特写、极简奢华大片与文字排版。 | `auto`, `low`, `medium`, `high`, `xhigh`, `max` | **是（原生支持 `transparent`）** | 16 张 (20MB) |
| `gpt-image-2` | 2K | **综合平衡型**。成熟稳定，适合常规概念设计与通用电商配图。 | `auto`, `low`, `medium`, `high` | 否（仅支持 `opaque`） | 16 张 (20MB) |

---

### 3. `generate_image` 电商场景调用标准契约

Agent 在执行电商图像任务时，必须通过标准化结构装配工具调用参数：

#### 核心调用字段说明
- **`model_id`**：指定逻辑模型，推荐 `"gpt-image-2.5-flare"` 或 `"gpt-image-2.5-sunburst"`。
- **`intent`**：
  - `"edit"`：用于垫图编辑、换背景（案例 31）、模特替换、商品换版等图生图场景；
  - `"generate"`：用于根据描述从零全新生成场景或概念图。
- **`scenario`**：固定为 `"product_or_commerce"` 或 `"product"`。
- **`prompt`**：填入经过本 Cookbook 模板装配并注入商品一致性保护锁的终版提示词。
- **`brief`**（结构化生产简报）：
  ```json
  {
    "purpose": "电商平台主图制作与背景替换",
    "subject": "黄色便携护肤乳液瓶",
    "composition": "居中构图，商品占比 85%，留白自然",
    "style": "商业静物摄影，极简现代风",
    "constraints": "Strictly preserve packaging, cap, logo, and label text unchanged."
  }
  ```
- **`output`**（规格控制）：
  - `aspect_ratio`：电商平台比例（如 `"1:1"` 正方主图、`"3:4"` 或 `"4:5"` 社交电商竖图、`"16:9"` 横版广告）；
  - `size_tier`：分辨率阶梯（`"1K"`, `"2K"`, `"4K"`）；
  - `quality`：画质档位（Flare 推荐 `"medium"`，Sunburst 推荐 `"high"` 或 `"xhigh"`）；
  - `transparent_background`：如需输出免抠图白底或透明底素材，设为 `true`（2.5 系列原生支持）；
  - `count`：单次输出张数（1~4 张）。
- **`references`**（参考图列表）：
  - 必须使用 SaaS 托管的稳定产物引用（如 `[{"input_ref": "artifact:art_123456", "role": "edit_target"}]`）；
  - 严禁传入不可靠的外网临时 URL。
- **`edit_policy`**（编辑保护策略）：
  - `preserve_identity: true`（强制锁定商品本体）；
  - `preserve_composition: true`（保持核心构图比例）；
  - `allow_crop: false`。
- **`text_policy`**（图内文字策略）：
  - 多语言主图时配置 `mode: "exact"` 或 `"embedded"`；
  - 指定 `exact_text` 与 `language`，并设置 `text_accuracy_required: true`。

---

### 4. 多 SKU 规模化批量生产的 Agent 自动化流水线

在 OpenHarness 中，面对整盘上百款 SKU、多语言多平台的生产需求，**批量化是由 Agent 的多轮工具调度流水线实现的，而非绕过系统的外部脚本**：

1. **商品资产清单化**：
   Agent 读取用户提供的商品 SKU 列表与对应的原图素材，将其在工作区中注册为受控的 `artifact` 引用。
2. **提示词工厂自动化装配**：
   Agent 针对不同 SKU 的品类、卖点、目标站点国家（如美区 Amazon、日区 Rakuten、东南亚 Shopee），按本 Cookbook 规则批量装配出对应的 7 屏提示词。
3. **标准化工具循环调用**：
   Agent 依次针对每个 SKU 调用 `generate_image` 工具发起到 SaaS 媒体网关。
4. **系统内生保障与闭环**：
   - **自动计费预扣（Reservation）**：SaaS 后端原子化预扣积分与记账，完全受控；
   - **多渠道熔断与故障自愈**：媒体网关根据上游 Provider（官方或聚合渠道）的健康度自动切换与重试，无需 Agent 介入；
   - **成果沉淀与交付**：所有生成的图片均作为用户的专属 Artifact 保存，支持前端画布（Canvas）拖拽、多图对比、一键下载与批量归档。
