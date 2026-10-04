---
name: novel-characters
description: |
  从小说或短故事里拆出角色表、人物画像、形象提示词、音色提示词，
  其中形象提示词含一张角色设定图的完整版面指令（左半身像 + 右全身三视图 + 细节条），
  产出 JSON + Markdown + 可交互的 report.html。
  报告语言可指定（--lang），默认中文，任意语言都支持；零依赖、零 API key、不出图。
  Use when asked to 拆小说角色、分析人物、生成角色卡、character sheets from a novel。
allowed-tools:
  - Read
  - Write
  - Bash
  - Task
  - Glob
metadata:
  version: 2.0.0
  triggers:
    - novel-characters
    - 拆角色
    - 拆书角色
    - 小说角色
    - 人物画像
    - 角色卡
    - 三视图
    - character sheet from novel
  license: Apache-2.0
  requires:
    bins:
      - node          # >= 18，只用标准库，无 npm 依赖
  runtimes:
    - claude-code
    - codex
---

## novel-characters

输入一篇小说/短故事，输出每个角色的：人物画像、形象提示词、音色提示词、角色设定图的版面指令。

**本 skill 不出图，只产提示词。**出图是下游的事——它要选模型、选画风、选画幅，那三件事在这里一个都答不了。

`{baseDir}` = 本文件所在目录。脚本 `{baseDir}/scripts/novel-characters.mjs`，零依赖，`node` 直接跑。

**运行环境**：Claude Code 和 codex 都能跑，没有差别——这条管线全是 node 脚本加模型读写，不碰任何本机可执行文件。

---

### Step 0 — 确定报告语言

用户可以指定语言，比如「用英文」「--lang en」「日本語で」。**没说就是中文（`zh`）。**

这个 `lang` 会一路传下去：第二趟生成角色卡时决定人类可读字段用什么语言，`validate` 和 `render` 也都要带上。

**界面文案分两种情况：**

- `zh` / `en` / `ja` —— 内置，不用管
- **其他任何语言** —— 你要现场翻一份。跑

  ```bash
  node {baseDir}/scripts/novel-characters.mjs ui-template <lang>
  ```

  它打印一份英文骨架，把每个值翻译成目标语言，整块放进 `cast.json` 顶层的 `ui` 字段。渲染时会合并进内置表。

  **不给 `ui` 的话 `validate` 会直接报错**——否则报告会是「角色内容是法语、界面标签是英文」的半吊子状态。

支持的语言不受内置表限制，法语韩语西班牙语都能出完整报告。

### Step 0.5 — 画风与渲染契约（继承上游）

在短剧流水线中，出图画风可继承自上游 `outline.json`（或项目输入配置）中的 `params.stylePreset`。平台支持标准化风格库注册模板及显式 `custom` 自定义风格。
当前画风的渲染元数据若已在输入配置（`config.stylePresetMeta`）中提供，可直接参考取用。
版面规则（16:9 三区、比例、细节让位）**不随风格变**，变的只有渲染质感。

### Step 1 — 定位输入与骨架生成

**有 outline.json 时优先**：使用 `seed` 或 `scaffold` 生成预填骨架：
```bash
node {baseDir}/scripts/novel-characters.mjs seed <outline.json> > cast.json
```
或使用腳手架：
```bash
node {baseDir}/scripts/novel-characters.mjs scaffold <outline.json> [--lang zh] [--style <style>] > cast.json
```

**长文本小说直接抽取模式**：
用户给文件路径就直接用。直接粘正文的，**先落到一个临时 .txt**——后面校验「引文是否逐字」要拿原文比对，没有原文文件这步就没法做。

确定输出目录：用户指定就用；没指定就用原书同级目录。

### Step 2 — 分块（仅长文本模式）

```bash
node {baseDir}/scripts/novel-characters.mjs chunk <book.txt> <workdir>
```

打印 `{"chunks": N, ...}`。

