#!/usr/bin/env python3
"""Safely sync installed Vane skills with the latest collection checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from install_skills import ROOT, SKILLS


def git(*args, check=True):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=check
    )


def refresh_checkout():
    if git("status", "--porcelain").stdout.strip():
        raise RuntimeError("合集文件夹有未提交或未跟踪的改动；请先备份并处理，再运行更新。")
    before = git("rev-parse", "HEAD").stdout.strip()
    result = git("pull", "--ff-only", check=False)
    if result.returncode:
        raise RuntimeError("无法更新合集，请检查网络、分支或远程仓库：\n" + result.stderr.strip())
    after = git("rev-parse", "HEAD").stdout.strip()
    print("合集仓库：" + ("已更新" if after != before else "已是最新"), flush=True)
    if before != after:
        # Run the freshly downloaded updater and installer definitions, not stale code.
        os.execv(sys.executable, [sys.executable, str(ROOT / "scripts/update_skills.py"), "--local", *sys.argv[1:]])


def digest_directory(path):
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        rel = item.relative_to(path).as_posix()
        if "__pycache__" in item.parts or item.name == ".DS_Store" or item.suffix == ".pyc":
            continue
        if item.is_symlink():
            value = ("link:" + os.readlink(item)).encode()
        elif item.is_file():
            value = hashlib.sha256(item.read_bytes()).digest()
        else:
            continue
        digest.update(rel.encode("utf-8") + b"\0" + value + b"\0")
    return digest.hexdigest()


def make_stage(skill, dest):
    stage = Path(tempfile.mkdtemp(prefix=".vane-stage-", dir=dest))
    try:
        for item in skill["items"]:
            source = skill["source"] / item
            if source.is_dir():
                shutil.copytree(source, stage / item, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
            else:
                shutil.copy2(source, stage / item)
    except Exception:
        shutil.rmtree(stage)
        raise
    return stage


def looks_like_previous_install(name, target):
    """Recognize an unmodified SKILL.md from this checkout's Git history."""
    candidate = target / "SKILL.md"
    if candidate.is_symlink() or not candidate.is_file():
        return False
    skill_file = SKILLS[name]["source"] / "SKILL.md"
    local = candidate.read_bytes()
    if local == skill_file.read_bytes():
        return True
    relative = skill_file.relative_to(ROOT).as_posix()
    commits = git("log", "--format=%H", "--", relative, check=False)
    if commits.returncode:
        return False
    for revision in commits.stdout.splitlines():
        result = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{revision}:{relative}"], capture_output=True
        )
        if result.returncode == 0 and result.stdout == local:
            return True
    return False


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".vane-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def update(destination, adopt):
    destination = destination.expanduser().absolute()
    destination.mkdir(parents=True, exist_ok=True)
    state_path = destination.parent / (destination.name + ".vane-gpt-image-skills.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if not isinstance(state, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in state.items()):
        raise ValueError(f"更新记录格式无效：{state_path}")
    backup_root = destination.parent / "vane-gpt-image-skills-backups"
    backup_dir = None
    changed = []
    skipped = []
    for name, skill in SKILLS.items():
        target = destination / name
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            skipped.append(name + "（同名项目不是普通目录）")
            continue
        exists = target.exists()
        if exists and name not in state and name not in adopt and not looks_like_previous_install(name, target):
            skipped.append(name + "（无法确认来源）")
            continue
        stage = make_stage(skill, destination)
        try:
            desired = digest_directory(stage)
            if exists and state.get(name) == desired:
                print(f"已是最新：{name}（保留本地修改）")
                continue
            if exists and digest_directory(target) == desired:
                state[name] = desired
                save_state(state_path, state)
                print(f"已是最新：{name}")
                continue
            if exists:
                if backup_dir is None:
                    backup_root.mkdir(parents=True, exist_ok=True)
                    backup_dir = Path(tempfile.mkdtemp(prefix="backup-", dir=backup_root))
                backup = backup_dir / name
                shutil.move(str(target), str(backup))
                try:
                    os.replace(stage, target)
                except Exception:
                    shutil.move(str(backup), str(target))
                    raise
                print(f"已更新：{name}；备份：{backup}")
            else:
                os.replace(stage, target)
                print(f"已安装：{name}")
            state[name] = desired
            save_state(state_path, state)
            changed.append(name)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    if skipped:
        print("\n保留并跳过：")
        for item in skipped:
            print("- " + item)
        print("请先核实目录内容；确认属于本合集且愿意备份替换时，使用 --adopt Skill名称。")
    print(f"\n完成：安装或更新 {len(changed)} 个，跳过 {len(skipped)} 个。请开启新的 Codex 对话。")


def main():
    parser = argparse.ArgumentParser(description="更新 Vane 生图 Skill 合集")
    parser.add_argument("--destination", type=Path, default=Path.home() / ".codex" / "skills", help="Skill 安装目录")
    parser.add_argument("--adopt", action="append", default=[], choices=SKILLS, help="确认接管指定同名 Skill；更新前备份")
    parser.add_argument("--local", action="store_true", help="不联网，只同步当前仓库版本")
    args = parser.parse_args()
    try:
        if not args.local:
            refresh_checkout()
        update(args.destination, set(args.adopt))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"更新未完成：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
