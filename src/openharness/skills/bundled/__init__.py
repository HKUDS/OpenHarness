"""Bundled skill definitions loaded from .md files."""

from __future__ import annotations

from pathlib import Path

from openharness.skills.types import SkillDefinition

_CONTENT_DIR = Path(__file__).parent / "content"


def get_bundled_skills() -> list[SkillDefinition]:
    """Load all bundled skills from the content/ directory. 从“content/”目录中加载所有捆绑的技能。"""
    skills: list[SkillDefinition] = []
    if not _CONTENT_DIR.exists():
        return skills
    for path in sorted(_CONTENT_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        name, description = _parse_frontmatter(path.stem, content)
        skills.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source="bundled",
                path=str(path),
            )
        )
    return skills


def _parse_frontmatter(default_name: str, content: str) -> tuple[str, str]:
    """Extract name and description from a skill markdown file.
    从技能的 Markdown 文件中提取名称和 description。
    Supports YAML frontmatter (``---`` delimited) and falls back to heading/paragraph parsing.
    支持 YAML 前置标记（以“---”分隔）格式，并在无法识别时转而采用标题/段落解析方式。
    """
    name = default_name
    description = ""
    lines = content.splitlines()

    # Try YAML frontmatter first
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                for fm_line in lines[1:i]:
                    fm = fm_line.strip()
                    if fm.startswith("name:"):
                        val = fm[5:].strip().strip("'\"")
                        if val:
                            name = val
                    elif fm.startswith("description:"):
                        val = fm[12:].strip().strip("'\"")
                        if val:
                            description = val
                break
        if description:
            return name, description

    # Fallback: heading + first paragraph
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            name = stripped[2:].strip() or default_name
            continue
        if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
            description = stripped[:200]
            break
    return name, description or f"Bundled skill: {name}"
