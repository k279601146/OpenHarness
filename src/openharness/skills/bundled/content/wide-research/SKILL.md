---
name: wide-research
description: >
  Wide Research bundled skill for batch, parallel public-source research across
  multiple explicit targets. Use when the user asks for Wide Research, 宽度调研,
  批量调研, 多对象调研, 横向调研, parallel research, Manus Wide Research style
  research, or asks to compare/research a list of companies, products, papers,
  URLs, tools, markets, rules, competitors, or other similar objects with a
  structured table and evidence links. This skill is an entry signal for the
  SaaS Wide Research coordinator/worker protocol, not a normal single-agent
  research workflow.
category: research
aliases:
  - Wide Research
  - 宽度调研
  - 批量调研
  - 多对象调研
  - 横向调研
  - parallel research
  - Manus Wide Research
triggers:
  - Wide Research
  - 宽度调研
  - 批量调研
  - 多对象调研
  - parallel research
  - manus wide research
---

# Wide Research

This skill declares a Wide Research request. In dev2 SaaS, Wide Research must be executed by the dedicated coordinator/worker run system, not by a normal single-agent skill workflow.

## Routing Contract

- If the user selected `$wide-research` or this skill, route the request to the SaaS Wide Research API.
- Do not solve the request by loading this skill and manually doing ordinary web research in the current agent turn.
- Do not load Agent Reach as a fallback for single-target requests.
- Require at least two explicit targets such as companies, products, papers, URLs, tools, competitors, regions, rules, or other comparable objects.
- If fewer than two clear targets are present, ask the user to provide the target list, research scope, and desired table fields.

## Execution Model

- A central coordinator plans the field schema, splits targets, dispatches isolated researcher workers, normalizes worker outputs, and synthesizes the final report.
- Researcher workers receive only their assigned target, shared output schema, evidence requirements, and JSON output contract.
- Researcher workers do not read sibling worker results, communicate with each other, or share intermediate context.
- Only the coordinator reads all worker outputs and writes the final table, evidence index, limitations, failed items, Markdown report, and CSV artifact.

## Safety Boundary

- Use only public sources, public URLs, public repositories, public reports, public docs, public media pages, or information the user provided.
- Do not request cookies, session tokens, private API keys, private account exports, browser login state, or proxy credentials.
- Do not provide CAPTCHA bypass, anti-bot bypass, fingerprint evasion, rate-limit bypass, or login-wall circumvention.
- Do not bulk harvest private communities, gated content, followers, account pages, or logged-in comments.

## Expected Output

- Structured `columns + rows` table.
- Evidence links with source title, URL, claim, date when available, and quality.
- Limitations and uncertainty.
- Failed items and retry suggestions.
- Markdown and CSV artifacts.

## Examples

- `$wide-research 请并行调研以下 20 个竞品。输出字段：产品定位、核心功能、定价线索、近期变化、证据链接、风险。竞品列表：...`
- `$wide-research 对这些论文做横向分析。输出字段：研究问题、方法、数据集、关键结论、局限、引用链接。论文列表：...`
- `$wide-research 批量研究这些城市的 AI 医疗监管政策。输出字段：适用地区、关键要求、影响范围、时间线、公开来源、不确定点。对象列表：...`
