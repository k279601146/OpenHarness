import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "install_skills.py"


class InstallationTests(unittest.TestCase):
    def run_installer(self, destination, *args):
        return subprocess.run(
            [sys.executable, str(INSTALLER), *args, "--destination", str(destination)],
            capture_output=True,
            text=True,
        )

    def test_install_all_and_required_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--all")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "vane-portrait-gif-stickers/SKILL.md").is_file())
            self.assertTrue((target / "vane-portrait-gif-stickers/scripts/export_frames.py").is_file())
            self.assertTrue((target / "vane-portrait-gif-stickers/references/frame-manifest.md").is_file())
            self.assertTrue((target / "vane-cinematic-poster/SKILL.md").is_file())
            self.assertTrue((target / "vane-cinematic-poster/references/layouts.md").is_file())
            self.assertTrue((target / "vane-cinematic-poster/assets/poster-layouts-28-36.png").is_file())
            self.assertTrue((target / "vane-cinematic-poster/assets/poster-layouts-zh-28-36.png").is_file())
            self.assertTrue((target / "vane-book-cinema/SKILL.md").is_file())
            self.assertEqual(len(list((target / "vane-book-cinema/assets").glob("books-*.jpg"))), 4)
            red_packet = target / "wechat-red-packet-cover"
            self.assertTrue((red_packet / "SKILL.md").is_file())
            self.assertTrue((red_packet / "scripts/cover_tool.py").is_file())
            self.assertTrue((red_packet / "references/styles.md").is_file())
            self.assertTrue((red_packet / "LICENSE").is_file())
            self.assertEqual(len(list((red_packet / "assets/style-gallery").glob("*.png"))), 4)
            pet = target / "vane-pet-new-year-portrait"
            self.assertTrue((pet / "SKILL.md").is_file())
            self.assertTrue((pet / "scripts/fit_white_canvas.py").is_file())
            self.assertTrue((pet / "evals/evals.json").is_file())
            self.assertEqual(len(list((pet / "assets").glob("*.png"))), 4)
            xhs = target / "vane-xhs-design"
            self.assertTrue((xhs / "SKILL.md").is_file())
            self.assertTrue((xhs / "styles/scrapbook/STYLE.md").is_file())
            self.assertTrue((xhs / "styles/scrapbook/references/content-and-layout.md").is_file())
            self.assertTrue((xhs / "styles/scrapbook/assets/approved-plant-reference.png").is_file())
            self.assertTrue((xhs / "styles/minimal-product/STYLE.md").is_file())
            self.assertTrue((xhs / "styles/minimal-product/references/layout-and-content.md").is_file())
            self.assertTrue((xhs / "styles/minimal-product/assets/strawberry-style-reference.png").is_file())
            self.assertTrue((xhs / "styles/bold-color/STYLE.md").is_file())
            self.assertTrue((xhs / "styles/bold-color/references/layout-and-content.md").is_file())
            self.assertTrue((xhs / "styles/bold-color/assets/approved-color-reference.png").is_file())
            self.assertFalse((target / "vane-portrait-gif-stickers/.git").exists())
            self.assertFalse((target / "vane-portrait-gif-stickers/skills").exists())

    def test_existing_skill_is_preserved_and_all_does_not_partially_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            existing = target / "vane-cinematic-poster"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("保留原内容", encoding="utf-8")
            result = self.run_installer(target, "--all")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), "保留原内容")
            self.assertFalse((target / "vane-portrait-gif-stickers").exists())
            self.assertFalse((target / "vane-book-cinema").exists())
            self.assertFalse((target / "wechat-red-packet-cover").exists())
            self.assertFalse((target / "vane-pet-new-year-portrait").exists())
            self.assertFalse((target / "vane-xhs-design").exists())

    def test_install_stickers_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "vane-portrait-gif-stickers")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "vane-portrait-gif-stickers/scripts/export_frames.py").is_file())
            self.assertFalse((target / "vane-cinematic-poster").exists())

    def test_install_posters_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "vane-cinematic-poster")
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / "vane-cinematic-poster"
            self.assertTrue((skill / "references/layouts.md").is_file())
            self.assertEqual(len(list((skill / "assets").glob("poster-layouts-*.png"))), 8)
            self.assertFalse((target / "vane-portrait-gif-stickers").exists())

    def test_install_book_cinema_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "vane-book-cinema")
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / "vane-book-cinema"
            self.assertTrue((skill / "agents/openai.yaml").is_file())
            self.assertEqual(len(list((skill / "assets").glob("books-*.jpg"))), 4)
            self.assertFalse((target / "vane-cinematic-poster").exists())

    def test_install_red_packet_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "wechat-red-packet-cover")
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / "wechat-red-packet-cover"
            self.assertTrue((skill / "scripts/cover_tool.py").is_file())
            self.assertEqual(len(list((skill / "assets/style-gallery").glob("*.png"))), 4)
            self.assertFalse((target / "vane-cinematic-poster").exists())

    def test_install_pet_portrait_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "vane-pet-new-year-portrait")
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / "vane-pet-new-year-portrait"
            self.assertTrue((skill / "scripts/fit_white_canvas.py").is_file())
            self.assertEqual(len(list((skill / "assets").glob("*.png"))), 4)
            self.assertFalse((target / "vane-cinematic-poster").exists())

    def test_install_xhs_design_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            result = self.run_installer(target, "--skill", "vane-xhs-design")
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = target / "vane-xhs-design"
            self.assertTrue((skill / "styles/scrapbook/STYLE.md").is_file())
            self.assertTrue((skill / "styles/scrapbook/assets/layout-skeleton.png").is_file())
            self.assertTrue((skill / "styles/minimal-product/STYLE.md").is_file())
            self.assertTrue((skill / "styles/minimal-product/assets/nine-page-layout.png").is_file())
            self.assertTrue((skill / "styles/bold-color/STYLE.md").is_file())
            self.assertTrue((skill / "styles/bold-color/assets/nine-page-layout.png").is_file())
            self.assertFalse((target / "vane-cinematic-poster").exists())


if __name__ == "__main__":
    unittest.main()
