"""Bundled skill definitions loaded from .md files."""

from __future__ import annotations

from pathlib import Path

from openharness.skills.types import SkillDefinition

_CONTENT_DIR = Path(__file__).parent / "content"


def get_bundled_skills() -> list[SkillDefinition]:
    """Load all bundled skills from content/ and aesthetics/ directories."""
    skills: list[SkillDefinition] = []
    
    # 扫描 content (逻辑技能) 和 aesthetics (审美技能)
    for sub_dir, s_type in [("content", "logic"), ("aesthetics", "aesthetic")]:
        target_dir = Path(__file__).parent / sub_dir
        if not target_dir.exists():
            continue
            
        for path in sorted(target_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            info = _parse_full_frontmatter(path.stem, content)
            skills.append(
                SkillDefinition(
                    name=info["name"],
                    description=info["description"],
                    content=content,
                    source="bundled",
                    path=str(path),
                    skill_type=s_type,
                    metadata=info["metadata"],
                )
            )
    return skills


def _parse_full_frontmatter(default_name: str, content: str) -> dict:
    """全面解析 frontmatter，返回包含 metadata 的字典。"""
    import yaml
    
    res = {
        "name": default_name,
        "description": f"Bundled skill: {default_name}",
        "metadata": {}
    }
    
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        end_index = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end_index = i
                break
        
        if end_index != -1:
            fm_text = "\n".join(lines[1:end_index])
            try:
                metadata = yaml.safe_load(fm_text)
                if isinstance(metadata, dict):
                    res["name"] = metadata.get("name", res["name"])
                    res["description"] = metadata.get("description", res["description"])
                    res["metadata"] = metadata
            except Exception:
                pass
                
    if res["description"] == f"Bundled skill: {default_name}":
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                res["name"] = stripped[2:].strip() or res["name"]
                continue
            if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                res["description"] = stripped[:200]
                break
                
    return res
