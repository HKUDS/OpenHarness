"""Session persistence for ``ohmo``."""

from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage
from openharness.services.session_backend import SessionBackend
from openharness.services.session_storage import _persistable_tool_metadata

from ohmo.workspace import get_sessions_dir


def get_session_dir(workspace: str | Path | None = None) -> Path:
    """Return the ohmo sessions directory."""
    session_dir = get_sessions_dir(workspace)
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _session_key_token(session_key: str) -> str:
    return hashlib.sha1(session_key.encode("utf-8")).hexdigest()[:12]


def _session_key_latest_path(workspace: str | Path | None, session_key: str) -> Path:
    session_dir = get_session_dir(workspace)
    token = _session_key_token(session_key)
    return session_dir / f"latest-{token}.json"


def save_session_snapshot(
    *,
    cwd: str | Path,
    workspace: str | Path | None = None,
    model: str,
    system_prompt: str,
    messages: list[ConversationMessage],
    usage: UsageSnapshot,
    session_id: str | None = None,
    session_key: str | None = None,
    tool_metadata: dict[str, object] | None = None,
) -> Path:
    """Persist the latest ohmo session snapshot."""
    session_dir = get_session_dir(workspace)
    sid = session_id or uuid4().hex[:12]
    now = time.time()
    summary = ""
    for msg in messages:
        if msg.role == "user" and msg.text.strip():
            summary = msg.text.strip()[:80]
            break

    payload = {
        "app": "ohmo",
        "session_id": sid,
        "session_key": session_key,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "system_prompt": system_prompt,
        "messages": [message.model_dump(mode="json") for message in messages],
        "usage": usage.model_dump(),
        "tool_metadata": _persistable_tool_metadata(tool_metadata),
        "created_at": now,
        "summary": summary,
        "message_count": len(messages),
    }
    data = json.dumps(payload, indent=2) + "\n"
    latest_path = session_dir / "latest.json"
    latest_path.write_text(data, encoding="utf-8")
    if session_key:
        _session_key_latest_path(workspace, session_key).write_text(data, encoding="utf-8")
    session_path = session_dir / f"session-{sid}.json"
    session_path.write_text(data, encoding="utf-8")
    return latest_path


def load_latest(workspace: str | Path | None = None) -> dict[str, Any] | None:
    path = get_session_dir(workspace) / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_for_session_key(workspace: str | Path | None, session_key: str) -> dict[str, Any] | None:
    path = _session_key_latest_path(workspace, session_key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def list_snapshots(workspace: str | Path | None = None, limit: int = 20) -> list[dict[str, Any]]:
    session_dir = get_session_dir(workspace)
    sessions: list[dict[str, Any]] = []
    for path in sorted(session_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sessions.append(
            {
                "session_id": data.get("session_id", path.stem.replace("session-", "")),
                "summary": data.get("summary", ""),
                "message_count": data.get("message_count", len(data.get("messages", []))),
                "model": data.get("model", ""),
                "created_at": data.get("created_at", path.stat().st_mtime),
            }
        )
        if len(sessions) >= limit:
            break
    return sessions


def load_by_id(workspace: str | Path | None, session_id: str) -> dict[str, Any] | None:
    path = get_session_dir(workspace) / f"session-{session_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    latest = load_latest(workspace)
    if latest and (latest.get("session_id") == session_id or session_id == "latest"):
        return latest
    return None


def export_session_markdown(
    *,
    cwd: str | Path,
    workspace: str | Path | None = None,
    messages: list[ConversationMessage],
) -> Path:
    path = get_session_dir(workspace) / "transcript.md"
    parts = ["# ohmo Session Transcript"]
    for message in messages:
        parts.append(f"\n## {message.role.capitalize()}\n")
        text = message.text.strip()
        if text:
            parts.append(text)
    path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    return path


class OhmoSessionBackend(SessionBackend):
    """Session backend rooted in ``.ohmo/sessions``."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self._workspace = workspace

    def get_session_dir(self, cwd: str | Path) -> Path:
        return get_session_dir(self._workspace)

    def save_snapshot(
        self,
        *,
        cwd: str | Path,
        model: str,
        system_prompt: str,
        messages: list[ConversationMessage],
        usage: UsageSnapshot,
        session_id: str | None = None,
        session_key: str | None = None,
        tool_metadata: dict[str, object] | None = None,
    ) -> Path:
        return save_session_snapshot(
            cwd=cwd,
            workspace=self._workspace,
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            usage=usage,
            session_id=session_id,
            session_key=session_key,
            tool_metadata=tool_metadata,
        )

    def load_latest(self, cwd: str | Path) -> dict[str, Any] | None:
        return load_latest(self._workspace)

    def list_snapshots(self, cwd: str | Path, limit: int = 20) -> list[dict[str, Any]]:
        return list_snapshots(self._workspace, limit=limit)

    def load_by_id(self, cwd: str | Path, session_id: str) -> dict[str, Any] | None:
        return load_by_id(self._workspace, session_id)

    def load_latest_for_session_key(self, session_key: str) -> dict[str, Any] | None:
        return load_latest_for_session_key(self._workspace, session_key)

    def export_markdown(
        self,
        *,
        cwd: str | Path,
        messages: list[ConversationMessage],
    ) -> Path:
        return export_session_markdown(cwd=cwd, workspace=self._workspace, messages=messages)
