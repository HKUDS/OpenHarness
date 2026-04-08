"""Skill loading from bundled and user directories."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_config_dir
from openharness.config.settings import load_settings
from openharness.skills.bundled import get_bundled_skills
from openharness.skills.markdown import load_skills_from_directory, parse_skill_markdown
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
    """Load markdown skills from the user config directory."""
    return load_skills_from_directory(get_user_skills_dir(), source="user")


__all__ = [
    "get_user_skills_dir",
    "load_skill_registry",
    "load_user_skills",
    "parse_skill_markdown",
]
