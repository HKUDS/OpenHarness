"""Scan project memory files."""

from __future__ import annotations

import json
from pathlib import Path
import re

from openharness.memory.provider import get_memory_provider
from openharness.memory import paths as memory_paths
from openharness.memory.types import MemoryHeader
from openharness.utils.fs import atomic_write_text


_MEMORY_INDEX_VERSION = 1
_MEMORY_INDEX_LINE_RE = re.compile(r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)\s*$")


def _load_index_records(cwd: str | Path) -> dict[str, dict[str, object]]:
    index_path = memory_paths.get_memory_metadata_index(cwd)
    if not index_path.exists():
        return {}

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}

    if not isinstance(payload, dict) or payload.get("version") != _MEMORY_INDEX_VERSION:
        return {}
    records = payload.get("entries")
    if not isinstance(records, list):
        return {}

    indexed: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        relative_path = record.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            continue
        indexed[relative_path] = record
    return indexed


def _scan_memory_files_from_disk(cwd: str | Path) -> list[MemoryHeader]:
    """Build memory headers from MEMORY.md and cached metadata without opening child files."""
    memory_dir = memory_paths.get_project_memory_dir(cwd)
    entrypoint = memory_paths.get_memory_entrypoint(cwd)
    if not entrypoint.exists():
        return []

    try:
        entrypoint_lines = entrypoint.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    indexed_records = _load_index_records(cwd)
    resolved_memory_dir = memory_dir.resolve()
    headers: list[MemoryHeader] = []
    seen_paths: set[Path] = set()
    for line in entrypoint_lines:
        match = _MEMORY_INDEX_LINE_RE.match(line)
        if match is None:
            continue
        relative_path = match.group("target").strip()
        title = match.group("title").strip()
        if not relative_path:
            continue
        path = (memory_dir / relative_path).resolve()
        try:
            path.relative_to(resolved_memory_dir)
        except ValueError:
            continue
        if path in seen_paths or path.name == "MEMORY.md":
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        record = indexed_records.get(relative_path, {})
        headers.append(
            MemoryHeader(
                path=path,
                title=title or str(record.get("title") or path.stem),
                description=str(record.get("description") or ""),
                modified_at=stat.st_mtime,
                memory_type=str(record.get("memory_type") or ""),
                memory_key=str(record.get("memory_key") or ""),
                body_preview=str(record.get("body_preview") or ""),
            )
        )
        seen_paths.add(path)
    headers.sort(key=lambda item: item.modified_at, reverse=True)
    return headers


def _header_to_index_record(memory_dir: Path, header: MemoryHeader) -> dict[str, object]:
    stat = header.path.stat()
    return {
        "relative_path": header.path.relative_to(memory_dir).as_posix(),
        "title": header.title,
        "description": header.description,
        "memory_type": header.memory_type,
        "memory_key": header.memory_key,
        "body_preview": header.body_preview,
        "modified_at": header.modified_at,
        "modified_at_ns": stat.st_mtime_ns,
    }


def write_memory_index(cwd: str | Path, headers: list[MemoryHeader]) -> None:
    """Persist a machine-readable metadata index for memory headers."""
    memory_dir = memory_paths.get_project_memory_dir(cwd)
    index_path = memory_paths.get_memory_metadata_index(cwd)
    payload = {
        "version": _MEMORY_INDEX_VERSION,
        "entries": [_header_to_index_record(memory_dir, header) for header in headers],
    }
    atomic_write_text(index_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def rebuild_memory_index(cwd: str | Path) -> list[MemoryHeader]:
    """Rebuild and persist the metadata index from MEMORY.md plus cached metadata."""
    headers = _scan_memory_files_from_disk(cwd)
    write_memory_index(cwd, headers)
    return headers


def _load_indexed_headers(cwd: str | Path) -> list[MemoryHeader] | None:
    headers = _scan_memory_files_from_disk(cwd)
    if not headers:
        return None
    return headers


def scan_memory_files_in_file_store(cwd: str | Path, *, max_files: int | None = 50) -> list[MemoryHeader]:
    """Return memory headers sorted by newest first."""
    headers = _load_indexed_headers(cwd)
    if headers is None:
        headers = rebuild_memory_index(cwd)
    if max_files is None:
        return headers
    return headers[:max_files]


def scan_memory_files(cwd: str | Path, *, max_files: int | None = 50) -> list[MemoryHeader]:
    """Return memory headers from the active memory provider."""
    return get_memory_provider(cwd).scan_memory_files(cwd, max_files=max_files)


def _parse_memory_file(path: Path, content: str) -> MemoryHeader:
    """Parse a memory file, extracting YAML frontmatter when present."""
    lines = content.splitlines()
    title = path.stem
    description = ""
    memory_type = ""
    memory_key = ""
    body_start = 0

    # Parse YAML frontmatter (--- ... ---)
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                for fm_line in lines[1:i]:
                    key, _, value = fm_line.partition(":")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if not value:
                        continue
                    if key == "name":
                        title = value
                    elif key == "description":
                        description = value
                    elif key == "type":
                        memory_type = value
                    elif key == "key":
                        memory_key = value
                body_start = i + 1
                break

    # Fallback: first non-empty, non-frontmatter line as description
    desc_line_idx: int | None = None
    if not description:
        for idx, line in enumerate(lines[body_start:body_start + 10], body_start):
            stripped = line.strip()
            if stripped and stripped != "---" and not stripped.startswith("#"):
                description = stripped[:200]
                desc_line_idx = idx
                break

    # Build body preview from content after frontmatter, excluding the
    # line already used as description so search scoring stays consistent.
    body_lines = [
        line.strip()
        for idx, line in enumerate(lines[body_start:], body_start)
        if line.strip()
        and not line.strip().startswith("#")
        and idx != desc_line_idx
    ]
    body_preview = " ".join(body_lines)[:300]

    return MemoryHeader(
        path=path,
        title=title,
        description=description,
        modified_at=path.stat().st_mtime,
        memory_type=memory_type,
        memory_key=memory_key,
        body_preview=body_preview,
    )
