"""Paths for persistent project memory."""

from __future__ import annotations

import contextlib
from hashlib import sha1
from pathlib import Path
import re

from openharness.config.paths import get_data_dir, get_memory_store_dir, memory_store_uses_shared_root
from openharness.utils.fs import atomic_write_text


_MEMORY_INDEX_LINE_RE = re.compile(r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)\s*$")


def _project_memory_leaf(path: Path) -> str:
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"{path.name}-{digest}"


def _append_index_entry(entrypoint: Path, *, title: str, relative_path: str) -> None:
    entry_line = f"- [{title}]({relative_path})"
    existing_lines = entrypoint.read_text(encoding="utf-8").splitlines() if entrypoint.exists() else ["# Memory Index"]
    for index, line in enumerate(existing_lines):
        if f"({relative_path})" in line:
            existing_lines[index] = entry_line
            break
    else:
        existing_lines.append(entry_line)
    atomic_write_text(entrypoint, "\n".join(existing_lines).rstrip() + "\n")


def _iter_legacy_memory_files(legacy_dir: Path) -> list[tuple[Path, str]]:
    entrypoint = legacy_dir / "MEMORY.md"
    indexed: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    if entrypoint.exists():
        for line in entrypoint.read_text(encoding="utf-8").splitlines():
            match = _MEMORY_INDEX_LINE_RE.match(line)
            if match is None:
                continue
            path = (legacy_dir / match.group("target").strip()).resolve()
            if path.name == "MEMORY.md" or not path.exists() or path in seen:
                continue
            indexed.append((path, match.group("title").strip() or path.stem))
            seen.add(path)

    for path in legacy_dir.rglob("*.md"):
        resolved = path.resolve()
        if path.name == "MEMORY.md" or resolved in seen:
            continue
        indexed.append((resolved, path.stem))
        seen.add(resolved)
    return indexed


def _allocate_merged_legacy_path(memory_root: Path, source_path: Path) -> Path:
    entries_dir = memory_root / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    candidate = entries_dir / source_path.name
    if not candidate.exists():
        return candidate
    stem = source_path.stem
    suffix = source_path.suffix
    counter = 2
    while True:
        alt = entries_dir / f"{stem}_{counter}{suffix}"
        if not alt.exists():
            return alt
        counter += 1


def _merge_single_legacy_project_memory_dir(legacy_dir: Path, memory_root: Path) -> None:
    if not legacy_dir.exists() or legacy_dir == memory_root:
        return

    target_entrypoint = memory_root / "MEMORY.md"
    for source_path, title in _iter_legacy_memory_files(legacy_dir):
        destination = _allocate_merged_legacy_path(memory_root, source_path)
        destination.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        source_path.unlink(missing_ok=True)
        _append_index_entry(
            target_entrypoint,
            title=title,
            relative_path=destination.relative_to(memory_root).as_posix(),
        )

    for child in sorted(legacy_dir.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            with contextlib.suppress(OSError):
                child.rmdir()
    with contextlib.suppress(OSError):
        legacy_dir.rmdir()


def _merge_legacy_project_memory_dir(path: Path, memory_root: Path) -> None:
    leaf = _project_memory_leaf(path)
    candidates = [memory_root / leaf, get_data_dir() / "memory" / leaf]
    seen: set[Path] = set()
    for legacy_dir in candidates:
        resolved = legacy_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _merge_single_legacy_project_memory_dir(legacy_dir, memory_root)


def get_project_memory_dir(cwd: str | Path) -> Path:
    """Return the persistent memory directory for a project."""
    path = Path(cwd).resolve()
    memory_root = get_memory_store_dir()
    if memory_store_uses_shared_root():
        memory_root.mkdir(parents=True, exist_ok=True)
        _merge_legacy_project_memory_dir(path, memory_root)
        return memory_root

    leaf = _project_memory_leaf(path)
    memory_dir = memory_root / leaf
    legacy_dir = get_data_dir() / "memory" / leaf

    if not memory_dir.exists() and legacy_dir.exists() and legacy_dir != memory_dir:
        legacy_dir.rename(memory_dir)

    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def get_project_memory_entries_dir(cwd: str | Path) -> Path:
    """Return the directory that stores child memory entry files."""
    entries_dir = get_project_memory_dir(cwd) / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    return entries_dir


def get_memory_entrypoint(cwd: str | Path) -> Path:
    """Return the project memory entrypoint file."""
    return get_project_memory_dir(cwd) / "MEMORY.md"


def get_memory_metadata_index(cwd: str | Path) -> Path:
    """Return the hidden metadata index used by the memory store."""
    return get_project_memory_dir(cwd) / ".memory.index.json"
