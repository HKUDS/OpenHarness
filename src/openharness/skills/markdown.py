"""Shared markdown skill parsing helpers."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from openharness.skills.types import SkillDefinition


_SKILL_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "user_invocable",
    "model_invocable",
    "aliases",
    "allowed_tools",
    "model_override",
    "effort_override",
    "execution_mode",
}


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    for i, line in enumerate(lines[1:], 1):
        if line.strip() != "---":
            continue
        raw = "\n".join(lines[1:i])
        body = "\n".join(lines[i + 1 :])
        parsed = yaml.safe_load(raw) or {}
        return parsed if isinstance(parsed, dict) else {}, body
    return {}, content


def _coerce_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _coerce_allowed_tools(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else None
    if isinstance(value, list):
        tools = tuple(str(item).strip() for item in value if str(item).strip())
        return tools or None
    return None


def _fallback_name_and_description(default_name: str, body: str) -> tuple[str, str]:
    name = default_name
    description = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            name = stripped[2:].strip() or default_name
            continue
        if stripped and not stripped.startswith("#"):
            description = stripped[:200]
            break
    return name, description or f"Skill: {name}"


def parse_skill_markdown(
    default_name: str,
    content: str,
    *,
    source: str,
    path: str | None = None,
) -> SkillDefinition:
    """Parse one markdown skill file into a normalized definition."""
    frontmatter, body = _split_frontmatter(content)
    fallback_name, fallback_description = _fallback_name_and_description(default_name, body)
    metadata = {k: frontmatter[k] for k in _SKILL_FRONTMATTER_FIELDS if k in frontmatter}
    skill = SkillDefinition(
        name=str(frontmatter.get("name") or fallback_name),
        description=str(frontmatter.get("description") or fallback_description),
        content=content,
        instructions=body.strip() or content.strip(),
        source=source,
        path=path,
        user_invocable=bool(frontmatter.get("user_invocable", True)),
        model_invocable=bool(frontmatter.get("model_invocable", True)),
        aliases=_coerce_aliases(frontmatter.get("aliases")),
        allowed_tools=_coerce_allowed_tools(frontmatter.get("allowed_tools")),
        model_override=(str(frontmatter["model_override"]).strip() if frontmatter.get("model_override") else None),
        effort_override=(str(frontmatter["effort_override"]).strip() if frontmatter.get("effort_override") else None),
        execution_mode=str(frontmatter.get("execution_mode") or "inline"),
        metadata=metadata,
    )
    return SkillDefinition(**asdict(skill))


def load_skills_from_directory(path: Path, *, source: str) -> list[SkillDefinition]:
    """Load all markdown skills from a directory."""
    if not path.exists():
        return []
    skills: list[SkillDefinition] = []
    for skill_path in sorted(path.glob("*.md")):
        content = skill_path.read_text(encoding="utf-8")
        skills.append(
            parse_skill_markdown(
                skill_path.stem,
                content,
                source=source,
                path=str(skill_path),
            )
        )
    return skills
