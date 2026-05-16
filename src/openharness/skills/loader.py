"""Skill loading from bundled, user, compatibility, and project directories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from openharness.config.paths import get_config_dir
from openharness.config.settings import load_settings
from openharness.skills._frontmatter import (
    optional_frontmatter_str,
    parse_bool_frontmatter,
    parse_skill_frontmatter,
    parse_skill_metadata,
)
from openharness.skills.bundled import get_bundled_skills
from openharness.skills.registry import SkillRegistry
from openharness.skills.types import SkillDefinition

logger = logging.getLogger(__name__)

_USER_COMPAT_SKILL_DIRS = (
    (".claude", "skills"),
    (".agents", "skills"),
)
_DEFAULT_PROJECT_SKILL_DIRS = (".openharness/skills", ".agents/skills", ".claude/skills")


def get_user_skills_dir() -> Path:
    """Return the OpenHarness user skills directory."""
    path = get_config_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_skill_dirs() -> list[Path]:
    """Return user-level skill directories loaded by default."""
    return [get_user_skills_dir(), *(Path.home().joinpath(*parts) for parts in _USER_COMPAT_SKILL_DIRS)]


def load_skill_registry(
    cwd: str | Path | None = None,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings=None,
) -> SkillRegistry:
    """Load bundled, user-defined, project, and plugin skills."""
    registry = SkillRegistry()
    for skill in get_bundled_skills():
        registry.register(skill)
    for skill in load_user_skills():
        registry.register(skill)
    for skill in load_skills_from_dirs(extra_skill_dirs, source="user"):
        registry.register(skill)

    resolved_settings = settings or load_settings()
    if cwd is not None and getattr(resolved_settings, "allow_project_skills", True):
        project_dirs = discover_project_skill_dirs(
            cwd,
            getattr(resolved_settings, "project_skill_dirs", list(_DEFAULT_PROJECT_SKILL_DIRS)),
        )
        for skill in load_skills_from_dirs(project_dirs, source="project", create_missing=False):
            registry.register(skill)

    if cwd is not None:
        from openharness.plugins.loader import load_plugins

        for plugin in load_plugins(resolved_settings, cwd, extra_roots=extra_plugin_roots):
            if not plugin.enabled:
                continue
            for skill in plugin.skills:
                registry.register(skill)
    return registry


def load_user_skills() -> list[SkillDefinition]:
    """Load markdown skills from user-level OpenHarness and compatibility directories."""
    return load_skills_from_dirs(get_user_skill_dirs(), source="user")


def discover_project_skill_dirs(
    cwd: str | Path,
    project_skill_dirs: Iterable[str] | None = None,
) -> list[Path]:
    """Return existing project skill directories from cwd up to the git root.

    Directories are ordered from least-specific to most-specific so later registry
    entries can override broader project or user skills deterministically.
    """
    start = Path(cwd).expanduser().resolve()
    if not start.exists():
        start = start.parent
    if start.is_file():
        start = start.parent

    relative_dirs = _valid_project_skill_dirs(project_skill_dirs or _DEFAULT_PROJECT_SKILL_DIRS)
    git_root = _find_git_root(start)
    home = Path.home().resolve()
    current = start
    levels: list[Path] = []
    while True:
        levels.append(current)
        if git_root is not None and current == git_root:
            break
        if git_root is None and current == home:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    roots: list[Path] = []
    seen: set[Path] = set()
    for base in reversed(levels):
        for rel in relative_dirs:
            candidate = (base / rel).resolve()
            if candidate in seen or not candidate.is_dir():
                continue
            seen.add(candidate)
            roots.append(candidate)
    return roots


def _valid_project_skill_dirs(project_skill_dirs: Iterable[str]) -> list[Path]:
    """Return safe relative project skill paths."""
    paths: list[Path] = []
    for raw in project_skill_dirs:
        value = str(raw).strip()
        if not value:
            continue
        rel = Path(value)
        if rel.is_absolute() or ".." in rel.parts:
            logger.warning("Ignoring unsafe project skill dir: %s", raw)
            continue
        paths.append(rel)
    return paths


def _find_git_root(start: Path) -> Path | None:
    """Find the nearest git root containing start, if any."""
    current = start
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_skills_from_dirs(
    directories: Iterable[str | Path] | None,
    *,
    source: str = "user",
    create_missing: bool = True,
) -> list[SkillDefinition]:
    """Load markdown skills from one or more directories.

    Supported layout:
    - ``<root>/<skill-dir>/SKILL.md``
    """
    skills: list[SkillDefinition] = []
    if not directories:
        return skills
    seen: set[Path] = set()
    for directory in directories:
        root = Path(directory).expanduser().resolve()
        if create_missing:
            root.mkdir(parents=True, exist_ok=True)
        elif not root.is_dir():
            continue
        candidates: list[Path] = []
        for child in sorted(root.iterdir()):
            if child.is_dir():
                skill_path = child / "SKILL.md"
                if skill_path.exists():
                    candidates.append(skill_path)
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            content = path.read_text(encoding="utf-8")
            default_name = path.parent.name
            metadata = _parse_skill_metadata(default_name, content)
            name = metadata["name"]
            description = metadata["description"]
            display_name = name if name != default_name else None
            skills.append(
                SkillDefinition(
                    name=name,
                    description=description,
                    content=content,
                    source=source,
                    path=str(path),
                    base_dir=str(path.parent),
                    command_name=default_name,
                    display_name=display_name,
                    user_invocable=metadata["user_invocable"],
                    disable_model_invocation=metadata["disable_model_invocation"],
                    model=metadata["model"],
                    argument_hint=metadata["argument_hint"],
                )
            )
    return skills


def _parse_skill_markdown(default_name: str, content: str) -> tuple[str, str]:
    """Parse name and description from a skill markdown file with YAML frontmatter support."""
    return parse_skill_frontmatter(default_name, content, fallback_template="Skill: {name}")


def _parse_skill_metadata(default_name: str, content: str) -> dict:
    parsed = parse_skill_metadata(default_name, content, fallback_template="Skill: {name}")
    frontmatter = parsed.get("frontmatter")
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return {
        "name": str(parsed["name"]),
        "description": str(parsed["description"]),
        "user_invocable": parse_bool_frontmatter(frontmatter.get("user-invocable"), default=True),
        "disable_model_invocation": parse_bool_frontmatter(
            frontmatter.get("disable-model-invocation"),
            default=False,
        ),
        "model": optional_frontmatter_str(frontmatter.get("model")),
        "argument_hint": optional_frontmatter_str(frontmatter.get("argument-hint")),
    }
