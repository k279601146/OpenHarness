# 电商主图与详情设计 (Listing & A+ Detail Suites)

本模块涵盖电商平台主图套图设计、多国多语言本地化排版、A+ 高级详情页视觉构架、爆款套图产品替换与图文批量翻译。

---

## 案例 1：电商平台主图套图

面向 Amazon、eBay、AliExpress、TEMU、SHEIN、TikTok Shop、Shopee、Lazada、Mercado Libre、Walmart、Etsy、Rakuten、Coupang、Shopify 等全球电商平台，根据平台规则与受众心理，自动规划完整的电商套图体系。

### 提示词模板

```text
帮我生成一组{平台名}套图，售卖到{国家}，{语言}，这款商品为{商品名}，卖点是{卖点描述}
```

### 7 屏标准化套图结构规范

Agent 在规划套图时，应按以下标准分工生成完整序列：

1. **白底主图（Hero / Main Image）**：
   纯白背景（RGB 255,255,255 或平台要求），主体占比 85% 以上，无多余配件，高清晰度还原商品全貌与真实反光。
2. **核心卖点图（Key Selling Point）**：
   放大 1~2 个最强差异化功能（如防水性能、超大吸力、降噪芯片），结合简洁视觉标注与局部特写。
3. **尺寸与规格图（Dimensions & Specs）**：
   等比标注长宽高尺寸、容量、重量与参照物对比，降低因尺寸误解引起的退货。
4. **多角度展示图（Multi-Angle Views）**：
   正面、背面、侧面 45°、顶部或展开图，消除消费者的视觉死角。
5. **生活场景图（Lifestyle Scene）**：
   将商品置于符合目标国文化审美的真实家居、办公或户外环境中，展示真实摆放美感。
6. **使用场景图（In-Use Demo）**：
   人物手持、操作或穿戴该商品，直观演示操作流程与使用方式。
7. **材质细节图（Material & Craftsmanship）**：
   微距或近景特写，呈现面料纹理、金属质感、缝线工艺或内部精密结构。
8. **选配/扩展屏（尺码表、参数清单、礼赠包装、系列汇总）**：
   针对服装补充详细尺码表（Size Chart），针对食品/数码补充参数汇总（Specs Summary）。

### 经典实战示例

- **示例 1：实木餐椅**
  - 输入：实木餐椅白底单品图
  - 输出 7 屏：白底主图、核心卖点图（进口白蜡木弧度）、尺寸图（座高与靠背尺寸）、多角度图（侧/仰/背）、生活场景图（北欧风餐厅）、使用场景图（家庭聚餐坐姿）、材质细节图（榫卯结构与木纹肌理）。
- **示例 2：运动水壶**
  - 输入：运动水壶单品图
  - 输出 6 屏：白底主图、多角度图、核心卖点图（双层真空锁温）、尺寸标定图（ml 与 oz 双刻度）、使用场景图（健身房/户外骑行补水）、材质细节图（食品级 Tritan/不锈钢与防漏硅胶密封圈）。
- **示例 3：运动 T 恤**
  - 输入：运动 T 恤平铺图
  - 输出 7 屏：核心卖点图（速干透气排汗孔）、产品参数图（面料成分比）、尺码表（S/M/L/XL 身高体重对照）、多角度图（平铺正反）、使用场景图（户外跑步动感）、材质细节图（高弹面料微距）、卖点总结图。

---

## 案例 2：多国主图套图 (Multi-Country Suites)

当卖家需要快速布局全球站点，且希望 AI 自动推断该国家电商消费者的排版偏好与文化元素时，使用精简多国模板。

### 提示词模板

```text
帮我生成一组{平台}套图，售卖到{国家}，{语言}
```

### 覆盖语言与市场文化范式

1. **中东市场（沙特、阿联酋）**：
   - 语言：阿拉伯语（RTL 从右向左文字排版）。
   - 视觉偏好：金色、绿色、尊贵感、家庭伦理与保守得体着装。
2. **日韩市场（日本、韩国）**：
   - 语言：日语、韩语。
   - 视觉偏好：精细化信息气泡、极简清透调色、精致排版、手写体小标与强调认证背书。
