# 产品互动与场景带货 (Product Interaction & Lifestyle)

本模块涵盖手部真实握持特写、为商品场景添加全新模特、指定参考人物真实互动，以及萌宠与宠物用品玩耍互动。

---

## 案例 1：手持产品特写 (Hand-held Product Close-up)

**适用场景**：通过真人手部握持，最直观地体现商品的**真实物理尺寸比例（Scale）**、质感手感、开箱体验与使用手势，广泛用于美妆口红、数码配件、五金工具、日化瓶罐。

### 提示词模板

```text
一只手拿着这个商品，{场景描述}，商品颜色不变
{动作描述}
```

### 手部生成解剖学保护准则
1. **手指与关节结构**：严格约束生成正常 5 根手指，指节弯曲自然，避免骨骼畸变或多指、融指。
2. **握持合理性（Grip Physics）**：手指受力点必须贴合商品圆柱形或方形表面，避免悬空握持或穿模。
3. **品牌保护**：手部握持位置应避开包装正面的核心 Logo 和主要文字区域。

### 经典实战示例
- **示例 1：粉色唇蜜**：一只保养得当的女性纤细手指轻握管身，时尚摄影棚柔光背景，商品颜色与金属反光完全不变。
- **示例 2：木柄多功能拖把**：粗壮有力手掌自然握紧实木把柄，展现下压拖地动作，地面水痕倒影清晰。

---

## 案例 2：生成人物互动场景 (Generated Character Interaction)

**适用场景**：用户已拥有精美的商品场景图（如家具样板间、车内空间、客厅或户外露台），需要引入契合目标受众的人物模特进行自然入镜互动，烘托生活氛围。

### 提示词模板

```text
给这个商品场景添加人物模特，模特要求是：{人物描述}，{姿势}，{动作}
```

### 关键执行规则
- **比例透视对齐（Perspective Match）**：新人物模特的高度、视平线与阴影必须严格与原场景中的沙发、门窗、桌椅等参照物保持透视一致。
- **情感与眼神导向**：模特的眼神应自然看向商品、窗外或与画面发生情感共鸣，避免呆滞盯镜头。

### 经典实战示例与社区案例
- **示例 1：中国风红色古典拱门** → 添加身着改良刺绣旗袍的年轻东方女子，侧身优雅漫步入场，手中持商品玩偶。
- **示例 2：银红专业降噪耳机** → 添加年轻都市女性，头部自然佩戴该耳机，闭目沉浸式聆听音乐。

#### 示例 3：奢华品牌编辑级海报 (Luxury Editorial Poster)
- **作者**：[@iamaiistudio](https://x.com/iamaiistudio)
- **提示词原文**：
  ```text
  [attach a luxury product photo]
  BRAND: [enter your brand name]

  Design a single high-end editorial poster. Preserve the product exactly as shown, unaltered. Identify the brand and position its authentic official logo with correct proportions and a subtle print texture in the most fitting location. Include a complementary attractive model naturally wearing or holding the product. Deep rich colors, HDR quality, premium studio lighting, clean minimal background, ample negative space, ultra-sharp 8K output. No additional text or watermarks.
  ```
- **核心要点**：保留产品 100% 不变、官方 Logo 等比放置并带微弱印刷压纹、气质出众的超模自然佩戴/手持、充足留白与浓郁电影光影。

---

## 案例 3：参考人物产品互动 (Reference Character Product Interaction)

**适用场景**：品牌需要维持统一的代言人形象，或需要将特定的真人模特面孔置入不同的商品使用情境中，进行身临其境的深度互动。

### 输入要求
- 图 1：商品及所在场景环境图
- 图 2：指定人物的正面/半身参考照（锁定五官面部）

### 提示词模板

```text
给图一的商品场景添加图二人物模特，{动作描述}
```

### 经典实战示例与社区大片

- **示例 1：卧室大床场景 + 白 T 恤男模特** → 指定男模自然斜倚在蓬松床头，神态放松，光影与卧室晨光无缝融合。
- **示例 2：庭院摇椅场景 + 优雅白衬衫男模特** → 指定男模安坐于摇椅之上，手捧书卷，阳光透过绿植斑驳洒在肩头。

#### 示例 3：参考人物便利店生活流对比选品 (Candid Convenience Store Shopping)
- **作者**：[@mehvishs25](https://x.com/mehvishs25)
- **提示词原文**：
  ```text
  Photorealistic candid lifestyle photograph of the same woman as the reference image, preserving her exact facial identity, facial proportions, skin tone, and recognizable features. She is casually shopping inside a modern convenience store, captured in an authentic everyday moment rather than a posed photoshoot.

  Medium-full body side-angle composition. She stands in a brightly illuminated aisle, comparing two beauty or wellness products while reading packaging details with a focused expression. One hand holds a sleek bottle close to her face while the other carries a second product she is considering.

  Her dark hair is styled in a relaxed high bun with a few loose strands framing her face. Slim gold hoop earrings, subtle glossy lips, natural makeup, and oversized black sunglasses resting on her head.

  Outfit: a bold, fitted black off-shoulder ribbed top paired with a charcoal gray mini skort and sheer black tights, creating a chic city-girl aesthetic. She carries a large luxury-inspired monogram shoulder bag and wears black ankle boots.

  Modern convenience store environment in Southeast Asia with narrow aisles, brightly stocked shelves filled with colorful skincare, beverages, snacks, and household essentials. Fluorescent ceiling panels cast soft, diffused light across the scene.

  Natural candid body language, realistic posture, genuine shopping behavior, authentic retail atmosphere, unposed documentary aesthetic. Soft depth of field with subtle background blur while keeping the subject sharply detailed.

  Shot with a 35mm lens at eye level, ultra-realistic RAW photography quality, realistic skin texture, accurate fabric details, natural colors, soft shadows, crisp focus, 4K detail.

  Vertical 4:5 composition, subject positioned slightly left of center, facing the shelves on the right side of the frame, immersive everyday shopping scene, contemporary urban lifestyle editorial feel without looking staged.
  ```
- **核心要点**：
  - **身份绝对一致（Exact Facial Identity）**：保留参考图女性的面部骨骼、肤色与神态。
  - **纪实抓拍感（Unposed Documentary Vibe）**：告别刻板摆拍，还原便利店真实挑货对比场景（一手拿瓶靠近看标签，另一手拿竞品对比）。
  - **35mm 人文视点**：货架商品丰富杂糅但有自然浅景深，日常真实感拉满。

---

## 案例 4：宠物与产品互动 (Pet-Product Interaction)

**适用场景**：宠物食品、咀嚼玩具、跑轮猫爬架、牵引绳、宠物服饰等需要可爱毛孩子亲身互动的真实生活瞬间。

### 提示词模板

```text
生成{宠物}和图中{商品}互动
```

### 关键执行规则
- **动物毛发与动态表现**：生动刻画狗狗扑跃、猫咪扑爪、仓鼠奔跑时的肌肉紧张感与根根分明的毛发丝光。
- **互动合理性**：玩具球需有咬合与追逐动态；跑轮需有四爪飞奔的旋转模糊与重心倾斜。
- **实战示例**：
  - 示例 1：橙色环保橡胶狗咬球 → 活泼可爱的柯基/金毛幼犬在草坪上扑咬球体，眼神机敏兴奋。
  - 示例 2：静音仓鼠跑轮 → 毛茸茸金丝熊仓鼠在透明跑轮内飞速奔跑，动作憨态可掬。
