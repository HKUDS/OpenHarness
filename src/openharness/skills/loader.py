"""Skill loading from bundled and user directories."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_config_dir
from openharness.config.settings import load_settings
from openharness.skills.bundled import get_bundled_skills
from openharness.skills.registry import SkillRegistry
from openharness.skills.types import SkillDefinition


def get_user_skills_dir() -> Path:
    """Return the user skills directory."""
    path = get_config_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_skill_registry(cwd: str | Path | None = None) -> SkillRegistry:
    """Load bundled and user-defined skills."""
    registry = SkillRegistry()
    for skill in get_bundled_skills():
        registry.register(skill)
    for skill in load_user_skills():
        registry.register(skill)
    if cwd is not None:
        from openharness.plugins.loader import load_plugins

        settings = load_settings()
        for plugin in load_plugins(settings, cwd):
            if not plugin.enabled:
                continue
            for skill in plugin.skills:
                registry.register(skill)
    return registry


def load_user_skills() -> list[SkillDefinition]:
    """Load markdown skills from the user config directory. 从用户配置目录加载 Markdown 技能。"""
    skills: list[SkillDefinition] = []
    for path in sorted(get_user_skills_dir().rglob("SKILL.md")):        # 递归查找 skills 目录下的 SKILL.md 文件
        content = path.read_text(encoding="utf-8")
        name, description = _parse_skill_markdown(path.stem, content)
        skills.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source="user",
                path=str(path),
            )
        )
    return skills


def _parse_skill_markdown(default_name: str, content: str) -> tuple[str, str]:
    """Parse name and description from a skill markdown file with YAML frontmatter support."""
    name = default_name
    description = ""

    lines = content.splitlines()

    # Try YAML frontmatter first (--- ... ---)
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                # Parse frontmatter fields
                for fm_line in lines[1:i]:
                    fm_stripped = fm_line.strip()
                    if fm_stripped.startswith("name:"):
                        val = fm_stripped[5:].strip().strip("'\"")
                        if val:
                            name = val
                    elif fm_stripped.startswith("description:"):
                        val = fm_stripped[12:].strip().strip("'\"")
                        if val:
                            description = val
                break

    # Fallback: extract from headings and first paragraph 备用方案：从标题和第一段中提取内容
    if not description:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                if not name or name == default_name:
                    name = stripped[2:].strip() or default_name
                continue
            if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                description = stripped[:200]
                break

    if not description:
        description = f"Skill: {name}"
    return name, description
