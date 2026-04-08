"""Skill registry."""

from __future__ import annotations

from openharness.skills.types import SkillDefinition


class SkillRegistry:
    """Store loaded skills by name and alias."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._aliases: dict[str, str] = {}

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower()

    def register(self, skill: SkillDefinition) -> None:
        """Register one skill."""
        canonical = self._normalize(skill.name)
        self._skills[canonical] = skill
        self._aliases[canonical] = canonical
        for alias in skill.aliases:
            normalized = self._normalize(alias)
            if normalized:
                self._aliases[normalized] = canonical

    def get(self, name: str) -> SkillDefinition | None:
        """Return a skill by name or alias."""
        normalized = self._normalize(name)
        canonical = self._aliases.get(normalized, normalized)
        return self._skills.get(canonical)

    def list_skills(self) -> list[SkillDefinition]:
        """Return all skills sorted by name."""
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def list_user_invocable(self) -> list[SkillDefinition]:
        """Return skills exposed as slash commands."""
        return [skill for skill in self.list_skills() if skill.user_invocable]

    def list_model_invocable(self) -> list[SkillDefinition]:
        """Return skills exposed to the model."""
        return [skill for skill in self.list_skills() if skill.model_invocable]
