"""Runtime helpers for activating skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from openharness.config.settings import Settings
from openharness.skills.loader import load_skill_registry
from openharness.skills.types import SkillDefinition

if TYPE_CHECKING:
    from openharness.tools.base import ToolRegistry


@dataclass(frozen=True)
class ActiveSkillContext:
    """Scoped runtime overrides for an active skill."""

    definition: SkillDefinition

    @property
    def allowed_tools(self) -> tuple[str, ...] | None:
        return self.definition.allowed_tools

    @property
    def model_override(self) -> str | None:
        return self.definition.model_override

    @property
    def effort_override(self) -> str | None:
        return self.definition.effort_override


def resolve_skill(name: str, cwd: str | Path) -> SkillDefinition | None:
    """Resolve a skill from the current registry."""
    return load_skill_registry(cwd).get(name)


def activate_skill(name: str, cwd: str | Path) -> ActiveSkillContext | None:
    """Resolve and wrap a skill for runtime activation."""
    skill = resolve_skill(name, cwd)
    if skill is None:
        return None
    return ActiveSkillContext(definition=skill)


def build_skill_instruction_message(skill: SkillDefinition) -> str:
    """Return the user-visible instruction payload for a skill activation."""
    return skill.instructions or skill.content


def build_active_skill_section(active_skill: ActiveSkillContext) -> str:
    """Return the prompt section describing the active skill scope."""
    allowed_tools = ", ".join(active_skill.allowed_tools) if active_skill.allowed_tools else "inherit runtime defaults"
    return (
        "# Active Skill\n"
        f"- Name: {active_skill.definition.name}\n"
        f"- Description: {active_skill.definition.description}\n"
        f"- Execution mode: {active_skill.definition.execution_mode}\n"
        f"- Allowed tools: {allowed_tools}\n\n"
        "Use the following skill instructions as the active scoped workflow for this turn:\n\n"
        f"{active_skill.definition.instructions}"
    )


def build_effective_system_prompt(base_prompt: str, active_skill: ActiveSkillContext | None) -> str:
    """Return the system prompt with any active skill section applied."""
    if active_skill is None:
        return base_prompt
    return f"{base_prompt}\n\n{build_active_skill_section(active_skill)}"


def filter_tool_registry(tool_registry: "ToolRegistry", allowed_tools: tuple[str, ...] | None) -> "ToolRegistry":
    """Return a filtered registry when a skill narrows tool access."""
    if allowed_tools is None:
        return tool_registry
    from openharness.tools.base import ToolRegistry

    allowed = {name.strip() for name in allowed_tools if name.strip()}
    filtered = ToolRegistry()
    for tool in tool_registry.list_tools():
        if tool.name in allowed:
            filtered.register(tool)
    return filtered


def apply_skill_overrides(settings: Settings, active_skill: ActiveSkillContext | None) -> Settings:
    """Return settings with any active skill overrides applied."""
    if active_skill is None:
        return settings
    updates: dict[str, object] = {}
    if active_skill.model_override:
        updates["model"] = active_skill.model_override
    if active_skill.effort_override:
        updates["effort"] = active_skill.effort_override
    if not updates:
        return settings
    return settings.model_copy(update=updates)
