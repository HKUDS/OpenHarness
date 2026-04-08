"""Higher-level system prompt assembly."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_project_issue_file, get_project_pr_comments_file
from openharness.config.settings import Settings
from openharness.memory import find_relevant_memories, load_memory_prompt
from openharness.memory.powermem_client import search_powermem_for_prompt
from openharness.prompts.claudemd import load_claude_md_prompt
from openharness.prompts.system_prompt import build_system_prompt
from openharness.skills.loader import load_skill_registry


def _build_skills_section(cwd: str | Path) -> str | None:
    """Build a system prompt section listing available skills."""
    registry = load_skill_registry(cwd)
    skills = registry.list_skills()
    if not skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following skills are available via the `skill` tool. "
        "When a user's request matches a skill, invoke it with `skill(name=\"<skill_name>\")` "
        "to load detailed instructions before proceeding.",
        "",
    ]
    for skill in skills:
        lines.append(f"- **{skill.name}**: {skill.description}")
    return "\n".join(lines)


def build_runtime_system_prompt(
    settings: Settings,
    *,
    cwd: str | Path,
    latest_user_prompt: str | None = None,
) -> str:
    """Build the runtime system prompt with project instructions and memory."""
    sections = [build_system_prompt(custom_prompt=settings.system_prompt, cwd=str(cwd))]

    if settings.fast_mode:
        sections.append(
            "# Session Mode\nFast mode is enabled. Prefer concise replies, minimal tool use, and quicker progress over exhaustive exploration."
        )

    sections.append(
        "# Reasoning Settings\n"
        f"- Effort: {settings.effort}\n"
        f"- Passes: {settings.passes}\n"
        "Adjust depth and iteration count to match these settings while still completing the task."
    )

    skills_section = _build_skills_section(cwd)
    if skills_section:
        sections.append(skills_section)

    claude_md = load_claude_md_prompt(cwd)
    if claude_md:
        sections.append(claude_md)

    for title, path in (
        ("Issue Context", get_project_issue_file(cwd)),
        ("Pull Request Comments", get_project_pr_comments_file(cwd)),
    ):
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                sections.append(f"# {title}\n\n```md\n{content[:12000]}\n```")

    if settings.memory.enabled:
        memory_section = load_memory_prompt(
            cwd,
            max_entrypoint_lines=settings.memory.max_entrypoint_lines,
        )
        if memory_section:
            sections.append(memory_section)

        if latest_user_prompt:
            mem = settings.memory
            if mem.backend in ("local", "hybrid"):
                relevant = find_relevant_memories(
                    latest_user_prompt,
                    cwd,
                    max_results=mem.max_files,
                )
                if relevant:
                    lines = ["# Relevant Memories"]
                    for header in relevant:
                        content = header.path.read_text(encoding="utf-8", errors="replace").strip()
                        lines.extend(
                            [
                                "",
                                f"## {header.path.name}",
                                "```md",
                                content[:8000],
                                "```",
                            ]
                        )
                    sections.append("\n".join(lines))

            if mem.backend in ("powermem_http", "powermem_sdk", "hybrid"):
                pm_hits = search_powermem_for_prompt(latest_user_prompt, mem)
                if pm_hits:
                    lines = ["# PowerMem Retrieval"]
                    for label, text in pm_hits:
                        lines.extend(["", f"## {label}", "```md", text[:8000], "```"])
                    sections.append("\n".join(lines))

    return "\n\n".join(section for section in sections if section.strip())
