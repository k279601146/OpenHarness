# API 参考

**API Base**：`https://api.skillhub.cn`，无需鉴权。查找统一走 `GET /api/skills`（关键词为**分词搜索**）；**不要**用 `/api/v1/search`。

## GET /api/skills（搜索 / 列表）

| 参数 | 说明 | 默认 |
|------|------|------|
| `keyword` | 关键词，**分词搜索**（标题/描述等命中即返回） | - |
| `category` | 一级标签 key（见 categories.md） | - |
| `source` | 来源（`community`/`enterprise`/`official`/`clawhub`） | - |
| `labels` | 属性标签过滤，`key:value` 逗号分隔，否定用 `key:!value` | - |
| `sortBy` | `updated_at`/`downloads`/`stars`/`installs`/`score` | `updated_at` |
| `order` | `asc`/`desc` | `desc` |
| `page` / `pageSize` | 分页（pageSize 1~100） | `1` / `20` |

- 找技能建议 `sortBy=score`（带 `keyword` 时启用智能打分，SkillHub 自有来源优先）；纯浏览分类用 `sortBy=downloads` 看热度。
- `labels` 常见 key：`requires_api_key`（是否需要 API Key）、`pricing_type`（`free`/`paid`）。

返回：`{"code":0,"message":"success","data":{"total":<n>,"skills":[ {...} ]}}`。每项关键字段：
`slug`、`name`、`description`/`description_zh`、`category`、`subCategories`（二级，仅展示）、`tags`、`labels`、`downloads`/`stars`/`installs`、`ownerName`、`homepage`、`version`、`source`。

### 示例

```bash
# 关键词分词搜索 + 智能排序，取前 5
curl -s "https://api.skillhub.cn/api/skills?keyword=周报&sortBy=score&pageSize=5"

# 一级标签浏览：办公效率，按下载量排序
curl -s "https://api.skillhub.cn/api/skills?category=office-efficiency&sortBy=downloads&pageSize=10"

# 分类内关键词检索
curl -s "https://api.skillhub.cn/api/skills?category=data-analysis&keyword=excel&sortBy=score&pageSize=5"

# 只看免费、不需要 API Key 的开发编程类
curl -s "https://api.skillhub.cn/api/skills?category=dev-programming&labels=pricing_type:free,requires_api_key:false&sortBy=downloads"

# 多候选词循环搜索，提取关键字段
for kw in 周报 工作汇报 "weekly report"; do
  curl -s "https://api.skillhub.cn/api/skills?keyword=${kw}&category=office-efficiency&sortBy=score&pageSize=5" \
    | jq '.data.skills[] | {name, slug, downloads, installs, category, desc: .description_zh}'
done
```

> 主页 URL 由 slug 拼接：`https://skillhub.cn/skills/<slug>`。

## 其他接口

```bash
# 单个 Skill 详情
curl -s "https://api.skillhub.cn/api/v1/skills/<slug>"

# 一级标签 / 二级类目实时列表
curl -s "https://api.skillhub.cn/api/v1/categories"
curl -s "https://api.skillhub.cn/api/v1/subcategories?parent=<一级key>"
```

技能主页统一用 `https://skillhub.cn/skills/<slug>`（如 `https://skillhub.cn/skills/wxa-skills-validate`）。不要用接口返回的 `homepage` 字段（那是 `api.skillhub.cn/<owner>/<slug>` 格式）。

## 安装边界

在 Bahew 中不得使用 SkillHub CLI、不得执行 `curl | bash`、不得写入开发机全局目录。安装必须由 `workflow-composer` 走平台工具链：

1. `skillhub_prepare_install` 生成安装摘要和 `confirmation_id`。
2. `ask_user_question` 向用户确认安装。
3. `skillhub_install_confirmed` 调用 SaaS marketplace 安全链路完成下载、Zip 校验、插件识别、权限确认和用户私有目录写入。

普通技能安装到当前用户私有技能目录；插件型扩展安装到当前用户私有插件目录。安装完成后，当前任务可继续通过 `skill` 工具加载新能力。
