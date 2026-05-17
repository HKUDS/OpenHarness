"""Helpers for managing memory files."""

from __future__ import annotations

from pathlib import Path
from re import sub

from openharness.memory.paths import get_memory_entrypoint, get_project_memory_dir
from openharness.memory.scan import scan_memory_files
from openharness.memory.schema import (
    SCHEMA_VERSION,
    compute_memory_signature,
    first_content_line,
    format_datetime,
    generate_memory_id,
    memory_metadata_from_path,
    render_memory_file,
    split_memory_file,
    coerce_int,
    utc_now,
)
from openharness.utils.file_lock import exclusive_file_lock
from openharness.utils.fs import atomic_write_text


def _memory_lock_path(cwd: str | Path) -> Path:
    return get_project_memory_dir(cwd) / ".memory.lock"


def list_memory_files(cwd: str | Path) -> list[Path]:
    """List memory markdown files for the project."""
    return sorted(header.path for header in scan_memory_files(cwd, max_files=None))


def add_memory_entry(cwd: str | Path, title: str, content: str) -> Path:
    """Create or refresh a memory file and append it to MEMORY.md."""
    memory_dir = get_project_memory_dir(cwd)
    slug = sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_") or "memory"
    with exclusive_file_lock(_memory_lock_path(cwd)):
        memory_type = "project"
        category = "knowledge"
        body = content.strip() + "\n"
        signature = compute_memory_signature(body, memory_type, category)
        existing = scan_memory_files(
            cwd,
            max_files=None,
            include_disabled=True,
            include_expired=True,
        )
        duplicate = next(
            (header for header in existing if _effective_signature(header.path, header.signature) == signature),
            None,
        )
        path = duplicate.path if duplicate is not None else _next_memory_path(memory_dir, slug)
        now = utc_now()
        now_text = format_datetime(now)
        if path.exists():
            metadata, old_body, _, _ = split_memory_file(path.read_text(encoding="utf-8"))
            metadata = memory_metadata_from_path(
                path,
                metadata,
                old_body,
                now=now,
                source=str(metadata.get("source") or "manual"),
            )
            created_at = str(metadata.get("created_at") or now_text)
            memory_id = str(metadata.get("id") or generate_memory_id(now))
        else:
            metadata = {}
            created_at = now_text
            memory_id = generate_memory_id(now)

        metadata.update(
            {
                "schema_version": SCHEMA_VERSION,
                "id": memory_id,
                "name": title.strip(),
                "description": first_content_line(body) or title.strip(),
                "type": str(metadata.get("type") or memory_type),
                "category": str(metadata.get("category") or category),
                "importance": max(coerce_int(metadata.get("importance"), default=0), 1),
                "source": "manual",
                "signature": signature,
                "created_at": created_at,
                "updated_at": now_text,
                "ttl_days": metadata.get("ttl_days"),
                "disabled": False,
                "supersedes": metadata.get("supersedes") or [],
            }
        )
        atomic_write_text(path, render_memory_file(metadata, body))

        entrypoint = get_memory_entrypoint(cwd)
        index_text = entrypoint.read_text(encoding="utf-8") if entrypoint.exists() else "# Memory Index\n"
        if path.name not in index_text:
            index_text = index_text.rstrip() + f"\n- [{title}]({path.name})\n"
            atomic_write_text(entrypoint, index_text)
    return path


def remove_memory_entry(cwd: str | Path, name: str) -> bool:
    """Soft-delete a memory file and remove its index entry."""
    matches = [
        header
        for header in scan_memory_files(
            cwd,
            max_files=None,
            include_disabled=True,
            include_expired=True,
        )
        if name in {header.path.stem, header.path.name, header.title, header.id}
    ]
    if not matches:
        return False
    header = matches[0]
    if header.disabled:
        return False
    path = header.path
    with exclusive_file_lock(_memory_lock_path(cwd)):
        if path.exists():
            content = path.read_text(encoding="utf-8")
            metadata, body, _, _ = split_memory_file(content)
            metadata = memory_metadata_from_path(path, metadata, body, source="manual")
            metadata["disabled"] = True
            metadata["updated_at"] = format_datetime(utc_now())
            atomic_write_text(path, render_memory_file(metadata, body))

        entrypoint = get_memory_entrypoint(cwd)
        if entrypoint.exists():
            lines = [
                line
                for line in entrypoint.read_text(encoding="utf-8").splitlines()
                if path.name not in line
            ]
            atomic_write_text(entrypoint, "\n".join(lines).rstrip() + "\n")
    return True


def _next_memory_path(memory_dir: Path, slug: str) -> Path:
    path = memory_dir / f"{slug}.md"
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = memory_dir / f"{slug}_{index}.md"
        if not candidate.exists():
            return candidate
        index += 1


def _effective_signature(path: Path, existing_signature: str) -> str:
    if existing_signature:
        return existing_signature
    try:
        metadata, body, _, _ = split_memory_file(path.read_text(encoding="utf-8"))
    except OSError:
        return ""
    memory_type = str(metadata.get("type") or "project")
    category = str(metadata.get("category") or "knowledge")
    return compute_memory_signature(body, memory_type, category)
