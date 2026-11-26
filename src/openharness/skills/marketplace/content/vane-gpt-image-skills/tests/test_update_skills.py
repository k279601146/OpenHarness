import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


UPDATER = Path(__file__).resolve().parents[1] / "scripts/update_skills.py"


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)


def installer_text(names):
    entries = ",\n".join(
        f'    "{name}": {{"source": ROOT / "skills" / "{name}", "items": ("SKILL.md", "assets")}}'
        for name in names
    )
    return f'from pathlib import Path\nROOT = Path(__file__).resolve().parent.parent\nSKILLS = {{\n{entries}\n}}\n'


def write_skill(repo, name, content):
    skill = repo / "skills" / name
    (skill / "assets").mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(content, encoding="utf-8")
    (skill / "assets" / "example.txt").write_text(content, encoding="utf-8")


def configure(repo):
    run("git", "config", "user.name", "Test", cwd=repo)
    run("git", "config", "user.email", "test@example.invalid", cwd=repo)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        run("git", "init", "-b", "main", cwd=self.repo)
        configure(self.repo)
        (self.repo / "scripts").mkdir()
        shutil.copy2(UPDATER, self.repo / "scripts/update_skills.py")
        (self.repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
        (self.repo / "scripts/install_skills.py").write_text(installer_text(["alpha"]), encoding="utf-8")
        write_skill(self.repo, "alpha", "alpha version one\n")
        run("git", "add", ".", cwd=self.repo)
        run("git", "commit", "-m", "first", cwd=self.repo)

    def test_legacy_upgrade_backups_skip_unknown_and_preserve_unrelated(self):
        destination = self.root / "home" / "skills"
        shutil.copytree(self.repo / "skills/alpha", destination / "alpha")
        (destination / "alpha" / "personal.txt").write_text("my notes", encoding="utf-8")
        write_skill(self.repo, "alpha", "alpha version two\n")
        write_skill(self.repo, "beta", "beta version one\n")
        write_skill(self.repo, "gamma", "gamma version one\n")
        (self.repo / "scripts/install_skills.py").write_text(installer_text(["alpha", "beta", "gamma"]), encoding="utf-8")
        run("git", "add", ".", cwd=self.repo)
        run("git", "commit", "-m", "second", cwd=self.repo)
        (destination / "beta").mkdir()
        (destination / "beta/SKILL.md").write_text("another source", encoding="utf-8")
        (destination / "unrelated").mkdir()
        (destination / "unrelated/note").write_text("untouched", encoding="utf-8")
        result = run(sys.executable, str(self.repo / "scripts/update_skills.py"), "--local", "--destination", str(destination))
        self.assertIn("无法确认来源", result.stdout)
        self.assertEqual((destination / "alpha/SKILL.md").read_text(), "alpha version two\n")
        self.assertEqual((destination / "beta/SKILL.md").read_text(), "another source")
        self.assertEqual((destination / "gamma/SKILL.md").read_text(), "gamma version one\n")
        self.assertEqual((destination / "unrelated/note").read_text(), "untouched")
        backups = list((destination.parent / "vane-gpt-image-skills-backups").glob("*/alpha/personal.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "my notes")
        # Local edits are preserved if the repository version has not changed.
        (destination / "alpha/SKILL.md").write_text("my local edit", encoding="utf-8")
        run(sys.executable, str(self.repo / "scripts/update_skills.py"), "--local", "--destination", str(destination))
        self.assertEqual((destination / "alpha/SKILL.md").read_text(), "my local edit")

    def test_adopt_explicitly_backs_up_an_unrecognized_skill(self):
        destination = self.root / "home" / "skills"
        (destination / "alpha").mkdir(parents=True)
        (destination / "alpha/SKILL.md").write_text("custom skill", encoding="utf-8")
        run(sys.executable, str(self.repo / "scripts/update_skills.py"), "--local", "--destination", str(destination), "--adopt", "alpha")
        self.assertEqual((destination / "alpha/SKILL.md").read_text(), "alpha version one\n")
        backups = list((destination.parent / "vane-gpt-image-skills-backups").glob("*/alpha/SKILL.md"))
        self.assertEqual(backups[0].read_text(), "custom skill")

    def test_new_style_updates_existing_skill_and_keeps_backup(self):
        destination = self.root / "home" / "skills"
        cmd = [sys.executable, str(self.repo / "scripts/update_skills.py"), "--local", "--destination", str(destination)]
        run(*cmd)
        new_style = self.repo / "skills/alpha/assets/new-style.txt"
        new_style.write_text("new style", encoding="utf-8")
        run(*cmd)
        self.assertEqual((destination / "alpha/assets/new-style.txt").read_text(), "new style")
        backups = list((destination.parent / "vane-gpt-image-skills-backups").glob("*/alpha/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "alpha version one\n")

    def test_one_command_pulls_and_uses_new_skill_catalog(self):
        remote = self.root / "remote.git"
        run("git", "clone", "--bare", str(self.repo), str(remote))
        checkout = self.root / "checkout"
        run("git", "clone", str(remote), str(checkout))
        destination = self.root / "home" / "skills"
        shutil.copytree(checkout / "skills/alpha", destination / "alpha")
        run("git", "remote", "add", "origin", str(remote), cwd=self.repo)
        write_skill(self.repo, "alpha", "alpha version two\n")
        write_skill(self.repo, "beta", "beta version one\n")
        (self.repo / "scripts/install_skills.py").write_text(installer_text(["alpha", "beta"]), encoding="utf-8")
        run("git", "add", ".", cwd=self.repo)
        run("git", "commit", "-m", "new skill", cwd=self.repo)
        run("git", "push", "origin", "main", cwd=self.repo)
        run(sys.executable, str(checkout / "scripts/update_skills.py"), "--destination", str(destination))
        self.assertEqual((destination / "alpha/SKILL.md").read_text(), "alpha version two\n")
        self.assertEqual((destination / "beta/SKILL.md").read_text(), "beta version one\n")

    def test_dirty_checkout_is_not_changed(self):
        (self.repo / "notes.txt").write_text("user work", encoding="utf-8")
        result = subprocess.run([sys.executable, str(self.repo / "scripts/update_skills.py")], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未提交或未跟踪", result.stderr)
        self.assertEqual((self.repo / "notes.txt").read_text(), "user work")


if __name__ == "__main__":
    unittest.main()
