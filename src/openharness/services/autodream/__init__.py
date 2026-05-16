"""Automatic memory consolidation (auto-dream)."""

from openharness.services.autodream.backup import (
    create_memory_backup,
    diff_memory_dirs,
    format_memory_diff,
    latest_memory_backup,
    restore_memory_backup,
)
from openharness.services.autodream.lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    record_consolidation,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from openharness.services.autodream.prompt import build_consolidation_prompt
from openharness.services.autodream.service import execute_auto_dream, start_dream_now

__all__ = [
    "build_consolidation_prompt",
    "create_memory_backup",
    "diff_memory_dirs",
    "execute_auto_dream",
    "format_memory_diff",
    "latest_memory_backup",
    "list_sessions_touched_since",
    "read_last_consolidated_at",
    "record_consolidation",
    "restore_memory_backup",
    "rollback_consolidation_lock",
    "start_dream_now",
    "try_acquire_consolidation_lock",
]
