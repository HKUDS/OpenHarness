"""Personal memory helpers for ``.ohmo``."""

from __future__ import annotations

from pathlib import Path
from re import sub

from ohmo.workspace import get_memory_dir, get_memory_index_path


def list_memory_files(workspace: str | Path | None = None) -> list[Path]:
    """List ``.ohmo`` memory markdown files."""
    memory_dir = get_memory_dir(workspace)
    return sorted(path for path in memory_dir.glob("*.md") if path.name != "MEMORY.md")


def add_memory_entry(workspace: str | Path | None, title: str, content: str) -> Path:
    """Create a personal memory file and append it to ``MEMORY.md``."""
    memory_dir = get_memory_dir(workspace)
    memory_dir.mkdir(parents=True, exist_ok=True)
    slug = sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_") or "memory"
    path = memory_dir / f"{slug}.md"
    path.write_text(content.strip() + "\n", encoding="utf-8")

    index_path = get_memory_index_path(workspace)
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Memory Index\n"
    if path.name not in existing:
        existing = existing.rstrip() + f"\n- [{title}]({path.name})\n"
        index_path.write_text(existing, encoding="utf-8")
    return path


def remove_memory_entry(workspace: str | Path | None, name: str) -> bool:
    """Delete a memory file and remove its index entry."""
    memory_dir = get_memory_dir(workspace)
    matches = [path for path in memory_dir.glob("*.md") if path.stem == name or path.name == name]
    if not matches:
        return False
    path = matches[0]
    path.unlink(missing_ok=True)

    index_path = get_memory_index_path(workspace)
    if index_path.exists():
        lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if path.name not in line]
        index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def load_memory_prompt(workspace: str | Path | None = None, *, max_files: int = 5) -> str | None:
    """Return a prompt section describing personal memory."""
    memory_dir = get_memory_dir(workspace)
    index_path = get_memory_index_path(workspace)
    lines = [
        "# ohmo Memory",
        f"- Personal memory directory: {memory_dir}",
        "- Use this memory for stable user preferences and durable personal context.",
    ]

    if index_path.exists():
        index_lines = index_path.read_text(encoding="utf-8").splitlines()[:200]
        lines.extend(["", "## MEMORY.md", "```md", *index_lines, "```"])

    for path in list_memory_files(workspace)[:max_files]:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            continue
        lines.extend(["", f"## {path.name}", "```md", content[:4000], "```"])

    return "\n".join(lines)
