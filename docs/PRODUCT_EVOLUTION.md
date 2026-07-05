# OpenHarness 商业级 AI 对话产品演进记录

更新时间：2026-07-04

## 目标

将当前 OpenHarness / ohmo 项目持续演进为对标 ChatGPT、Claude、Gemini、Grok、Manus 等主流 AI 对话与代理产品的成熟商业级应用。演进方式采用“调研 -> 需求提出 -> 实现 -> 复盘 -> 文档同步”的循环。

## 竞品校准

本轮参考的公开官方入口：

- ChatGPT：<https://openai.com/chatgpt/overview/>
- Claude：<https://www.anthropic.com/claude>
- Gemini：<https://gemini.google/overview/>
- Grok：<https://grok.com/>
- Manus：<https://manus.im/>

归纳出的成熟产品共性：

- 首屏直接暴露核心能力：模型、历史、项目/任务、文件/图片、语音、搜索、工具执行。
- 用户信任能力前置：账号状态、权限确认、隐私/数据控制、导出、用量/额度提示。
- 长任务可观察：流式输出、工具状态、并行代理、可恢复历史、失败恢复。
- 商业化承载：订阅/套餐、用量边界、账号/组织、合规与隐私入口、多语言体验。
- 设计一致性：明确的主题/token、深浅色模式、稳定命令体系、低学习成本的 onboarding。

## 当前项目状态

已有优势：

- Python 后端具备 provider/profile、Claude/Codex/Gemini 等多后端接入、外部订阅授权、MCP、工具、任务、swarm/agents、session resume、export/share、privacy/settings 等基础能力。
- React Ink 终端前端已有流式对话、命令选择器、状态栏、权限/选择弹窗、图片剪贴板入口、voice/vim/theme/output-style 等交互。
- 测试覆盖面较广，包含命令、UI、工具、auth、session、gateway、autopilot 等模块。

主要差距：

- 商业级首屏能力发现不足：成熟能力散落在 slash commands 中，首次用户不容易理解“我现在能做什么”。
- 缺少产品演进台账：需求、竞品差距、阶段结果、下一步计划没有固定文档承接。
- 订阅/计费 UI、组织/账号 UI、i18n、合规说明、移动/桌面平台适配仍处于早期或缺失状态。
- 当前 `frontend/terminal/node_modules` 本地安装不完整，完整 TypeScript 验证受阻，需要修复依赖环境。

## 本阶段已完成

阶段：P0 - 首次体验与产品台账

- 新增本文档，建立长期产品演进记录。
- 重写 React TUI 欢迎区为 `Product cockpit`：
  - 使用稳定 ASCII 品牌展示，替换原先编码损坏的 logo。
  - 展示当前 provider/model/auth/permission mode 摘要。
  - 将关键成熟能力分组前置：Start、Trust、Workflows。
  - 入口覆盖 onboarding、history/resume、account/provider、model、privacy、permissions、usage、export、images、voice、skills、agents。
  - 根据后端命令清单自动过滤不可用 slash actions，同时保留前端本地快捷入口 `Ctrl+V`。
- 为欢迎区 helper 增加测试，覆盖命令过滤和状态摘要格式化。

涉及文件：

- `frontend/terminal/src/components/WelcomeBanner.tsx`
- `frontend/terminal/src/components/WelcomeBanner.test.ts`
- `frontend/terminal/src/components/ConversationView.tsx`
- `frontend/terminal/src/App.tsx`
- `docs/PRODUCT_EVOLUTION.md`

## 当前验证状态

- 已通过：`git diff --check -- frontend/terminal/src/components/WelcomeBanner.tsx frontend/terminal/src/components/WelcomeBanner.test.ts frontend/terminal/src/components/ConversationView.tsx frontend/terminal/src/App.tsx docs/PRODUCT_EVOLUTION.md`
- 已通过：使用 TypeScript `transpileModule` 对本阶段 TS/TSX 文件做语法级校验：
  - `src/App.tsx`
  - `src/components/ConversationView.tsx`
  - `src/components/WelcomeBanner.tsx`
  - `src/components/WelcomeBanner.test.ts`
- 受阻：完整 `tsc --noEmit` 依赖本地 `@types/node` / `@types/react` 内容，但当前 `node_modules` 中这些包目录缺少 package 内容。
- 受阻：`node --import tsx --test src\components\WelcomeBanner.test.ts` 未能执行到断言；当前 `node_modules` 中 `tsx`、`react`、`ink`、`@types/node`、`@types/react` 的 package 内容均缺失。此前 `npm install --ignore-scripts` 遇到 Windows `EPERM`，无法清理 `node_modules/ansi-escapes`。

## 下一阶段计划

P1 - 商业成熟度入口：

- 增加 TUI 内的 usage/subscription readiness 面板：展示 token、provider、auth、profile、可选模型、额度/速率限制建议。
- 将 `/privacy-settings`、`/usage`、`/provider` 的关键结果转为更结构化的前端状态，而不只作为文本输出。
- 规划订阅/计费 UI 的本地 mock 层，先明确套餐、额度、超限、组织账号等信息架构。

P2 - i18n 与 onboarding：

- 抽取终端前端固定文案，建立 `en` / `zh-CN` 字典。
- 将 onboarding 拆为可恢复 checklist，覆盖 provider、model、privacy、permissions、history、multimodal、agents。

P3 - 历史/项目化体验：

- 将 session resume 升级为项目/会话列表视图，支持标签、搜索、最近任务、导出/分享状态。
- 对标 ChatGPT Projects / Claude Projects 的项目上下文入口，沉淀 workspace-level memory 与隐私边界。

## 遗留问题

- 修复 `frontend/terminal/node_modules` 的 Windows 权限/锁定问题后，恢复完整 TypeScript 与 React TUI 测试。
- 需要后续明确商业套餐与真实计费后端边界：当前只能做 readiness/mock UI，不能声称已有真实订阅能力。
- 多语言、A11y、平台适配仍需系统性拆分任务并逐步落地。
