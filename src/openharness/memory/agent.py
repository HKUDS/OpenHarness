"""Agent-scoped memory paths and snapshots."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Literal

from openharness.config.paths import get_data_dir
from openharness.memory.paths import get_project_memory_dir

AgentMemoryScope = Literal["user", "project", "local"]

MEMORY_INDEX = "MEMORY.md"
SNAPSHOT_DIR_NAME = "agent-memory-snapshots"


def sanitize_agent_type(agent_type: str) -> str:
    """Return a path-safe agent type."""

    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", agent_type.strip()).strip("._") or "default"


def get_agent_memory_dir(cwd: str | Path, agent_type: str, scope: AgentMemoryScope) -> Path:
    """Return an agent memory vault for the requested scope."""

    safe = sanitize_agent_type(agent_type)
    if scope == "project":
        return get_project_memory_dir(cwd) / "agent" / safe
    if scope == "local":
        return Path(cwd).resolve() / ".openharness" / "agent-memory-local" / safe
    return get_data_dir() / "agent-memory" / safe


def ensure_agent_memory_vault(cwd: str | Path, agent_type: str, scope: AgentMemoryScope) -> Path:
    """Create and return an agent-scoped memory vault."""

    memory_dir = get_agent_memory_dir(cwd, agent_type, scope)
    memory_dir.mkdir(parents=True, exist_ok=True)
    entrypoint = memory_dir / MEMORY_INDEX
    if not entrypoint.exists():
        entrypoint.write_text("# Memory Index\n", encoding="utf-8")
    return memory_dir


def get_agent_memory_entrypoint(cwd: str | Path, agent_type: str, scope: AgentMemoryScope) -> Path:
    """Return an agent memory ``MEMORY.md`` path."""

    return ensure_agent_memory_vault(cwd, agent_type, scope) / MEMORY_INDEX


def get_agent_snapshot_dir(cwd: str | Path, agent_type: str) -> Path:
    """Return the project snapshot directory for an agent type."""

    return Path(cwd).resolve() / ".openharness" / SNAPSHOT_DIR_NAME / sanitize_agent_type(agent_type)


def initialize_agent_memory_from_snapshot(
    cwd: str | Path,
    agent_type: str,
    scope: AgentMemoryScope,
    *,
    replace: bool = False,
) -> Path | None:
    """Initialize local agent memory from a project snapshot if present."""

    snapshot_dir = get_agent_snapshot_dir(cwd, agent_type)
    if not snapshot_dir.exists():
        return None
    target = ensure_agent_memory_vault(cwd, agent_type, scope)
    if replace and target.exists():
        shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
    for src in snapshot_dir.rglob("*.md"):
        rel = src.relative_to(snapshot_dir)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if replace or not dest.exists() or _is_default_agent_index(dest):
            shutil.copy2(src, dest)
    return target


def _is_default_agent_index(path: Path) -> bool:
    if path.name != MEMORY_INDEX or not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return text.startswith("# Memory Index\n")
