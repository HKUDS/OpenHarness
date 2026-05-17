"""File-backed session memory for compact continuity."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from openharness.config.paths import get_data_dir
from openharness.engine.messages import ConversationMessage, ToolResultBlock
from openharness.services.token_estimation import estimate_tokens
from openharness.utils.fs import atomic_write_text

MAX_SESSION_MEMORY_CHARS = 12_000
MAX_RECENT_LINES = 80


def get_session_memory_dir(cwd: str | Path) -> Path:
    """Return the project session-memory directory."""

    root = Path(cwd).resolve()
    digest = sha1(str(root).encode("utf-8")).hexdigest()[:12]
    path = get_data_dir() / "session-memory" / f"{root.name}-{digest}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_session_memory_path(cwd: str | Path, session_id: str | None = None) -> Path:
    """Return the markdown session-memory path."""

    safe_session = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (session_id or "default"))
    return get_session_memory_dir(cwd) / f"{safe_session or 'default'}.md"


def prepare_session_memory_metadata(
    cwd: str | Path,
    tool_metadata: dict[str, object],
    *,
    session_id: str | None = None,
) -> Path:
    """Ensure metadata points compaction to the session-memory file."""

    sid = session_id or str(tool_metadata.get("session_id") or "default")
    path = get_session_memory_path(cwd, sid)
    tool_metadata["session_memory_path"] = str(path)
    return path


def get_session_memory_content(path: str | Path | None) -> str:
    """Read session memory content if available."""

    if not path:
        return ""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return ""
    try:
        return candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def update_session_memory_file(
    cwd: str | Path,
    messages: list[ConversationMessage],
    *,
    tool_metadata: dict[str, object] | None = None,
    session_id: str | None = None,
) -> Path:
    """Update the deterministic session-memory checkpoint."""

    path = prepare_session_memory_metadata(cwd, tool_metadata or {}, session_id=session_id)
    body = build_session_memory_document(messages, tool_metadata=tool_metadata)
    atomic_write_text(path, body)
    return path


def build_session_memory_document(
    messages: list[ConversationMessage],
    *,
    tool_metadata: dict[str, object] | None = None,
) -> str:
    """Build a compact markdown checkpoint for the current session."""

    state = tool_metadata.get("task_focus_state") if isinstance(tool_metadata, dict) else None
    goal = ""
    next_step = ""
    verified: list[str] = []
    artifacts: list[str] = []
    if isinstance(state, dict):
        goal = str(state.get("goal") or "").strip()
        next_step = str(state.get("next_step") or "").strip()
        verified = [str(item).strip() for item in state.get("verified_state", []) if str(item).strip()]
        artifacts = [str(item).strip() for item in state.get("active_artifacts", []) if str(item).strip()]

    lines = ["# Session Memory", ""]
    lines.extend(["## Current State", goal or "(no current goal recorded)", ""])
    if next_step:
        lines.extend(["## Next Step", next_step, ""])
    if verified:
        lines.extend(["## Verified Work", *[f"- {item}" for item in verified[-10:]], ""])
    if artifacts:
        lines.extend(["## Active Artifacts", *[f"- {item}" for item in artifacts[-10:]], ""])
    lines.extend(["## Recent Conversation", *_recent_message_lines(messages), ""])
    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_SESSION_MEMORY_CHARS:
        text = text[:MAX_SESSION_MEMORY_CHARS].rsplit("\n", 1)[0]
        text += "\n\n> Session memory was truncated to stay within budget.\n"
    return text


def session_memory_to_compact_text(content: str) -> str:
    """Prepare persisted session memory for insertion across compact boundaries."""

    stripped = content.strip()
    if not stripped:
        return ""
    if estimate_tokens(stripped) > 4_000:
        stripped = stripped[:MAX_SESSION_MEMORY_CHARS].rsplit("\n", 1)[0]
    return "Session memory checkpoint from earlier in this conversation:\n" + stripped


def _recent_message_lines(messages: list[ConversationMessage]) -> list[str]:
    lines: list[str] = []
    for message in messages[-MAX_RECENT_LINES:]:
        line = _summarize_message(message)
        if line:
            lines.append(f"- {line}")
    return lines or ["- (no recent messages)"]


def _summarize_message(message: ConversationMessage) -> str:
    text = " ".join(message.text.split())
    if text:
        return f"{message.role}: {text[:220]}"
    if message.tool_uses:
        return f"{message.role}: tool calls -> {', '.join(block.name for block in message.tool_uses[:6])}"
    if any(isinstance(block, ToolResultBlock) for block in message.content):
        return f"{message.role}: tool results returned"
    return f"{message.role}: [non-text content]"
