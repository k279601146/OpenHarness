#!/usr/bin/env python3
"""Install selected repository skills without overwriting existing copies."""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = {
    "vane-portrait-gif-stickers": {
        "description": "照片转动态表情包",
        "source": ROOT,
        "items": ("SKILL.md", "agents", "references", "scripts"),
    },
    "vane-cinematic-poster": {
        "description": "电影级海报设计",
        "source": ROOT / "skills" / "vane-cinematic-poster",
        "items": ("SKILL.md", "agents", "references", "assets"),
    },
    "vane-book-cinema": {
        "description": "书页里的电影",
        "source": ROOT / "skills" / "vane-book-cinema",
        "items": ("SKILL.md", "agents", "assets"),
    },
    "wechat-red-packet-cover": {
        "description": "微信红包封面制作",
        "source": ROOT / "skills" / "wechat-red-packet-cover",
        "items": ("SKILL.md", "README.md", "LICENSE", "references", "scripts", "assets"),
    },
    "vane-pet-new-year-portrait": {
        "description": "宠物新年写真",
        "source": ROOT / "skills" / "vane-pet-new-year-portrait",
        "items": ("SKILL.md", "scripts", "evals", "assets"),
    },
    "vane-xhs-design": {
        "description": "Vane 小红书图文设计",
        "source": ROOT / "skills" / "vane-xhs-design",
        "items": ("SKILL.md", "styles"),
    },
}


def install(names, destination):
    # Check the whole request first: --all must not partially overwrite a copy.
    for name in names:
        target = destination / name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"已存在：{target}。请备份后移走，或只选择尚未安装的 Skill。")
        skill = SKILLS[name]
        for item in skill["items"]:
            source = skill["source"] / item
            if not source.exists():
                raise FileNotFoundError(f"Skill 文件不完整：{source}")

    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        skill = SKILLS[name]
        target = destination / name
        target.mkdir()
        try:
            for item in skill["items"]:
                source = skill["source"] / item
                if source.is_dir():
                    shutil.copytree(source, target / item)
                else:
                    shutil.copy2(source, target / item)
        except Exception:
            shutil.rmtree(target)
            raise
        print(f"已安装 {name} → {target}")
    print("请开始新的 Codex 对话，再使用对应的 $Skill 名称。")


def main():
    parser = argparse.ArgumentParser(description="安装 Vane GPT Image Skills")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出可安装的 Skill")
    group.add_argument("--all", action="store_true", help="安装所有 Skill")
    group.add_argument("--skill", action="append", choices=SKILLS, help="安装指定 Skill；可重复使用")
    parser.add_argument("--destination", type=Path, default=Path.home() / ".codex" / "skills", help="Skill 安装目录")
    args = parser.parse_args()

    if args.list:
        for name, skill in SKILLS.items():
            print(f"{name}  —  {skill['description']}")
        return 0

    names = list(SKILLS) if args.all else list(dict.fromkeys(args.skill))
    try:
        install(names, args.destination.expanduser())
    except (OSError, shutil.Error) as error:
        print(f"安装未完成：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
