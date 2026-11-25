# 🚀 统一安装入口

[← 返回 Skill 合集首页](../README.md)

本合集目前有六个 Skill，可以任选一个，也可以一起安装。下面的命令适用于有 Python 3、Git 和 Codex 的 macOS / Linux 环境。

| Skill | 用途 | 调用名称 |
| --- | --- | --- |
| 照片转动态表情包 | 使用照片或角色制作多画风 GIF 表情包 | `$vane-portrait-gif-stickers` |
| 电影级海报设计 | 选择 36 种构图，制作中文或英文电影海报方案或图片 | `$vane-cinematic-poster` |
| 书页里的电影 | 根据书籍内容制作电影感海报 | `$vane-book-cinema` |
| 微信红包封面制作 | 设计红包封面、查看模拟效果并导出 | `$wechat-red-packet-cover` |
| 宠物新年写真 | 根据宠物照片制作新年写真，可先查看九宫格预览 | `$vane-pet-new-year-portrait` |
| Vane 小红书图文设计 | 按可选风格制作小红书封面与正文图 | `$vane-xhs-design` |

## 1. 获取合集

在终端运行：

```bash
git clone https://github.com/VaneAi888/vane-gpt-image-skills.git
cd vane-gpt-image-skills
```

如果当前目录已经有 `vane-gpt-image-skills` 文件夹，请进入现有仓库并在确认本地更改后更新；也可以在另一个目录重新克隆。

**以前安装过？** 请查看[统一更新教程](updating.md)，了解如何安装新增的 Skill、备份并更新旧版。

## 2. 选择要安装的 Skill

先查看可选项：

```bash
python3 scripts/install_skills.py --list
```

安装全部：

```bash
python3 scripts/install_skills.py --all
```

或者只安装其中一个：

```bash
python3 scripts/install_skills.py --skill vane-portrait-gif-stickers
```

```bash
python3 scripts/install_skills.py --skill vane-cinematic-poster
```

```bash
python3 scripts/install_skills.py --skill vane-book-cinema
```

```bash
python3 scripts/install_skills.py --skill wechat-red-packet-cover
```

```bash
python3 scripts/install_skills.py --skill vane-pet-new-year-portrait
```

```bash
python3 scripts/install_skills.py --skill vane-xhs-design
```

默认安装到 `~/.codex/skills/`。安装器会复制每个 Skill 需要的指令和参考素材，不会自动安装 Pillow 或 FFmpeg 等依赖。

**已有同名 Skill 时，安装器会停止，不会覆盖原文件。** 如果只想新增另一个 Skill，请使用对应的单独安装命令；如果需要替换已有版本，请先备份并移走原目录，再运行安装命令。`--all` 会在开始复制前检查全部目标，任意一个已存在时不会安装其他 Skill。

## 3. 开始使用

开始新的 Codex 对话，上传照片、角色图或文章内容，再输入对应的调用名称。建议先查看少量样稿，确认方向后再制作完整内容。

- [动态表情包示例与使用教程](portrait-gif-stickers.md)
- [电影级海报示例与使用教程](vane-cinematic-poster.md)
- [书页里的电影示例与使用教程](vane-book-cinema.md)
- [微信红包封面示例与使用教程](wechat-red-packet-cover.md)
- [宠物新年写真示例与使用教程](vane-pet-new-year-portrait.md)
- [小红书图文设计示例与使用教程](vane-xhs-design.md)
- [效果测试记录](testing.md)
- [统一更新教程](updating.md)

使用时需要支持读取参考图和图像生成的环境。动态 GIF 的制作可能还需要 Pillow、FFmpeg 或其他可用工具；实际能力、文字准确性和动作流畅度请以当前环境及生成结果为准。