3. **欧洲市场（德国、英国、法国、西班牙、意大利、荷兰）**：
   - 语言：德语、英语、法语、西班牙语、意大利语、荷兰语。
   - 视觉偏好：严谨客观参数、环保认证、高对比度黑白灰或低饱和度莫兰迪色系、极简现代主义。
4. **拉美市场（墨西哥、巴西）**：
   - 语言：西班牙语、葡萄牙语。
   - 视觉偏好：高饱和暖色调、热情生动、突出性价比与多功能特性。
5. **东南亚市场（泰国、越南、印尼）**：
   - 语言：泰语、越南语、印尼语。
   - 视觉偏好：亮色系、促销角标、防晒防潮卖点显眼化。
6. **南亚与东欧（印度、孟加拉、俄罗斯、土耳其）**：
   - 语言：印地语、孟加拉语、俄语、土耳其语。

### 经典实战示例
- **示例 1：紫色波点连衣裙**：分别生成阿拉伯语版（长款端庄展示）、中文版（显瘦高腰卖点）、英文版（度假休闲风）、日文版（精致穿搭说明）、韩文版（流行日常风）、葡萄牙语版。
- **示例 2：无线吸尘器**：分别生成孟加拉语版、德语版（强调吸力千帕与续航分钟数）、西班牙语版、法语版、印地语版、俄语版（突出耐用与防缠绕）。
- **示例 3：圣诞主题手机壳**：分别生成印尼语版、意大利语版、荷兰语版、泰语版、土耳其语版、越南语版。

---

## 案例 3：A+ 产品详情视觉 (A+ / EBC Visuals)

面向亚马逊品牌注册（Brand Registry）卖家及 Shopify 独立站高端落地页，打造极具品牌叙事感的 A+ 页面模块（Modules）。

### 提示词模板

```text
这是一{商品描述}，帮我生成A+详情图，售卖到{国家}，{语言}
```

### 经典全套 A+ 屏序拆解

- **示例 1：高端茶叶礼盒**
  - **A+ 头屏（Banner Hero）**：大幅品牌愿景图，高山云雾茶园与精装礼盒并置，主标题呼应自然与传统工艺。
  - **设计与工艺屏**：内衬植绒、烫金封条与双层铁罐保鲜工艺特写。
  - **产品系列屏**：展示明前龙井、大红袍、正山小种等系列横向矩阵。
  - **易用与冲泡指南屏**：水温、冲泡时长与器具搭配图解。
  - **礼赠场景屏**：商务洽谈、节日走亲访友送礼陈列。
  - **使用场景屏**：茶室静心品茗、茶汤色泽透亮特写。
- **示例 2：天然胶水棒**
  - 头屏（核心环保卖点）+ 详情屏 1（无毒无味安全配方）+ 详情屏 2（强力粘合纸木实测）+ 详情屏 3（儿童手工课场景）+ 详情屏 4（不脏手旋转式设计）+ A+ 总结屏。
- **示例 3：奶茶饮品**
  - 核心原料原产地直采 + 茶底萃取工艺 + 0 反式脂肪酸健康标 + 冷热双饮场景 + 包装便携性。

### 社区高级创作者标杆案例

