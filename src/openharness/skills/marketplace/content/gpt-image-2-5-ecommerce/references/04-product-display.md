# 产品展示与环境精修 (Product Display & Retouching)

本模块涵盖纯白底产品精修、全方位多角度拆解、面料材质与颜色变体切换、AI 智能背景生成、高定制化描述背景置换，以及参考风格图无缝融合合成。

---

## 案例 1：纯白背景产品精修 (Clean White Studio Retouch)

**适用场景**：供应商提供的原片拍摄环境简陋（如工厂车间、办公室桌面、带杂物背景），需要一键抠图去杂，精修出达到亚马逊等国际电商平台严苛入仓标准的高清纯白底主图。

### 提示词模板

```text
生成白底精修图
```

### 关键执行规则
1. **纯白背景标准**：背景必须呈现完全无噪点的纯白色（RGB 255, 255, 255），无灰边、无毛边。
2. **边缘平滑度与透光**：对于毛绒、半透明塑料、玻璃边缘，自动处理半透明透光通道，杜绝粗暴生硬的羽化死黑边。
3. **真实接触投影（Ground Contact Shadow）**：在底部自然生成微弱的柔和接触阴影与镜面微倒影，让商品扎实落在地面上，避免“浮空感”。
4. **质感再精修**：去除商品表面由于手机拍摄产生的反光噪点或指纹污渍，增强金属、皮革、陶瓷的高级哑光或镜面反光。

### 经典实战示例
- **示例 1：居家杂乱场景产品图** → 高清无瑕白底精修图（自然保留底部柔和微阴影）。
- **示例 2：原始工厂实拍图** → 商业摄影棚级别白底渲染图。

---

## 案例 2：多角度产品视图 (Multi-Angle Product Views)

**适用场景**：为买家提供 360° 无死角视觉审视，全面展示商品的正面、侧面、背面、底部结构与俯视透视，常用于鞋靴、箱包、数码外设、小家电与家具。

### 提示词模板

```text
生成多角度的商品图
```

### 标准 6 视角分解
1. **正视图（Front View）**：对称正面对焦，展示主体品牌标识与主立面。
2. **45° 侧视图（Three-Quarter Perspective）**：展示深度与体积感，展现立体线条。
3. **后视图（Rear View）**：展示背板接口、提手、后跟缝线或拉链结构。
4. **底视图（Bottom / Sole View）**：鞋靴大底防滑花纹、电子产品脚垫与散热铭牌。
5. **俯视图（Top-Down Overhead）**：俯视鞋口开合、背包顶部提手与拉链仓位分布。
6. **局部特异角（Detail Angle）**：折叠状态或微距受力结构。

### 经典实战示例
- **示例 1：黄棕色户外登山靴**：正面系带特写、侧面 45° 支撑线条、后跟缓冲结构、鞋底耐磨齿纹、俯视鞋垫包裹感。
- **示例 2：多功能徒步鞋（其他款）**：全套 6 视角展开，防撞鞋头与抓地鞋底一览无余。

---

## 案例 3：材质与颜色变体 (Material & Color Variants)

**适用场景**：同一款式商品（如经典夹克、沙发、箱包、耳机），在完全不改动原有版型、剪裁、拉链、版面比例的前提下，快速探索或批量生产多种不同**面料材质与季节限定配色**。

### 提示词模板

```text
修改商品材质，人物衣服分别变成：{材质1}、{材质2}和{材质3}
```

### 材质与肌理词汇库
- **麂皮面料（Suede）**：表面带有细腻微绒毛，吸光不反光，呈现深邃哑光高级感。
- **丹宁牛仔（Denim）**：清晰斜纹织物肌理，边缘带有自然的酵洗水洗白痕。
- **条绒灯芯绒（Corduroy）**：粗细均匀的立体凸条绒道，带复古温润光感。
- **头层牛皮（Full-Grain Leather）**：真实自然皮纹褶皱，轻微油脂光泽。
- **防撕裂机能面料（Ripstop Nylon）**：微细十字网格纹理，带户外防水涂层光泽。

### 经典实战示例
- **示例 1：绿色男士夹克** → 变体 1 浅灰色细腻麂皮、变体 2 深棕色酵洗牛仔、变体 3 酒红色复古条绒灯芯绒。
- **示例 2：黑色机车皮夹克** → 哑光复古做旧皮、高光漆皮、编织皮革等变体。

---

## 案例 4：智能背景生成 (Smart Background Generation)

**适用场景**：只有白底单品图，无需繁琐的美术 prompt，让 AI 根据商品的品类属性自动推导最契合的商业光影、空间材质与生活情调。

### 提示词模板

```text
生成合适的商品图
```

### AI 自动推导逻辑
- **休闲零食类**：自动匹配温暖原木餐桌、周末露营野餐垫、午后阳光与绿植散景。
- **高端护肤品**：自动匹配微水泥台面、水波倒影、鹅卵石、晨光穿透玻璃的清透柔光。
- **数码科技类**：自动匹配深灰极简电竞桌、柔和冷调轮廓光、极简线缆。
- **实战示例**：
  - 示例 1：包装零食 → 4 组明亮休闲生活场景。
  - 示例 2：护肤精华液 → 4 组水光水疗大理石高级场景。

---

## 案例 5：自定义描述换背景 (Custom Described Background)

