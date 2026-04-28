"""Skill data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SkillDefinition:
    """A loaded skill."""

    name: str
    description: str
    content: str
    source: str
    path: str | None = None
    instructions: str = ""
    user_invocable: bool = True
    model_invocable: bool = True
    aliases: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] | None = None
    model_override: str | None = None
    effort_override: str | None = None
    execution_mode: str = "inline"
    metadata: dict[str, Any] = field(default_factory=dict)