#### 示例 4：Sony A7 爆炸视图 (Exploded-View Diagram)
- **作者**：[@iamaiistudio](https://x.com/iamaiistudio)
- **提示词**：
  ```text
  Detailed exploded-view diagram of a Sony A7 mirrorless camera, with all internal components separated and clearly visible, each part labeled with its name. Technical product illustration style, clean white background, precise and informative layout.
  ```
- **核心要点**：工业设计插画风格、所有内部电子元件悬浮分离且清晰可见、精确技术引线标注、纯净白底、极具科技可信度。

#### 示例 5：建筑感产品目录页 (Architectural Product Design Catalog)
- **作者**：[@iamaiistudio](https://x.com/iamaiistudio)
- **提示词**：
  ```text
  Create a vertical 3:4 product design catalog page with a warm neutral paper-like background.

  Top section - lifestyle hero shot: place the product (use the uploaded image as the exact reference, preserving its form, proportions, materials, and identity without redesign) center-dominant with generous whitespace. Setting is a minimal architectural interior with a textured plaster wall and subtle concrete/stone floor. Lighting is natural sunlight angled from the side, soft but casting high-contrast shadows. Render in editorial lifestyle photography style, high realism, warm and muted color grading.

  Bottom section - technical specification panel laid out in a clean modular grid:
  - Bottom left and center: orthographic architectural line drawings showing front view, side view, and three-quarter cutaway/profile view. Lines in muted red or sepia, fine technical weight, with minimal editorial measurement and construction callouts.
  - Bottom right: 3-4 material swatch samples derived from the product's actual materials (fabric, leather, metal, wood, or plastic as applicable), in square or rectangular format with small editorial captions.

  Typography: minimal editorial style, subtle captions only, no large headlines, soft black or dark brown.

  Overall mood: design catalog / product design journal - architectural, premium, calm. No clutter, no bold colors, no heavy branding, no decorative graphics, no perspective distortion in the technical drawings.
  ```
- **核心要点**：上半部分为高审美建筑空间摄影，下半部分为建筑正交三视图线稿（正/侧/剖面）与真实面料色卡块（Swatches），呈现顶级工业设计手册质感。

#### 示例 6：逆向解构产品广告 (Reverse-Disintegration Concept)
- **作者**：[@iamaiistudio](https://x.com/iamaiistudio)
- **提示词**：
  ```text
  [PRODUCT] reassembling in midair from scattered pieces, reverse-disintegration effect, mechanical precision, each component suspended at a different depth, dark void background, high-concept product advertising, cinematic VFX.
  ```
- **核心要点**：零重力悬浮重组特效、精密机械部件分层定格、黑色深邃虚空背景、高端概念广告电影级特效。

---

## 案例 4：批量生成亚马逊套图 (Batch Amazon Suites)

**适用场景**：同品类多 SKU（如同一款式的 20 种颜色、不同规格型号），需要统一排版规范批量出图。
- **执行规则**：
  1. 固化套图骨架（白底、尺寸、功能、场景、材质）；
  2. 保持版式尺寸与文字占位恒定，仅按 SKU 输入图批量更新；
  3. 目前同一批次建议统一语言执行，以保证字体一致性。

---

## 案例 5：批量替换产品主图 (Viral Layout Product Swapping)

**适用场景**：爆款主图一键复刻，**换品不换版**。在不改动爆款素材排版、文案构图、背景氛围和模特肢体的前提下，将老款商品替换为新款商品。

### 输入要求
- 图 1：源新商品单品原图（白底或透明底最佳）。
- 图 2~7：已验证转化率极高的爆款主图套图。

### 提示词模板

```text
把图1商品将他替换到图2~7当中，除了替换的商品改变，保证其它内容不变
```

### 经典实战示例
- **示例 1：球形氛围灯（替换蘑菇灯爆款套图）**：将 6 张原蘑菇灯套图中的灯具精准替换为球形氛围灯，台面反光、卧室夜间环境、手持尺寸均保持原版效果。
- **示例 2：木质床头柜（替换红色储物柜套图）**：替换 4 张主图中的柜体，地毯、墙面挂画、盆栽等背景元素完全一致。

---

## 案例 6：批量主图图文翻译 (Batch Listing Translation)

**适用场景**：已有中文或其他语言的高质量设计主图，需要出海铺货到多国站点，要求**精准翻译文字且完美保留原图版式、字体粗细与配色**。

### 输入要求
上传所有包含文字标注的主图原图。

### 提示词模板

```text
将所有图片的文字翻译成{目标语言}
```

### 关键执行规则
1. **版式保留（Preserve Layout）**：文字位置、箭头指引、背景衬底框、边框装饰完全保留。
2. **字体与配色匹配**：翻译后的外文与原文色彩、投影、字重完全协调。
3. **实战示例**：
   - 示例 1：储物柜主图（中文 → 英文）：抽屉承重、防倾倒设计、静音导轨等参数文案无缝换为地道英文短语。
   - 示例 2：储物柜主图（多语言批量翻译）：一次性并行出德语、法语、西班牙语、日语版本。
