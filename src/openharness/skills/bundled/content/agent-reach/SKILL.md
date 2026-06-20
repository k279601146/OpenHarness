---
name: agent-reach
description: >
  Agent Reach bundled skill adapter for public-source internet research. MUST
  USE when the user asks for 调研/research/搜索/search/查/找/look up public
  information, shares a public URL, asks to read public articles/docs/RSS,
  compare GitHub projects, summarize public video or podcast material, collect
  public competitor evidence, perform technical evaluation, or fact-check public
  claims. This dev2 adapter follows the upstream Agent Reach skill routing
  model, but only exposes public-source research workflows and never packages
  cookies, login sessions, proxy setup, credential collection, anti-bot bypass,
  or bulk account-content collection.
category: research
aliases:
  - 联网调研
  - 公开资料调研
  - Agent Reach
  - web research
triggers:
  - research: 调研/全网调研/帮我调研/研究一下/research/深入了解
  - search: 搜/查/找/search/搜索/查一下/帮我搜/看看公开资料
  - dev: github/代码/仓库/gh/issue/pr/开源项目/技术选型
  - web: 网页/链接/文章/rss/读一下/打开这个/报告/文档
  - video: youtube/视频/播客/字幕/公开音视频
  - public-community: v2ex/reddit/twitter/x/小红书/b站/linkedin/雪球/公开讨论
metadata:
  upstream:
    name: Agent Reach
    source: D:\Agent-Reach-main\Agent-Reach-main
    homepage: https://github.com/Panniantong/Agent-Reach
  dev2_adapter:
    bundled_skill: true
    executable_runtime_included: false
    high_risk_platform_flows_excluded: true
---

# Agent Reach — dev2 Bundled Skill Adapter

This skill is the dev2 bundled-skill adapter for the upstream Agent Reach project. It keeps Agent Reach's routing idea and reference layout, but dev2 only exposes safe public-source research workflows through the existing OpenHarness skill mechanism.

When this skill is selected by `$agent-reach`, use it as the research planner and evidence organizer for public web material. Do not invent a separate scraping or login workflow.

## Distribution Boundary

Included here:

- Upstream license file.
- Agent Reach skill-compatible root `SKILL.md`.
- Agent Reach-style `references/` route documents for public research categories.
- A sanitized configuration example for user-local optional providers.
- Upstream provenance notes.

Not included here:

- The upstream `agent_reach/` Python runtime package.
- Platform CLI wrappers, automated collectors, tests, or scripts that execute platform collection.
- Real `.env`, API keys, cookies, tokens, private account state, proxy credentials, browser session export, or login-state reuse.

If the user already has Agent Reach installed locally, they may use their own local setup. dev2 must not ask them to paste secrets into chat and must not package those secrets with SaaS or bundled skill files.

## Global Rules

1. Use only public sources, user-provided public URLs, public repositories, public feeds, public reports, public docs, public media pages, or information the user already provided.
2. Do not ask for cookies, session tokens, private API keys, private account exports, browser login state, or proxy credentials.
3. Do not provide instructions for CAPTCHA bypass, anti-bot bypass, fingerprint evasion, rate-limit bypass, or login-wall circumvention.
4. Do not perform bulk harvesting of account pages, comments, followers, private communities, or gated content.
5. If a platform or page requires login, state the limitation and suggest public alternatives.
6. Keep source links with findings. Distinguish facts, interpretations, uncertainty, and unsupported claims.
7. For GitHub tasks, default to public repository metadata, README, releases, issues, PRs, discussions, docs, and public code search.
8. For social/community tasks, only summarize public pages or user-provided public links; avoid account automation or deep collection.

## Route Table

| User intent | Route | Reference |
|---|---|---|
| Web search, semantic search, technical search | `search` | [references/search.md](references/search.md) |
| Public URL, article, docs, report, RSS/feed reading | `web` | [references/web.md](references/web.md) |
| GitHub, repository, issue/PR, code ecosystem research | `dev` | [references/dev.md](references/dev.md) |
| Public video/podcast notes and transcript-based summaries | `video` | [references/video.md](references/video.md) |
| Public community discussion summary | `public-community` | [references/social.md](references/social.md) |
| Hiring, company, role, market, finance public information | `career-finance` | [references/career.md](references/career.md) |

## Workflow

1. Clarify scope when needed: target question, geography, time range, depth, output format, audience, and language.
2. Pick one or more routes from the route table.
3. Gather public evidence using available OpenHarness/browser/search tools or the user's own locally configured Agent Reach, staying inside the Global Rules.
4. Build an evidence table with source, date if available, claim, source quality, and link.
5. Synthesize findings into the requested format: research brief, comparison table, timeline, decision memo, fact-check, learning pack, or presentation outline.
6. Report limitations clearly, especially when sources are stale, unavailable, login-gated, region-limited, or contradictory.

## Output Templates

### Public Research Brief

- Executive summary
- Key findings
- Evidence table with links
- Opposing views or uncertainty
- Risks and missing evidence
- Recommended next questions

### URL Reading

- Source metadata
- Section summary
- Key facts
- Short compliant excerpts only when useful
- Links and references
- Bias/freshness notes

### Technical / GitHub Evaluation

- Project positioning
- Public activity and maintenance signals
- Docs and ecosystem quality
- Integration cost and constraints
- Alternatives
- Recommendation and caveats

### Fact Check

- Claim
- Best available original source
- Supporting evidence
- Conflicting evidence
- Verdict and confidence
- What would change the conclusion

## Examples

- `$agent-reach 请围绕“AI 编程助手商业化趋势”做公开资料调研，输出关键结论、证据链接和不确定点。`
- `$agent-reach 请阅读这些公开 URL，提炼核心观点、关键数据、可引用片段和后续追问问题。`
- `$agent-reach 请比较这三个 GitHub 项目的定位、活跃度、生态、风险和推荐使用场景。`
- `$agent-reach 请对这个说法做公开资料事实核对，并区分事实、推断和争议。`

## Upstream Notes

This adapter is based on the upstream Agent Reach skill layout from `D:\Agent-Reach-main\Agent-Reach-main\agent_reach\skill`. The full upstream project may contain additional platform backends and setup instructions. dev2 intentionally does not package those executable platform collectors or sensitive setup flows as a bundled SaaS feature.
