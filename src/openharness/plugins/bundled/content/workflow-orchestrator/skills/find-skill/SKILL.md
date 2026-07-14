---
name: find-skill-skillhub
description: 在 SkillHub 平台查找/搜索 Skill 技能。基于 skills 列表接口，支持关键词分词搜索、一级标签筛选和组合检索。当用户说“找个 xxx 技能”“有没有处理 PDF 的 skill”“SkillHub 上搜一下 xxx”“按分类看技能”“推荐一个做数据分析的 skill”“这个需求有现成技能吗”，或 workflow-composer 需要发现能力缺口时使用。
---

# 在 SkillHub 查找 Skill

本技能负责发现和推荐 SkillHub 能力。SaaS 场景中，搜索优先使用 `skillhub_search_capabilities`；安装必须走 `skillhub_prepare_install` + `ask_user_question` + `skillhub_install_confirmed`，不得执行 SkillHub CLI、不得执行 `curl | bash`、不得把命令行安装步骤交给用户。

接口参数 / 返回字段 / 更多示例见 [references/api.md](references/api.md)。

## 使用模式

### 独立推荐模式

用户主动要求“找技能”时，输出 3-5 个最匹配候选，并说明匹配理由。不要把原始列表直接丢给用户。

### 编排器内部模式

当 `workflow-composer` 为某个步骤寻找能力时：

- 只返回候选摘要和排序理由。
- 不要求用户在原始技能列表中挑选，除非多个候选难以判断。
- 不展示安装命令。
- 不直接安装；把候选交回 `workflow-composer` 走确认链路。

## 核心流程

关键词分词召回有限，必须走完四步，不要拿用户原话搜一次就结束。

### Step 1 · 理解场景

从用户自然语言中提取：任务意图、领域标签（映射到 `category`）、中英文关键词（同义/上位词扩展，2-4 个）。

例："帮我自动写周报发给老板" -> `office-efficiency`；`周报` / `工作汇报` / `日报` / `weekly report`

### Step 2 · 多次搜索

优先调用 `skillhub_search_capabilities`。如果当前运行时没有该工具，才基于公开接口 `GET https://api.skillhub.cn/api/skills` 搜索；关键词使用 `keyword`，排序优先 `sortBy=score`，不要用 `/api/v1/search`。

### Step 3 · 意图匹配排序

结合 `name`、`description`、`description_zh`、分类、是否需要 API key、下载/安装数据判断契合度。过滤不相关项，挑出最契合的 3-5 个；同档按热度和描述清晰度排序。

命中过多时用 `category` 或 `labels` 收窄；为空时去掉 category、换同义/上位词放宽。

### Step 4 · 输出推荐

独立推荐模式输出：

```text
为你找到 {N} 个相关技能：

1. {name} - {一句话用途}
   匹配理由：{为什么适合这个场景}
   分类：{category 中文名} | 下载：{downloads} | 安装：{installs}
   主页：https://skillhub.cn/skills/{slug}

需要我帮你安装第几个？安装前我会先确认。
```

编排器内部模式输出紧凑候选摘要：

```json
{
  "candidates": [
    {
      "slug": "skill-slug",
      "name": "技能名",
      "fit_reason": "适合当前步骤的原因",
      "requires_confirmation": true
    }
  ]
}
```

## 一级标签（category）

12 个一级标签（`?category=<key>`），映射意图时按需打开对应详情文件（渐进式披露）。完整索引与说明见 [references/categories.md](references/categories.md)：

`office-efficiency` 办公效率 · `content-creation` 内容创作 · `dev-programming` 开发编程 · `data-analysis` 数据分析 · `design-media` 设计多媒体 · `ai-agent` AI Agent · `knowledge-management` 知识管理 · `business-ops` 商业运营 · `education` 教育学习 · `professional` 行业专业 · `it-ops-security` IT 运维与安全 · `life-service` 生活服务