- **N == 1**：跳过 Step 3，直接在当前会话读原文做第一趟，结果自己写成 `<workdir>/roster-00.json`
- **N > 1**：进 Step 3
- `truncated: true`：明确告诉用户尾部没扫到，别闷着

### Step 3 — 第一趟扫描（仅 N > 1）

**当前环境支持子代理就并发**（Claude Code 的 Task、codex 的 subagent）：每块一个子代理，**所有调用放在同一条消息里**才是真并发。不支持就一块一块串行读，结果一样，只是慢。

每个子代理的任务：
1. 读 `{baseDir}/references/roster-pass.md`，照它执行
2. 读 `<workdir>/chunk-NN.txt`
3. 把 roster JSON 写到 `<workdir>/roster-NN.json`
4. 只回一句「done NN，抽到 X 个角色」

### Step 4 — 归并 + 复核

```bash
node {baseDir}/scripts/novel-characters.mjs merge <workdir> | tee <workdir>/merged.json
```

落到 `merged.json` 不只是留档：Step 6 的 assemble 靠它拿同档角色的戏份顺序。

按名字+别名精确收敛（某块把「陆」列成「陆行远」的别名，两条就并成一个人），notes 累加、quotes 去重，按出现块数降序——出现的块越多戏份越重。

输出是 `{ "characters": [...], "mergeCandidates": [...] }`。**`mergeCandidates` 要逐条复核**：精确匹配只能收敛两块恰好写了相同称呼的情况，剩下的是语义判断，脚本做不了。候选来自名字包含关系（`「陆」⊂「陆行远」`）——是强信号不是判决，同姓的父子、兄弟就不能合。候选之外你自己看出来的同人（「陆先生」和「行远」没有包含关系，不会进候选）也要合。

要合并就写一份 merges.json 再落地：

```json
{ "merges": [{ "keep": "陆行远", "absorb": ["陆", "陆先生"] }] }
```

```bash
node {baseDir}/scripts/novel-characters.mjs merge <workdir> --apply merges.json | tee <workdir>/merged.json
```

`keep`/`absorb` 用名字或任一别名定位都行，找不到会直接报错。输出仍带 `mergeCandidates`，剩下的都确认是不同的人（或清空）再进下一步。没有要合的就直接往下走——但 `merged.json` 必须留着。

### Step 5 — 选角

取前 N 位。默认 30，用户说了就听用户的。剩下的角色在最后汇报里提一句「还识别出 X 位没做画像」。

### Step 6 — 第二趟出卡

每个角色一份，同样能并发就并发。

每份任务拿到：
- `{baseDir}/references/profile-pass.md` 和 `{baseDir}/references/schema.md`（读它们，照着做）
- **报告语言 `lang`**（Step 0 定的）
- 该角色归并后的 `name` / `aliases` / `notes` / `quotes`
- **同批其他角色的名字**（避免长相声线撞车）

按 `profile-pass.md` 完成身份—外观语义自检后再交卡：人物档案、形象提示词、本地译文与设定图主体不能各说一种身份。大纲决定名单和改编取舍，原文观察补足外形依据；不要只给大纲而跳过 Step 2–4 的原文扫描。

角色卡 JSON 写到 `<workdir>/card-<slug>.json`。**断点续跑**：`card-<slug>.json` 已存在的角色不必重跑。

**同时写一段故事摘要**：用 `lang` 指定的语言，3–5 句，交代时空背景、核心情境、这几个人聚在一起的由头。短篇直接从原文写；长篇从各块的 roster note 归纳。不剧透结局，不写成推荐语。写到 `<workdir>/summary.txt`。非内置语言的话，把 Step 0 翻好的 ui 整块存成 `<workdir>/ui.json`。

然后合成 cast.json——**用 assemble，不要手拼**（手拼会丢字段、写错顶层键）：

```bash
node {baseDir}/scripts/novel-characters.mjs assemble <workdir> \
  --source <书名> --lang <lang> \
  --out <输出目录>/<书名>-cast.json
```

