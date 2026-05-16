"""Skill exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from openharness.skills.registry import SkillRegistry
    from openharness.skills.types import SkillDefinition

__all__ = [
    "SkillDefinition",
    "SkillRegistry",
    "discover_project_skill_dirs",
    "get_user_skill_dirs",
    "get_user_skills_dir",
    "load_skill_registry",
]


def __getattr__(name: str):
    if name in {"discover_project_skill_dirs", "get_user_skill_dirs", "get_user_skills_dir", "load_skill_registry"}:
        from openharness.skills.loader import (
            discover_project_skill_dirs,
            get_user_skill_dirs,
            get_user_skills_dir,
            load_skill_registry,
        )

        return {
            "discover_project_skill_dirs": discover_project_skill_dirs,
            "get_user_skill_dirs": get_user_skill_dirs,
            "get_user_skills_dir": get_user_skills_dir,
            "load_skill_registry": load_skill_registry,
        }[name]
    if name == "SkillRegistry":
        from openharness.skills.registry import SkillRegistry

        return SkillRegistry
    if name == "SkillDefinition":
        from openharness.skills.types import SkillDefinition

        return SkillDefinition
    raise AttributeError(name)
