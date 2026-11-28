"""Project instruction discovery and loading (CLAUDE.md + AGENTS.md)."""

from __future__ import annotations

from pathlib import Path

from openharness.config.paths import get_config_dir

# Per-directory instruction filenames, in load order. AGENTS.md is the
# cross-tool standard (Codex et al.); CLAUDE.md is OpenHarness-native. Both are
# loaded when present so a repo authored for either convention works unchanged.
_INSTRUCTION_FILENAMES = ("AGENTS.md", "CLAUDE.md")


def discover_claude_md_files(cwd: str | Path) -> list[Path]:
    """Discover project instruction files (AGENTS.md / CLAUDE.md) from cwd upward.

    Walks from ``cwd`` to the filesystem root collecting, at each level, any
    ``AGENTS.md`` / ``CLAUDE.md`` / ``.claude/CLAUDE.md`` plus ``.claude/rules/*.md``.
    Order is most-specific first (cwd → parents → root); the least-specific global
    fallback ``~/.openharness/AGENTS.md`` is appended last, matching the existing
    root-last convention so repo/dir instructions take precedence over it.
    """
    current = Path(cwd).resolve()
    results: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        if candidate not in seen and candidate.exists():
            results.append(candidate)
            seen.add(candidate)

    for directory in [current, *current.parents]:
        for name in _INSTRUCTION_FILENAMES:
            add(directory / name)
        add(directory / ".claude" / "CLAUDE.md")

        rules_dir = directory / ".claude" / "rules"
        if rules_dir.is_dir():
            for rule in sorted(rules_dir.glob("*.md")):
                add(rule)

        if directory.parent == directory:
            break

    # Least-specific global instructions, loaded last (overridable by repo/dir).
    # create=False: discovery must not materialize ~/.openharness as a side effect.
    try:
        add(get_config_dir(create=False) / "AGENTS.md")
    except OSError:
        pass

    return results


def load_claude_md_prompt(cwd: str | Path, *, max_chars_per_file: int = 12000) -> str | None:
    """Load discovered instruction files into one prompt section."""
    files = discover_claude_md_files(cwd)
    if not files:
        return None

    lines = ["# Project Instructions"]
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + "\n...[truncated]..."
        lines.extend(["", f"## {path}", "```md", content.strip(), "```"])
    return "\n".join(lines)
