"""Persistent metadata for ohmo-managed chat groups."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from ohmo.workspace import get_groups_dir


@dataclass(frozen=True)
class ManagedGroupRecord:
    """Metadata for a chat group created and managed by ohmo."""

    channel: str
    chat_id: str
    owner_open_id: str
    name: str
    created_at: str
    cwd: str | None = None
    repo: str | None = None
    binding_status: str = "pending_agent"
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_group_name(raw: str) -> str:
    """Return a safe Feishu group name from command text."""
    name = " ".join(str(raw).strip().split())
    if not name:
        raise ValueError("Group name is required.")
    if len(name) > 100:
        raise ValueError("Group name is too long; keep it within 100 characters.")
    return name


def group_record_path(
    *,
    workspace: str | Path | None,
    channel: str,
    chat_id: str,
) -> Path:
    safe_chat_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(chat_id)).strip("._") or "unknown"
    return get_groups_dir(workspace) / channel / f"{safe_chat_id}.json"


def save_managed_group_record(
    *,
    workspace: str | Path | None,
    channel: str,
    chat_id: str,
    owner_open_id: str,
    name: str,
    cwd: str | None = None,
    repo: str | None = None,
    binding_status: str = "pending_agent",
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Persist metadata for an ohmo-managed group and return the path."""
    record = ManagedGroupRecord(
        channel=channel,
        chat_id=chat_id,
        owner_open_id=owner_open_id,
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        cwd=normalize_cwd(cwd) if cwd else None,
        repo=repo,
        binding_status=binding_status,
        metadata=metadata or {},
    )
    path = group_record_path(workspace=workspace, channel=channel, chat_id=chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_managed_group_record(
    *,
    workspace: str | Path | None,
    channel: str,
    chat_id: str,
) -> dict[str, Any] | None:
    """Load metadata for an ohmo-managed group if present."""
    path = group_record_path(workspace=workspace, channel=channel, chat_id=chat_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_cwd(cwd: str | Path) -> str:
    """Normalize a cwd binding."""
    return str(Path(cwd).expanduser().resolve())
