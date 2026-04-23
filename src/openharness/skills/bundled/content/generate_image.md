---
name: generate_image
description: 使用专业的图片模型进行从零创作、局部编辑或参考图特征融合。
---

# 视觉创作专家 (Image Creation Expert)

使用先进的图片模型根据文本描述进行从零生成、编辑或参考特征创作。

## 使用场景 (When to use)
- 用户要求绘制、设计、创作任何静态视觉内容（插画、UI布局、写实照片等）。
- 需要对已有图片进行局部修改、添删元素或变换风格。
- 需要保持角色一致性，通过参考图生成新场景。

## 核心模型矩阵 (Model Strategy)
根据任务需求选择最合适的模型：
- **Nano Banana 2**: 极速生成，适合快速创意迭代。
- **Nano Banana Pro**: 工作室级 4K 品质，适合复杂的排版、精确的文字渲染和高细节场景。
- **Doubao (Seedream 5.0)**: 极致的写实感与审美，适合要求极高的艺术创作或细腻的人像。

## 1. 任务流 (Workflow)
1. **意图确认**：分析用户是需要“从零生成 (gen_creative_image)”、“编辑 (edit_image)”还是“参考生成 (generate_from_reference)”。
2. **审美对齐 (Aesthetic Retrieval)**：**重要！** 检查用户需求是否匹配任何专业的 [审美技能 (Aesthetic Skill)]。例如：宣传册 (marketing-brochures)、Logo (logo-brand-design)、电商 (ecommerce-product-listing)。
3. **提示词增强**：
   - 若匹配到审美技能：调用 `skill(name='...')` 读取其关键词库、视觉决策树和执行规则。
   - 整合审美规范，将用户的口语描述转化为包含：主体、风格、光影、构图的详细英文 Prompt。
4. **模型分发**：
   - 若用户追求速度 -> 指定 `model='nano-banana-2'`。
   - 若涉及文字或精细布局 -> 指定 `model='nano-banana-pro'`。
   - 若追求极致质感 -> 指定 `model='doubao-seedream-5-0-260128'`。
5. **结果交付**：调用对应工具后，将产物物理路径同步给用户。

## 2. 核心规则 (Rules)
- **审美优先**：优先查阅配套的行业 Prompt 规范（审美技能）以确保产出符合专业水准。
- **提示词规范**：图片提示词必须转化为英文以获得最佳生成效果。
- **路径敏感**：进行编辑或参考生图时，必须确保输入的图片路径是有效的物理磁盘路径。
- **原子性执行**：禁止通过 bash 脚本猜测 API，必须使用专门的媒体工具类。