**适用场景**：品牌策划对画面有极高要求，希望指定特定氛围、地理环境、陈列道具与电影级用光。

### 提示词模板

```text
帮我图中的商品换一个背景：{背景描述}
```

### 经典实战示例与社区神作

- **基础实操**：
  - 示例 1：登山靴 → 置于崎岖险峻的冰川岩石悬崖，远处是朝阳雪山，突出极端防护与抓地力。
  - 示例 2：香水瓶特写 → 静置在光滑白色水磨石上，背景是柔和淡蓝湖泊与雪山，氛围清冷飘逸。

#### 示例 3：Solaris 防晒霜能量保护罩广告 (The Invisible Shield)
- **作者**：[@iamrealsnow](https://x.com/iamrealsnow)
- **提示词原文**：
  ```text
  SUNSCREEN AD, "THE INVISIBLE SHIELD"

  Luxury skincare advertising masterpiece, a colossal premium sunscreen bottle standing on a pristine tropical shoreline at golden hour, powerful beams of sunlight crashing down from the sky and splitting apart upon contact with a transparent protective energy dome radiating from the sunscreen, millions of sparkling UV particles dissolving into golden dust before reaching flawless skin, crystal clear ocean reflections, flowing water suspended in mid air around the product, microscopic droplets catching cinematic sunlight, ultra realistic textures revealing every detail of the bottle surface, luxury beauty campaign aesthetics, dramatic volumetric lighting, glowing atmospheric haze, premium white and gold color palette, futuristic protection technology visualized as elegant light waves, hyper detailed environment, commercial photography perfection, award winning advertising design, photorealistic rendering, 16K ultra resolution, global skincare brand campaign, masterpiece quality.

  Text Overlay:
  SUNSCREEN

  Tagline:
  "Protect Every Ray. Reveal Every Glow."
  ```
- **核心要点**：金色海滩、阳光与能量罩撞击粒子化、水滴悬浮、白金配色、未来感防护科技具象化。

#### 示例 4：主题化镂空陀飞轮腕表 CAD 宫格 (Luxury Watch CAD System)
- **作者**：[@Gdgtify](https://x.com/Gdgtify)
- **提示词原文**：
  ```text
  2x2 grid, do this for 4 stunning themes, 16:9 [luxury_watch_cad_system] base_chassis: "hyper-luxury skeletonized tourbillon watch" conceptual_theme: "[$theme, e.g., the samurai shogun]" <mechanism_generation> - ai inference: do not just paint the watch. build the gears, hands, and face using elements from the [$theme]. - example: if ocean, the gears look like coral patterns and the hands are trident spears. if space, the center is a glowing meteorite. - materials: sapphire crystal, forged carbon, rose gold, glowing tritium tubes. </mechanism_generation> <photography> a macro product shot of the watch face. extreme close-up. lighting: dark background, sharp rim lighting catching the metallic edges of the gears. resolution: 8k, razor-sharp focus on the tourbillon movement. vibe: impossibly expensive, intricately engineered, a masterpiece of micro-mechanics. </photography>
  ```
- **核心要点**：2x2 四主题宫格、机械结构根据主题智能重构（海洋珊瑚齿轮/三叉戟指针、太空陨石核心）、暗调锐利边缘轮廓光、超微距陀飞轮机械精密感。

#### 示例 5：极简北欧精华液静物 (Minimalist Scandinavian Still Life)
- **作者**：[@iamaiistudio](https://x.com/iamaiistudio)
- **提示词原文**：
  ```text
  Minimalist studio product photography, a small transparent glass facial oil dropper bottle with a black rubber pipette cap, containing pale pink serum with suspended dried pink floral elements, centered on a natural raw wooden block with visible grain and split texture. Tall matte white skincare box on the left labeled "HUILE ÉCLAT VISAGE" with clean black typography and subtle logo near the bottom. Clear cylindrical glass vase on the right filled with water and thin stems of dried pink gypsophila extending upward. Composition rests on a smooth matte pastel pink surface against a matching seamless pink studio background. Strong directional soft light from the left casts long natural-style shadows of the flowers onto the background, with gentle highlights on the glass, subtle reflections on the serum bottle, and soft texture on the wooden block. Straight-on tabletop camera angle, all objects in sharp focus. Color palette: blush pink, soft rose, warm light wood, clean white, transparent glass. Premium Scandinavian minimalist skincare aesthetic, ultra-realistic, studio-grade.
  ```
- **核心要点**：玻璃滴管瓶、天然木块原木裂纹、哑光包装盒与水培干花配景、侧向强光拉长自然投影、粉白温润北欧极简美学。

---

## 案例 6：参考图背景生成 (Reference Image Background Transfer)

**适用场景**：找到了一张非常喜欢的竞品或摄影大片背景（图 2），希望将自己的商品（图 1）无缝搬入该背景风格中，保持光影、台面反射与色调深度统一。

### 输入要求
- 图 1：自己的商品图
- 图 2：目标参考背景图

### 提示词模板

```text
图一是我的{商品}，参考图二背景生成
```

### 经典实战示例
- **示例 1：粉色复古小汽车模型 + 绿色热带森林背景** → 复古小车自然放置在森林深处的粗糙木桩台面上，叶片阴影斑驳洒落在车身表面。
- **示例 2：红色奢华口红 + 黑金奢华大理石背景** → 口红膏体旋出，斜倚在黑金大理石台面，反射出温润的金色暗光。
