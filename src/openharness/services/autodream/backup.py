"""Backup, diff, and rollback helpers for auto-dream memory directories."""

from __future__ import annotations

import filecmp
import shutil
import time
from pathlib import Path

from openharness.config.paths import get_data_dir


def default_backup_root(memory_dir: str | Path, *, app_label: str = "openharness") -> Path:
    """Return the backup root for a memory directory."""

    memory_dir = Path(memory_dir).expanduser().resolve()
    if ".ohmo" in memory_dir.parts:
        try:
            idx = memory_dir.parts.index(".ohmo")
            return Path(*memory_dir.parts[: idx + 1]) / "backups"
        except ValueError:
            pass
    safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in app_label).strip("-")
    return get_data_dir() / "memory-backups" / (safe_label or "openharness")


def create_memory_backup(
    memory_dir: str | Path,
    *,
    backup_root: str | Path | None = None,
    app_label: str = "openharness",
) -> Path:
    """Create a timestamped copy of ``memory_dir`` and return the backup path."""

    memory_dir = Path(memory_dir).expanduser().resolve()
    root = Path(backup_root).expanduser().resolve() if backup_root is not None else default_backup_root(memory_dir, app_label=app_label)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("memory-%Y%m%d-%H%M%S")
    backup = root / timestamp
    suffix = 1
    while backup.exists():
        suffix += 1
        backup = root / f"{timestamp}-{suffix}"
    if memory_dir.exists():
        shutil.copytree(memory_dir, backup, ignore=shutil.ignore_patterns(".consolidate-lock"))
    else:
        backup.mkdir(parents=True)
    return backup


def diff_memory_dirs(before: str | Path, after: str | Path) -> dict[str, list[str]]:
    """Return added/removed/changed file names between two memory dirs."""

    before = Path(before).expanduser().resolve()
    after = Path(after).expanduser().resolve()
    before_files = {p.name: p for p in before.glob("*.md")} if before.exists() else {}
    after_files = {p.name: p for p in after.glob("*.md")} if after.exists() else {}
    added = sorted(set(after_files) - set(before_files))
    removed = sorted(set(before_files) - set(after_files))
    changed = sorted(
        name
        for name in set(before_files) & set(after_files)
        if not filecmp.cmp(before_files[name], after_files[name], shallow=False)
    )
    return {"added": added, "removed": removed, "changed": changed}


def format_memory_diff(diff: dict[str, list[str]]) -> str:
    """Format a compact memory diff summary."""

    lines: list[str] = []
    for label in ("added", "changed", "removed"):
        values = diff.get(label, [])
        if values:
            lines.append(f"{label}: " + ", ".join(values))
    return "\n".join(lines) if lines else "no markdown file changes"


def latest_memory_backup(memory_dir: str | Path, *, app_label: str = "openharness") -> Path | None:
    """Return the latest backup for a memory directory, if any."""

    root = default_backup_root(memory_dir, app_label=app_label)
    if not root.exists():
        return None
    backups = [path for path in root.iterdir() if path.is_dir() and path.name.startswith("memory-")]
    if not backups:
        return None
    return max(backups, key=lambda path: path.stat().st_mtime)


def restore_memory_backup(backup_dir: str | Path, memory_dir: str | Path) -> None:
    """Restore memory_dir from a backup directory."""

    backup_dir = Path(backup_dir).expanduser().resolve()
    memory_dir = Path(memory_dir).expanduser().resolve()
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup not found: {backup_dir}")
    tmp = memory_dir.with_name(f".{memory_dir.name}.restore-tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(backup_dir, tmp)
    if memory_dir.exists():
        shutil.rmtree(memory_dir)
    tmp.rename(memory_dir)
