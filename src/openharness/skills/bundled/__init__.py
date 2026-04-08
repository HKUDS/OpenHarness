"""Bundled skill definitions loaded from .md files."""

from __future__ import annotations

from pathlib import Path

from openharness.skills.markdown import load_skills_from_directory
from openharness.skills.types import SkillDefinition

_CONTENT_DIR = Path(__file__).parent / "content"


def get_bundled_skills() -> list[SkillDefinition]:
    """Load all bundled skills from the content/ directory."""
    return load_skills_from_directory(_CONTENT_DIR, source="bundled")
