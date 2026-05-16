"""Memory prompt helpers."""

from __future__ import annotations

from pathlib import Path

from openharness.memory.paths import get_memory_entrypoint, get_project_memory_dir, get_project_memory_entries_dir
from openharness.memory.scan import scan_memory_files


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def load_memory_prompt(cwd: str | Path, *, max_entrypoint_lines: int = 200) -> str | None:
    """Return the memory prompt section for the current project."""
    memory_dir = get_project_memory_dir(cwd)
    entries_dir = get_project_memory_entries_dir(cwd)
    entrypoint = get_memory_entrypoint(cwd)
    lines = [
        "# Memory",
        f"- Persistent memory directory: {memory_dir}",
        f"- Child memory entries directory: {entries_dir}",
        "- Use this directory to store durable user or project context that should survive future sessions.",
        "- Prefer concise English child-memory files under entries/ plus an index entry in MEMORY.md.",
        "- Treat MEMORY.md as the default index. Do not preload linked child memory files into context.",
        "- When a user asks about a linked memory entry or you need its details, read that child file on demand via the path in MEMORY.md.",
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


def load_memory_review_snapshot(cwd: str | Path, *, max_entries: int = 12) -> str | None:
    """Return a compact memory summary tailored for turn-level review prompts."""
    headers = scan_memory_files(cwd, max_files=None)
    if not headers:
        return None

    lines = ["# Current Durable Memories", f"- Total entries: {len(headers)}"]
    for header in headers[:max_entries]:
        identity = header.memory_key or header.path.stem
        detail_parts = [identity]
        if header.memory_type:
            detail_parts.append(header.memory_type)
        detail_parts.append(_truncate(header.title, 120))
        if header.description:
            detail_parts.append(_truncate(header.description, 140))
        lines.append(f"- {' | '.join(part for part in detail_parts if part)}")

    if len(headers) > max_entries:
        lines.append(f"- ... {len(headers) - max_entries} more entries in MEMORY.md")

    return "\n".join(lines)
