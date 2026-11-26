# 🔄 更新 Vane 生图 Skill 合集

[← 返回 Skill 合集首页](../README.md) · [首次安装教程](installation.md)

GitHub 仓库是合集的来源；安装到 Codex 的 Skill 是电脑上的另一份副本。**更新 GitHub 仓库，不会自动更新已安装的副本。** 本教程把这两步连起来，适用于安装到 Codex 默认目录的用户。

## 最简单的方法：直接告诉 Codex

复制下面的话，发给 Codex：

> 请帮我更新 Vane 生图 Skill 合集：https://github.com/VaneAi888/vane-gpt-image-skills 。先找到我之前克隆的仓库并更新；如果没有，请先克隆。运行仓库的统一更新脚本，安装新增 Skill，更新已识别的旧版并保留备份。遇到来源无法确认的同名 Skill，先不要覆盖，并告诉我处理结果。

Codex 会根据你电脑上的实际目录操作。更新完成后，开启一个新的 Codex 对话使用 Skill。

## 自己在终端更新

### 已经克隆过合集，但第一次使用更新功能

进入你之前克隆的 `vane-gpt-image-skills` 文件夹，运行：

```bash
git pull --ff-only
python3 scripts/update_skills.py
```

第一行先下载更新脚本；第二行会同步已安装的 Skill。**只运行 `git pull` 不会更新 Codex 里的副本。** 如果你还没克隆过合集，请先按[安装教程](installation.md)克隆，再运行第二行。

### 以后更新

进入同一个合集文件夹，只需运行：

```bash
python3 scripts/update_skills.py
```

脚本会先用 Git 获取最新合集，再用最新的脚本和 Skill 列表继续同步。需要 Git、Python 3 和网络；若合集文件夹有未提交或未跟踪的改动，脚本会停止，请先备份并处理这些改动。

## 更新时会发生什么？

- **新 Skill**：自动安装合集里尚未安装的 Skill。即使你以前只安装了其中几个，本次也会安装其余缺少的 Skill。
- **已识别的旧版**：检查到合集版本变化时，先备份整个原目录，再安装新版；脚本会输出每个备份位置。
- **没有新版**：保留原目录，包括你自己的修改，不重复覆盖。
- **无法确认来源的同名 Skill**：保留并跳过。旧版安装器没有来源记录；脚本会尝试根据已安装的 `SKILL.md` 与本地 Git 历史识别旧版。如果文件被修改或历史不完整，可能无法确认。
- **其他 Skill**：不在本合集列表中的目录不会修改；从合集移除的 Skill 也不会自动从你的电脑删除。

默认备份位于 `~/.codex/vane-gpt-image-skills-backups/`。如果想恢复某一份备份，可以把脚本输出的备份路径交给 Codex，要求它帮你恢复；恢复前请先保留当前版本。

### 出现「无法确认来源」怎么办？

先检查提示的同名目录，确认它属于本合集、并且愿意用本合集版本替换后，可以在仓库文件夹中运行：

```bash
python3 scripts/update_skills.py --adopt Skill名称
```

把 `Skill名称` 换成提示中的准确名称，例如 `vane-cinematic-poster`。这会先备份该目录，再安装本合集版本。不要对来源不明或想继续保留原样的 Skill 使用这个选项。

如需只同步当前仓库内容而不联网，可运行 `python3 scripts/update_skills.py --local`；此模式不会检查 GitHub 是否有更新。