坏卡会被逐个点名——哪份 `card-*.json` 坏了就只重跑那个角色，其他不用动。

同档角色的先后是戏份顺序，来自 Step 4 留下的 `<workdir>/merged.json`（assemble 自动读，也可用 `--order` 指别的文件）。报告左栏「按戏份排序」的序号就靠它——看到「同档角色将按文件名序」的警告说明 merged.json 丢了，回 Step 4 重新生成。

### Step 7 — 校验 ⛔ 不能跳

```bash
node {baseDir}/scripts/novel-characters.mjs validate <cast.json> <book.txt>
```

记得带上 `--lang`（Step 0 定的）。检查：结构、`importance` 枚举、**引文逐字**、**出图提示词不含人名**、**语言分工**（人类字段跟随 `lang`、出图/TTS 提示词永远英文）、以及**非内置语言必须带 `ui`**。

**有违规就按报错逐条修，改完重跑，直到通过。** 这四类错模型真的会犯——这套检查就是被真实输出打出来的。

### Step 8 — 输出

```bash
cd <输出目录>
node {baseDir}/scripts/novel-characters.mjs render <cast.json> --md   > <书名>-cast.md
node {baseDir}/scripts/novel-characters.mjs render <cast.json> --html > report.html
```

语言取 `cast.json` 里的 `lang`，要临时覆盖就加 `--lang <code>`。

`render` 默认去 cast.json 同级的 `images/<slug>-sheet.png` 找图；图在别处就用 `--images <目录>`
指过去（任意路径）。**本 skill 不产生这些文件**——下游出完图，重跑一次 render 就能把图嵌进报告。

report.html 的样式约定见 `{baseDir}/references/report-style.md`——要改样式先读它，别把它改回通用卡片墙。

### Step 10 — 输出与交付边界

**在 SaaS 自动化流水线下**：
Agent 的交付物理边界收敛为唯一核心产物 **`cast.json`**。一旦 `node novel-characters.mjs validate` 校验通过，**立刻结束轮次并交付**。
严禁在沙盒会话中执行 `selftest.mjs`、`render` 或出图操作。HTML 报告渲染由 SaaS 后台服务统一提供。

**在本地 CLI 完整跑批场景下（可选）**：
```
<输出目录>/
├── <书名>-cast.json
├── <书名>-cast.md
├── report.html                    ← 双击就能开
└── images/                        ← 本 skill 不写这个目录
    └── <slug>-sheet.png           ← 下游出完图放这儿，render 会捡起来
```

### Step 9 — 汇报

一句话说清：角色数、报告路径。校验一次没过的话，说明修了什么。原文被截断要明确说清楚。

**不要说「已出图」或「已生成设定图」**——这一步不存在了，交付的是提示词。

---

## 边界与约束

- **SaaS 自动化运行约束**：禁止读取 `schema.md`、`profile-pass.md` 或运行 `selftest.mjs`，所有 schema 与画风渲染参数已在系统提示词和输入配置中结构化下发
- 单次上限 24 块（净覆盖约 93 万字符），超了会明确报 `truncated`，不静默截断
- 人类可读字段跟随 `--lang`（默认中文）；出图和 TTS 提示词**永远英文**，那些引擎吃英文最稳
- **本 skill 不出图。**`image.sheet` 是给下游的版面指令，版面最容易崩的几处（一张图两个长相、为了塞细节把人物压扁、左栏收口）靠提示词里写死的几句压住，见 `references/sheet.md`
- 想要能实时编辑、边跑边看的交互界面，那是另一个东西，不在这个 skill 里

## 本地开发自测（仅限本地代码开发，Agent 线上运行严禁调用）

```bash
node {baseDir}/scripts/selftest.mjs
```

974 项断言，不调模型、不花额度，覆盖分块 / 归并 / 合成 / 多语言 / 校验 / 渲染的全部确定性逻辑。改完脚本先跑这个。

