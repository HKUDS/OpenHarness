"""Memory prompt helpers."""

from __future__ import annotations

from pathlib import Path

from openharness.memory.paths import get_memory_entrypoint, get_project_memory_dir


def load_memory_prompt(cwd: str | Path, *, max_entrypoint_lines: int = 200) -> str | None:
    """Return the memory prompt section for the current project."""
    memory_dir = get_project_memory_dir(cwd)
    entrypoint = get_memory_entrypoint(cwd)
    lines = [
        "# Memory",
        f"- Persistent memory directory: {memory_dir}",
        "- Use this directory to store durable project and repository context that should survive future sessions.",
        "- Prefer concise topic files plus an index entry in MEMORY.md.",
    ]

    if entrypoint.exists():
        content_lines = entrypoint.read_text(encoding="utf-8").splitlines()[:max_entrypoint_lines]
        if content_lines:
            lines.extend(["", "## MEMORY.md", "```md", *content_lines, "```"])
    else:
        lines.extend(
            [
                "",
                "## MEMORY.md",
                "(not created yet)",
            ]
        )

    return "\n".join(lines)
