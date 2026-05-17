"""Migration utilities for schema-v1 memory frontmatter."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from openharness.memory.paths import get_project_memory_dir
from openharness.memory.schema import (
    memory_metadata_from_path,
    render_memory_file,
    split_memory_file,
    utc_now,
)
from openharness.utils.fs import atomic_write_text


@dataclass(frozen=True)
class MigrationSummary:
    """Summary returned by a memory schema migration run."""

    scanned: int
    changed: int
    unchanged: int
    failed: int
    dry_run: bool
    backup_dir: str
    changed_files: tuple[str, ...]
    failed_files: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def migrate_memory(
    cwd: str | Path,
    *,
    memory_dir: str | Path | None = None,
    default_type: str = "project",
    default_category: str = "knowledge",
    apply: bool = False,
) -> MigrationSummary:
    """Backfill schema-v1 frontmatter for top-level memory markdown files."""

    root = Path(memory_dir).expanduser().resolve() if memory_dir is not None else get_project_memory_dir(cwd)
    root.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in root.glob("*.md") if path.name != "MEMORY.md")
    changed_payloads: list[tuple[Path, str]] = []
    failed_files: list[str] = []
    seen_ids: set[str] = set()
    now = utc_now()

    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
            metadata, body, _, _ = split_memory_file(content)
            migrated = memory_metadata_from_path(
                path,
                metadata,
                body,
                now=now,
                source="migration",
                default_type=default_type,
                default_category=default_category,
                seen_ids=seen_ids,
            )
            rendered = render_memory_file(migrated, body)
            if rendered != content:
                changed_payloads.append((path, rendered))
        except OSError:
            failed_files.append(path.name)

    backup_dir = ""
    if apply and changed_payloads:
        backup_path = _create_migration_backup(root)
        backup_dir = str(backup_path)
        for path, rendered in changed_payloads:
            atomic_write_text(path, rendered)

    changed_files = tuple(path.name for path, _ in changed_payloads)
    return MigrationSummary(
        scanned=len(files),
        changed=len(changed_payloads),
        unchanged=len(files) - len(changed_payloads) - len(failed_files),
        failed=len(failed_files),
        dry_run=not apply,
        backup_dir=backup_dir,
        changed_files=changed_files,
        failed_files=tuple(failed_files),
    )


def main(argv: list[str] | None = None) -> int:
    """Command-line entrypoint for one-off memory migrations."""

    parser = argparse.ArgumentParser(description="Backfill OpenHarness memory schema metadata.")
    parser.add_argument("--cwd", default=".", help="Project cwd whose memory store should be migrated.")
    parser.add_argument("--memory-dir", default=None, help="Explicit memory directory to migrate.")
    parser.add_argument("--default-type", default="project", help="Type for legacy files without one.")
    parser.add_argument("--default-category", default="knowledge", help="Category for legacy files without one.")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change.")
    parser.add_argument("--apply", action="store_true", help="Write migrated files and create a backup.")
    args = parser.parse_args(argv)
    if args.dry_run == args.apply:
        parser.error("pass exactly one of --dry-run or --apply")
    summary = migrate_memory(
        args.cwd,
        memory_dir=args.memory_dir,
        default_type=args.default_type,
        default_category=args.default_category,
        apply=args.apply,
    )
    print(json.dumps(summary.as_dict(), indent=2, ensure_ascii=False))
    return 0


def _create_migration_backup(memory_dir: Path) -> Path:
    timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
    backup_dir = memory_dir / "backups" / f"migration-{timestamp}"
    suffix = 2
    while backup_dir.exists():
        backup_dir = memory_dir / "backups" / f"migration-{timestamp}-{suffix}"
        suffix += 1
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in sorted(memory_dir.glob("*.md")):
        shutil.copy2(path, backup_dir / path.name)
    usage_index = memory_dir / "usage_index.json"
    if usage_index.exists():
        shutil.copy2(usage_index, backup_dir / usage_index.name)
    return backup_dir


if __name__ == "__main__":
    raise SystemExit(main())
