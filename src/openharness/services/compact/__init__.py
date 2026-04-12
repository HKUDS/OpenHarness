"""Conversation compaction — microcompact and full LLM-based summarization.

Faithfully translated from Claude Code's compaction system:
- Microcompact: clear old tool result content to reduce token count cheaply
- Full compact: call the LLM to produce a structured summary of older messages
- Auto-compact: trigger compaction automatically when token count exceeds threshold
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal
from uuid import uuid4

from openharness.engine.messages import (
    ConversationMessage,
    ContentBlock,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from openharness.engine.stream_events import CompactProgressEvent
from openharness.hooks import HookEvent, HookExecutor
from openharness.services.token_estimation import estimate_tokens

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (from Claude Code microCompact.ts / autoCompact.ts)
# ---------------------------------------------------------------------------

COMPACTABLE_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "bash",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
    "edit_file",
    "write_file",
})

TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

# Auto-compact thresholds
AUTOCOMPACT_BUFFER_TOKENS = 13_000
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3
COMPACT_TIMEOUT_SECONDS = 25
MAX_COMPACT_STREAMING_RETRIES = 2
MAX_PTL_RETRIES = 3
SESSION_MEMORY_KEEP_RECENT = 12
SESSION_MEMORY_MAX_LINES = 48
SESSION_MEMORY_MAX_CHARS = 4_000
CONTEXT_COLLAPSE_TEXT_CHAR_LIMIT = 2_400
CONTEXT_COLLAPSE_HEAD_CHARS = 900
CONTEXT_COLLAPSE_TAIL_CHARS = 500
MAX_COMPACT_ATTACHMENTS = 6
MAX_DISCOVERED_TOOLS = 12

# Microcompact defaults
DEFAULT_KEEP_RECENT = 5
DEFAULT_GAP_THRESHOLD_MINUTES = 60

# Token estimation padding (conservative)
TOKEN_ESTIMATION_PADDING = 4 / 3

# Default context windows per model family
_DEFAULT_CONTEXT_WINDOW = 200_000
PTL_RETRY_MARKER = "[earlier conversation truncated for compaction retry]"
ERROR_MESSAGE_INCOMPLETE_RESPONSE = "Compaction interrupted before a complete summary was returned."

CompactTrigger = Literal["auto", "manual", "reactive"]
CompactProgressCallback = Callable[[CompactProgressEvent], Awaitable[None]]
CompactionKind = Literal["full", "session_memory"]


@dataclass
class CompactAttachment:
    """Structured compact asset carried across a compaction boundary."""

    kind: str
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompactionResult:
    """Structured compaction result, inspired by Claude Code's result shape."""

    trigger: CompactTrigger
    compact_kind: CompactionKind
    boundary_marker: ConversationMessage
    summary_messages: list[ConversationMessage]
    messages_to_keep: list[ConversationMessage]
    attachments: list[CompactAttachment]
    hook_results: list[CompactAttachment]
    compact_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_message_tokens(messages: list[ConversationMessage]) -> int:
    """Estimate total tokens for a conversation, including the 4/3 padding."""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += estimate_tokens(block.text)
            elif isinstance(block, ToolResultBlock):
                total += estimate_tokens(block.content)
            elif isinstance(block, ToolUseBlock):
                total += estimate_tokens(block.name)
                total += estimate_tokens(str(block.input))
    return int(total * TOKEN_ESTIMATION_PADDING)


def estimate_conversation_tokens(messages: list[ConversationMessage]) -> int:
    """Alias kept for backward compatibility."""
    return estimate_message_tokens(messages)


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_metadata(item) for item in value]
    return str(value)


def _record_compact_checkpoint(
    carryover_metadata: dict[str, Any] | None,
    *,
    checkpoint: str,
    trigger: CompactTrigger,
    message_count: int,
    token_count: int,
    attempt: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "checkpoint": checkpoint,
        "trigger": trigger,
        "message_count": message_count,
        "token_count": token_count,
    }
    if attempt is not None:
        payload["attempt"] = attempt
    if details:
        payload.update(_sanitize_metadata(details))
    if carryover_metadata is not None:
        checkpoints = carryover_metadata.setdefault("compact_checkpoints", [])
        if isinstance(checkpoints, list):
            checkpoints.append(payload)
        carryover_metadata["compact_last"] = payload
    return payload


async def _emit_progress(
    callback: CompactProgressCallback | None,
    *,
    phase: Literal[
        "hooks_start",
        "context_collapse_start",
        "context_collapse_end",
        "session_memory_start",
        "session_memory_end",
        "compact_start",
        "compact_retry",
        "compact_end",
        "compact_failed",
    ],
    trigger: CompactTrigger,
    message: str | None = None,
    attempt: int | None = None,
    checkpoint: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if callback is None:
        return
    await callback(
        CompactProgressEvent(
            phase=phase,
            trigger=trigger,
            message=message,
            attempt=attempt,
            checkpoint=checkpoint,
            metadata=_sanitize_metadata(metadata) if metadata else None,
        )
    )


def _is_prompt_too_long_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "prompt too long",
            "context length",
            "maximum context",
            "context window",
            "too many tokens",
            "too large for the model",
        )
    )


def _group_messages_by_prompt_round(
    messages: list[ConversationMessage],
) -> list[list[ConversationMessage]]:
    groups: list[list[ConversationMessage]] = []
    current: list[ConversationMessage] = []
    for message in messages:
        starts_new_round = (
            message.role == "user"
            and not any(isinstance(block, ToolResultBlock) for block in message.content)
            and bool(message.text.strip())
        )
        if starts_new_round and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)
    return groups


def _collapse_text(text: str) -> str:
    if len(text) <= CONTEXT_COLLAPSE_TEXT_CHAR_LIMIT:
        return text
    omitted = len(text) - CONTEXT_COLLAPSE_HEAD_CHARS - CONTEXT_COLLAPSE_TAIL_CHARS
    head = text[:CONTEXT_COLLAPSE_HEAD_CHARS].rstrip()
    tail = text[-CONTEXT_COLLAPSE_TAIL_CHARS:].lstrip()
    return f"{head}\n...[collapsed {omitted} chars]...\n{tail}"


def try_context_collapse(
    messages: list[ConversationMessage],
    *,
    preserve_recent: int,
) -> list[ConversationMessage] | None:
    """Deterministically shrink oversized text blocks before full compact."""
    if len(messages) <= preserve_recent + 2:
        return None

    older = messages[:-preserve_recent]
    newer = messages[-preserve_recent:]
    changed = False
    collapsed_older: list[ConversationMessage] = []
    for message in older:
        new_blocks: list[ContentBlock] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                collapsed = _collapse_text(block.text)
                if collapsed != block.text:
                    changed = True
                new_blocks.append(TextBlock(text=collapsed))
            else:
                new_blocks.append(block)
        collapsed_older.append(ConversationMessage(role=message.role, content=new_blocks))

    if not changed:
        return None

    result = [*collapsed_older, *newer]
    if estimate_message_tokens(result) >= estimate_message_tokens(messages):
        return None
    return result


def truncate_head_for_ptl_retry(
    messages: list[ConversationMessage],
) -> list[ConversationMessage] | None:
    """Drop the oldest prompt rounds when the compact request itself is too large."""
    groups = _group_messages_by_prompt_round(messages)
    if len(groups) < 2:
        return None

    drop_count = max(1, len(groups) // 5)
    drop_count = min(drop_count, len(groups) - 1)
    retained = [message for group in groups[drop_count:] for message in group]
    if not retained:
        return None
    if retained[0].role == "assistant":
        return [ConversationMessage.from_user_text(PTL_RETRY_MARKER), *retained]
    return retained


def _extract_attachment_paths(messages: list[ConversationMessage]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    path_pattern = re.compile(r"path:\s*([^)\\n]+)")
    attachment_pattern = re.compile(r"\[attachment:\s*([^\]]+)\]")
    for message in messages:
        for block in message.content:
            if isinstance(block, ImageBlock) and block.source_path:
                path = str(Path(block.source_path).expanduser())
                if path not in seen:
                    seen.add(path)
                    found.append(path)
            elif isinstance(block, TextBlock):
                for match in path_pattern.findall(block.text):
                    path = match.strip()
                    if path and path not in seen:
                        seen.add(path)
                        found.append(path)
                for match in attachment_pattern.findall(block.text):
                    path = match.strip()
                    if path and "download failed" not in path and path not in seen:
                        seen.add(path)
                        found.append(path)
            if len(found) >= MAX_COMPACT_ATTACHMENTS:
                return found
    return found


def _extract_discovered_tools(messages: list[ConversationMessage]) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()
    for message in messages:
        for tool_use in message.tool_uses:
            if tool_use.name and tool_use.name not in seen:
                seen.add(tool_use.name)
                discovered.append(tool_use.name)
            if len(discovered) >= MAX_DISCOVERED_TOOLS:
                return discovered
    return discovered


def _create_attachment(kind: str, title: str, lines: list[str], *, metadata: dict[str, Any] | None = None) -> CompactAttachment | None:
    filtered = [line.rstrip() for line in lines if line and line.strip()]
    if not filtered:
        return None
    return CompactAttachment(
        kind=kind,
        title=title,
        body="\n".join(filtered),
        metadata=_sanitize_metadata(metadata or {}),
    )


def render_compact_attachment(attachment: CompactAttachment) -> ConversationMessage:
    """Serialize a structured compact attachment into a conversation message."""
    header = f"[Compact attachment: {attachment.kind}] {attachment.title}".strip()
    text = f"{header}\n{attachment.body}".strip()
    return ConversationMessage.from_user_text(text)


def create_compact_boundary_message(metadata: dict[str, Any]) -> ConversationMessage:
    """Create a boundary marker message for post-compact conversation rebuild."""
    lines = [
        "[Compact boundary marker]",
        "Earlier conversation was compacted. Use the summary and preserved assets below as the continuity boundary.",
    ]
    trigger = str(metadata.get("trigger") or "").strip()
    compact_kind = str(metadata.get("compact_kind") or "").strip()
    pre_messages = metadata.get("pre_compact_message_count")
    pre_tokens = metadata.get("pre_compact_token_count")
    post_messages = metadata.get("post_compact_message_count")
    post_tokens = metadata.get("post_compact_token_count")
    if trigger:
        lines.append(f"Trigger: {trigger}")
    if compact_kind:
        lines.append(f"Compaction kind: {compact_kind}")
    if pre_messages is not None or pre_tokens is not None:
        lines.append(
            "Pre-compact footprint: "
            f"messages={pre_messages if pre_messages is not None else 'unknown'}, "
            f"tokens={pre_tokens if pre_tokens is not None else 'unknown'}"
        )
    if post_messages is not None or post_tokens is not None:
        lines.append(
            "Post-compact footprint: "
            f"messages={post_messages if post_messages is not None else 'unknown'}, "
            f"tokens={post_tokens if post_tokens is not None else 'unknown'}"
        )
    anchor = str(metadata.get("preserved_segment_anchor") or "").strip()
    if anchor:
        lines.append(f"Preserved segment anchor: {anchor}")
    return ConversationMessage.from_user_text("\n".join(lines))


def build_post_compact_messages(result: CompactionResult) -> list[ConversationMessage]:
    """Rebuild the post-compact message list in Claude Code's ordering."""
    attachment_messages = [render_compact_attachment(attachment) for attachment in result.attachments]
    hook_messages = [render_compact_attachment(attachment) for attachment in result.hook_results]
    return [
        result.boundary_marker,
        *result.summary_messages,
        *result.messages_to_keep,
        *attachment_messages,
        *hook_messages,
    ]


def _create_recent_attachments_attachment_if_needed(
    attachment_paths: list[str],
) -> CompactAttachment | None:
    if not attachment_paths:
        return None
    return _create_attachment(
        "recent_attachments",
        "Recent local attachments",
        ["Keep these local attachment paths in working memory:"] + [f"- {path}" for path in attachment_paths],
        metadata={"paths": attachment_paths},
    )


def create_recent_files_attachment_if_needed(
    read_file_state: Any,
) -> CompactAttachment | None:
    if not isinstance(read_file_state, list) or not read_file_state:
        return None
    lines = ["Recently read files that may still matter:"]
    entries: list[dict[str, Any]] = []
    normalized_entries = [
        entry
        for entry in read_file_state
        if isinstance(entry, dict) and str(entry.get("path") or "").strip()
    ]
    normalized_entries.sort(
        key=lambda entry: float(entry.get("timestamp") or 0.0),
        reverse=True,
    )
    for entry in normalized_entries[:4]:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        span = str(entry.get("span") or "").strip()
        preview = str(entry.get("preview") or "").strip()
        timestamp = entry.get("timestamp")
        if not path:
            continue
        bullet = f"- {path}"
        if span:
            bullet += f" ({span})"
        lines.append(bullet)
        if preview:
            lines.append(f"  Preview: {preview}")
        entries.append({"path": path, "span": span, "preview": preview, "timestamp": timestamp})
    return _create_attachment("recent_files", "Recently read files", lines, metadata={"entries": entries})


def create_task_focus_attachment_if_needed(
    metadata: dict[str, Any],
) -> CompactAttachment | None:
    state = metadata.get("task_focus_state")
    if not isinstance(state, dict):
        return None
    goal = str(state.get("goal") or "").strip()
    recent_goals = [
        str(item).strip()
        for item in state.get("recent_goals", [])
        if str(item).strip()
    ]
    active_artifacts = [
        str(item).strip()
        for item in state.get("active_artifacts", [])
        if str(item).strip()
    ]
    verified_state = [
        str(item).strip()
        for item in state.get("verified_state", [])
        if str(item).strip()
    ]
    next_step = str(state.get("next_step") or "").strip()
    if not any((goal, recent_goals, active_artifacts, verified_state, next_step)):
        return None
    lines = ["Current working focus to preserve across compaction:"]
    if goal:
        lines.append(f"- Goal: {goal}")
    if recent_goals:
        lines.append("- Recent user goals that still matter:")
        lines.extend(f"  - {item}" for item in recent_goals[-3:])
    if active_artifacts:
        lines.append("- Active artifacts in play:")
        lines.extend(f"  - {item}" for item in active_artifacts[-5:])
    if verified_state:
        lines.append("- Verified state already established:")
        lines.extend(f"  - {item}" for item in verified_state[-4:])
    if next_step:
        lines.append(f"- Suggested next step: {next_step}")
    return _create_attachment(
        "task_focus",
        "Current working focus",
        lines,
        metadata={
            "goal": goal,
            "recent_goals": recent_goals[-3:],
            "active_artifacts": active_artifacts[-5:],
            "verified_state": verified_state[-4:],
            "next_step": next_step,
        },
    )


def create_recent_verified_work_attachment_if_needed(
    verified_work: Any,
) -> CompactAttachment | None:
    if not isinstance(verified_work, list) or not verified_work:
        return None
    entries = [str(entry).strip() for entry in verified_work[-8:] if str(entry).strip()]
    if not entries:
        return None
    return _create_attachment(
        "recent_verified_work",
        "Recently verified work",
        ["These steps or conclusions were explicitly verified before compaction:"] + [f"- {entry}" for entry in entries],
        metadata={"entries": entries},
    )


def create_plan_attachment_if_needed(metadata: dict[str, Any]) -> CompactAttachment | None:
    permission_mode = str(metadata.get("permission_mode") or "").strip().lower()
    if permission_mode != "plan":
        return None
    lines = [
        "Plan mode is still active for this session.",
        "Do not execute mutating tools until the user explicitly exits plan mode.",
    ]
    plan_summary = str(metadata.get("plan_summary") or "").strip()
    if plan_summary:
        lines.append(f"Current plan summary: {plan_summary}")
    return _create_attachment(
        "plan",
        "Plan mode context",
        lines,
        metadata={"permission_mode": permission_mode, "plan_summary": plan_summary},
    )


def create_invoked_skills_attachment_if_needed(
    invoked_skills: Any,
) -> CompactAttachment | None:
    if not isinstance(invoked_skills, list) or not invoked_skills:
        return None
    normalized = [str(skill).strip() for skill in invoked_skills[-8:] if str(skill).strip()]
    if not normalized:
        return None
    return _create_attachment(
        "invoked_skills",
        "Skills used earlier in the session",
        ["The following skills were invoked and may still shape the next step:", "- " + ", ".join(normalized)],
        metadata={"skills": normalized},
    )


def create_async_agent_attachment_if_needed(
    async_agent_state: Any,
) -> CompactAttachment | None:
    if not isinstance(async_agent_state, list) or not async_agent_state:
        return None
    entries = [str(entry).strip() for entry in async_agent_state[-6:] if str(entry).strip()]
    if not entries:
        return None
    return _create_attachment(
        "async_agents",
        "Async agent and background task state",
        ["Recent async-agent/background-task activity:"] + [f"- {entry}" for entry in entries],
        metadata={"entries": entries},
    )


def create_work_log_attachment_if_needed(
    recent_work_log: Any,
) -> CompactAttachment | None:
    if not isinstance(recent_work_log, list) or not recent_work_log:
        return None
    entries = [str(entry).strip() for entry in recent_work_log[-8:] if str(entry).strip()]
    if not entries:
        return None
    return _create_attachment(
        "recent_work_log",
        "Recent execution checkpoints",
        ["Recent work and verification steps taken in this session:"] + [f"- {entry}" for entry in entries],
        metadata={"entries": entries},
    )


def _create_hook_attachments(hook_note: str | None) -> list[CompactAttachment]:
    if not hook_note or not hook_note.strip():
        return []
    attachment = _create_attachment(
        "hook_results",
        "Compact hook notes",
        [hook_note.strip()],
        metadata={"note": hook_note.strip()},
    )
    return [attachment] if attachment is not None else []


def _build_compact_attachments(
    messages: list[ConversationMessage],
    *,
    metadata: dict[str, Any] | None,
) -> list[CompactAttachment]:
    metadata = metadata or {}
    attachments: list[CompactAttachment] = []
    attachment_paths = _extract_attachment_paths(messages)
    builders = [
        create_task_focus_attachment_if_needed(metadata),
        create_recent_verified_work_attachment_if_needed(metadata.get("recent_verified_work")),
        _create_recent_attachments_attachment_if_needed(attachment_paths),
        create_recent_files_attachment_if_needed(metadata.get("read_file_state")),
        create_plan_attachment_if_needed(metadata),
        create_invoked_skills_attachment_if_needed(metadata.get("invoked_skills")),
        create_async_agent_attachment_if_needed(metadata.get("async_agent_state")),
        create_work_log_attachment_if_needed(metadata.get("recent_work_log")),
    ]
    attachments.extend(attachment for attachment in builders if attachment is not None)
    return attachments


def _finalize_compaction_result(result: CompactionResult) -> CompactionResult:
    messages = build_post_compact_messages(result)
    result.compact_metadata.setdefault("post_compact_message_count", len(messages))
    result.compact_metadata.setdefault("post_compact_token_count", estimate_message_tokens(messages))
    result.boundary_marker = create_compact_boundary_message(result.compact_metadata)
    return result


def _metadata_has_checkpoint(metadata: dict[str, Any] | None, checkpoint: str) -> bool:
    if metadata is None:
        return False
    checkpoints = metadata.get("compact_checkpoints")
    if not isinstance(checkpoints, list):
        return False
    return any(isinstance(entry, dict) and entry.get("checkpoint") == checkpoint for entry in checkpoints)


def _build_passthrough_compaction_result(
    messages: list[ConversationMessage],
    *,
    trigger: CompactTrigger,
    compact_kind: CompactionKind,
    metadata: dict[str, Any] | None = None,
) -> CompactionResult:
    compact_metadata = {
        "trigger": trigger,
        "compact_kind": compact_kind,
        "pre_compact_message_count": len(messages),
        "pre_compact_token_count": estimate_message_tokens(messages),
        **_sanitize_metadata(metadata or {}),
    }
    result = CompactionResult(
        trigger=trigger,
        compact_kind=compact_kind,
        boundary_marker=create_compact_boundary_message(compact_metadata),
        summary_messages=[],
        messages_to_keep=list(messages),
        attachments=[],
        hook_results=[],
        compact_metadata=compact_metadata,
    )
    return _finalize_compaction_result(result)


# ---------------------------------------------------------------------------
# Microcompact — clear old tool results to reduce tokens cheaply
# ---------------------------------------------------------------------------

def _collect_compactable_tool_ids(messages: list[ConversationMessage]) -> list[str]:
    """Walk messages and collect tool_use IDs whose results are compactable."""
    ids: list[str] = []
    for msg in messages:
        if msg.role != "assistant":
            continue
        for block in msg.content:
            if isinstance(block, ToolUseBlock) and block.name in COMPACTABLE_TOOLS:
                ids.append(block.id)
    return ids


def microcompact_messages(
    messages: list[ConversationMessage],
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> tuple[list[ConversationMessage], int]:
    """Clear old compactable tool results, keeping the most recent *keep_recent*.

    This is the cheap first pass — no LLM call required. Tool result content
    is replaced with :data:`TIME_BASED_MC_CLEARED_MESSAGE`.

    Returns:
        (messages, tokens_saved) — messages are mutated in place for efficiency.
    """
    keep_recent = max(1, keep_recent)  # never clear ALL results
    all_ids = _collect_compactable_tool_ids(messages)

    if len(all_ids) <= keep_recent:
        return messages, 0

    keep_set = set(all_ids[-keep_recent:])
    clear_set = set(all_ids) - keep_set

    tokens_saved = 0
    for msg in messages:
        if msg.role != "user":
            continue
        new_content: list[ContentBlock] = []
        for block in msg.content:
            if (
                isinstance(block, ToolResultBlock)
                and block.tool_use_id in clear_set
                and block.content != TIME_BASED_MC_CLEARED_MESSAGE
            ):
                tokens_saved += estimate_tokens(block.content)
                new_content.append(
                    ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=TIME_BASED_MC_CLEARED_MESSAGE,
                        is_error=block.is_error,
                    )
                )
            else:
                new_content.append(block)
        msg.content = new_content

    if tokens_saved > 0:
        log.info("Microcompact cleared %d tool results, saved ~%d tokens", len(clear_set), tokens_saved)

    return messages, tokens_saved


def _summarize_message_for_memory(message: ConversationMessage) -> str:
    text = " ".join(message.text.split())
    if text:
        text = text[:160]
        return f"{message.role}: {text}"
    tool_uses = [block.name for block in message.tool_uses]
    if tool_uses:
        return f"{message.role}: tool calls -> {', '.join(tool_uses[:4])}"
    if any(isinstance(block, ToolResultBlock) for block in message.content):
        return f"{message.role}: tool results returned"
    return f"{message.role}: [non-text content]"


def _build_session_memory_message(messages: list[ConversationMessage]) -> ConversationMessage | None:
    lines: list[str] = []
    total_chars = 0
    for message in messages:
        line = _summarize_message_for_memory(message)
        if not line:
            continue
        projected = total_chars + len(line) + 1
        if lines and (len(lines) >= SESSION_MEMORY_MAX_LINES or projected >= SESSION_MEMORY_MAX_CHARS):
            lines.append("... earlier context condensed ...")
            break
        lines.append(line)
        total_chars = projected
    if not lines:
        return None
    body = "\n".join(lines)
    return ConversationMessage.from_user_text(
        "Session memory summary from earlier in this conversation:\n" + body
    )


def try_session_memory_compaction(
    messages: list[ConversationMessage],
    *,
    preserve_recent: int = SESSION_MEMORY_KEEP_RECENT,
    trigger: CompactTrigger = "auto",
    metadata: dict[str, Any] | None = None,
) -> CompactionResult | None:
    """Cheap deterministic compaction for long chats before full LLM compaction."""
    if len(messages) <= preserve_recent + 4:
        return None
    older = messages[:-preserve_recent]
    newer = messages[-preserve_recent:]
    summary_message = _build_session_memory_message(older)
    if summary_message is None:
        return None
    provisional = [summary_message, *newer]
    if (
        estimate_message_tokens(provisional) >= estimate_message_tokens(messages)
        and len(provisional) >= len(messages)
    ):
        return None
    compact_metadata = {
        "trigger": trigger,
        "compact_kind": "session_memory",
        "pre_compact_message_count": len(messages),
        "pre_compact_token_count": estimate_message_tokens(messages),
        "preserve_recent": preserve_recent,
        "used_session_memory": True,
        "pre_compact_discovered_tools": _extract_discovered_tools(older),
        "attachments": _extract_attachment_paths(older),
    }
    result = CompactionResult(
        trigger=trigger,
        compact_kind="session_memory",
        boundary_marker=create_compact_boundary_message(compact_metadata),
        summary_messages=[summary_message],
        messages_to_keep=list(newer),
        attachments=_build_compact_attachments(older, metadata=metadata),
        hook_results=[],
        compact_metadata=compact_metadata,
    )
    return _finalize_compaction_result(result)


# ---------------------------------------------------------------------------
# Full compact — LLM-based summarization
# ---------------------------------------------------------------------------

NO_TOOLS_PREAMBLE = """\
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

- Do NOT use read_file, bash, grep, glob, edit_file, write_file, or ANY other tool.
- You already have all the context you need in the conversation above.
- Tool calls will be REJECTED and will waste your only turn — you will fail the task.
- Your entire response must be plain text: an <analysis> block followed by a <summary> block.

"""

BASE_COMPACT_PROMPT = """\
Your task is to create a detailed summary of the conversation so far. This summary will replace the earlier messages, so it must capture all important information.

First, draft your analysis inside <analysis> tags. Walk through the conversation chronologically and extract:
- Every user request and intent (explicit and implicit)
- The approach taken and technical decisions made
- Specific code, files, and configurations discussed (with paths and line numbers where available)
- All errors encountered and how they were fixed
- Any user feedback or corrections

Then, produce a structured summary inside <summary> tags with these sections:

1. **Primary Request and Intent**: All user requests in full detail, including nuances and constraints.
2. **Key Technical Concepts**: Technologies, frameworks, patterns, and conventions discussed.
3. **Files and Code Sections**: Every file examined or modified, with specific code snippets and line numbers.
4. **Errors and Fixes**: Every error encountered, its cause, and how it was resolved.
5. **Problem Solving**: Problems solved and approaches that worked vs. didn't work.
6. **All User Messages**: Non-tool-result user messages (preserve exact wording for context).
7. **Pending Tasks**: Explicitly requested work that hasn't been completed yet.
8. **Current Work**: Detailed description of the last task being worked on before compaction.
9. **Optional Next Step**: The single most logical next step, directly aligned with the user's recent request.
"""

NO_TOOLS_TRAILER = """
REMINDER: Do NOT call any tools. Respond with plain text only — an <analysis> block followed by a <summary> block. Tool calls will be rejected and you will fail the task."""


def get_compact_prompt(custom_instructions: str | None = None) -> str:
    """Build the full compaction prompt sent to the model."""
    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT
    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"
    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(raw_summary: str) -> str:
    """Strip the <analysis> scratchpad and extract the <summary> content."""
    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw_summary)
    m = re.search(r"<summary>([\s\S]*?)</summary>", text)
    if m:
        text = text.replace(m.group(0), f"Summary:\n{m.group(1).strip()}")
    text = re.sub(r"\n\n+", "\n\n", text)
    return text.strip()


def build_compact_summary_message(
    summary: str,
    *,
    suppress_follow_up: bool = False,
    recent_preserved: bool = False,
) -> str:
    """Create the injected user message that replaces compacted history."""
    formatted = format_compact_summary(summary)
    text = (
        "This session is being continued from a previous conversation that ran "
        "out of context. The summary below covers the earlier portion of the "
        "conversation.\n\n"
        f"{formatted}"
    )
    if recent_preserved:
        text += "\n\nRecent messages are preserved verbatim."
    if suppress_follow_up:
        text += (
            "\nContinue the conversation from where it left off without asking "
            "the user any further questions. Resume directly — do not acknowledge "
            "the summary, do not recap what was happening, do not preface with "
            '"I\'ll continue" or similar. Pick up the last task as if the break '
            "never happened."
        )
    return text


# ---------------------------------------------------------------------------
# Auto-compact tracking
# ---------------------------------------------------------------------------

@dataclass
class AutoCompactState:
    """Mutable state that persists across query loop turns."""

    compacted: bool = False
    turn_counter: int = 0
    turn_id: str = ""
    consecutive_failures: int = 0


# ---------------------------------------------------------------------------
# Context window helpers
# ---------------------------------------------------------------------------

def get_context_window(model: str) -> int:
    """Return the context window size for a model (conservative defaults)."""
    m = model.lower()
    if "opus" in m:
        return 200_000
    if "sonnet" in m:
        return 200_000
    if "haiku" in m:
        return 200_000
    # Kimi / other providers — be conservative
    return _DEFAULT_CONTEXT_WINDOW


def get_autocompact_threshold(model: str) -> int:
    """Calculate the token count at which auto-compact fires."""
    context_window = get_context_window(model)
    reserved = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, 20_000)
    effective = context_window - reserved
    return effective - AUTOCOMPACT_BUFFER_TOKENS


def should_autocompact(
    messages: list[ConversationMessage],
    model: str,
    state: AutoCompactState,
) -> bool:
    """Return True when the conversation should be auto-compacted."""
    if state.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return False
    token_count = estimate_message_tokens(messages)
    threshold = get_autocompact_threshold(model)
    return token_count >= threshold


# ---------------------------------------------------------------------------
# Full compact execution (calls the LLM)
# ---------------------------------------------------------------------------

async def compact_conversation(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    preserve_recent: int = 6,
    custom_instructions: str | None = None,
    suppress_follow_up: bool = True,
    trigger: CompactTrigger = "manual",
    progress_callback: CompactProgressCallback | None = None,
    emit_hooks_start: bool = True,
    hook_executor: HookExecutor | None = None,
    carryover_metadata: dict[str, Any] | None = None,
) -> CompactionResult:
    """Compact messages by calling the LLM to produce a summary.

    1. Microcompact first (cheap token reduction).
    2. Split into older (to summarize) and recent (to preserve).
    3. Call the LLM with the compact prompt to get a structured summary.
    4. Replace older messages with the summary + preserved recent messages.

    Args:
        messages: The full conversation history.
        api_client: An ``AnthropicApiClient`` or compatible for the summary call.
        model: Model ID to use for the summary.
        system_prompt: System prompt for the summary call.
        preserve_recent: Number of recent messages to keep verbatim.
        custom_instructions: Optional extra instructions for the summary prompt.
        suppress_follow_up: If True, instruct the model not to ask follow-ups.

    Returns:
        Structured compaction result that can be rebuilt into post-compact messages.
    """
    from openharness.api.client import ApiMessageRequest, ApiMessageCompleteEvent

    if len(messages) <= preserve_recent:
        return _build_passthrough_compaction_result(
            messages,
            trigger=trigger,
            compact_kind="full",
            metadata={"reason": "conversation already within preserve_recent window"},
        )

    # Step 1: microcompact to reduce tokens cheaply
    messages, tokens_freed = microcompact_messages(messages, keep_recent=DEFAULT_KEEP_RECENT)

    pre_compact_tokens = estimate_message_tokens(messages)
    log.info("Compacting conversation: %d messages, ~%d tokens", len(messages), pre_compact_tokens)

    # Step 2: split into older (summarize) and newer (preserve)
    older = messages[:-preserve_recent]
    newer = messages[-preserve_recent:]

    # Step 3: build compact request — send older messages + compact prompt
    compact_prompt = get_compact_prompt(custom_instructions)
    compact_messages = list(older) + [ConversationMessage.from_user_text(compact_prompt)]
    attachment_paths = _extract_attachment_paths(older)
    discovered_tools = _extract_discovered_tools(older)
    hook_payload = {
        "event": HookEvent.PRE_COMPACT.value,
        "trigger": trigger,
        "model": model,
        "message_count": len(messages),
        "token_count": pre_compact_tokens,
        "preserve_recent": preserve_recent,
        "attachments": attachment_paths,
        "discovered_tools": discovered_tools,
        **(carryover_metadata or {}),
    }
    start_checkpoint = _record_compact_checkpoint(
        carryover_metadata,
        checkpoint="compact_prepare",
        trigger=trigger,
        message_count=len(messages),
        token_count=pre_compact_tokens,
        details={
            "preserve_recent": preserve_recent,
            "attachments": attachment_paths,
            "discovered_tools": discovered_tools,
        },
    )

    if emit_hooks_start:
        await _emit_progress(
            progress_callback,
            phase="hooks_start",
            trigger=trigger,
            message="Preparing conversation compaction.",
            checkpoint="compact_hooks_start",
            metadata=start_checkpoint,
        )
    if hook_executor is not None:
        hook_result = await hook_executor.execute(HookEvent.PRE_COMPACT, hook_payload)
        if hook_result.blocked:
            reason = hook_result.reason or "pre-compact hook blocked compaction"
            failed_checkpoint = _record_compact_checkpoint(
                carryover_metadata,
                checkpoint="compact_failed",
                trigger=trigger,
                message_count=len(messages),
                token_count=pre_compact_tokens,
                details={"reason": reason},
            )
            await _emit_progress(
                progress_callback,
                phase="compact_failed",
                trigger=trigger,
                message=reason,
                checkpoint="compact_failed",
                metadata=failed_checkpoint,
            )
            return _build_passthrough_compaction_result(
                messages,
                trigger=trigger,
                compact_kind="full",
                metadata={"reason": reason},
            )
    compact_start_checkpoint = _record_compact_checkpoint(
        carryover_metadata,
        checkpoint="compact_start",
        trigger=trigger,
        message_count=len(messages),
        token_count=pre_compact_tokens,
        details={"preserve_recent": preserve_recent},
    )
    await _emit_progress(
        progress_callback,
        phase="compact_start",
        trigger=trigger,
        message="Compacting conversation memory.",
        checkpoint="compact_start",
        metadata=compact_start_checkpoint,
    )

    summary_text = ""
    messages_to_summarize = compact_messages
    retry_messages = messages_to_summarize
    ptl_retries = 0

    async def _collect_summary(summary_request_messages: list[ConversationMessage]) -> str:
        collected = ""
        stream = api_client.stream_message(
            ApiMessageRequest(
                model=model,
                messages=summary_request_messages,
                system_prompt=system_prompt or "You are a conversation summarizer.",
                max_tokens=MAX_OUTPUT_TOKENS_FOR_SUMMARY,
                tools=[],  # no tools for compact call
            )
        )
        if inspect.isawaitable(stream):
            stream = await stream
        if not hasattr(stream, "__aiter__"):
            raise RuntimeError("Compaction client did not provide a streaming response.")
        async for event in stream:
            if isinstance(event, ApiMessageCompleteEvent):
                collected = event.message.text
        if collected.strip():
            return collected
        raise RuntimeError(ERROR_MESSAGE_INCOMPLETE_RESPONSE)

    for attempt in range(1, MAX_COMPACT_STREAMING_RETRIES + 2):
        try:
            summary_text = await asyncio.wait_for(
                _collect_summary(retry_messages),
                timeout=COMPACT_TIMEOUT_SECONDS,
            )
            break
        except Exception as exc:
            if _is_prompt_too_long_error(exc) and ptl_retries < MAX_PTL_RETRIES:
                truncated = truncate_head_for_ptl_retry(retry_messages[:-1])
                if truncated:
                    ptl_retries += 1
                    retry_messages = [*truncated, retry_messages[-1]]
                    await _emit_progress(
                        progress_callback,
                        phase="compact_retry",
                        trigger=trigger,
                        message="Compaction prompt was too large; retrying with older context trimmed.",
                        attempt=ptl_retries,
                        checkpoint="compact_retry_prompt_too_long",
                        metadata=_record_compact_checkpoint(
                            carryover_metadata,
                            checkpoint="compact_retry_prompt_too_long",
                            trigger=trigger,
                            message_count=len(retry_messages),
                            token_count=estimate_message_tokens(retry_messages),
                            attempt=ptl_retries,
                            details={"ptl_retries": ptl_retries},
                        ),
                    )
                    continue
            if attempt > MAX_COMPACT_STREAMING_RETRIES:
                await _emit_progress(
                    progress_callback,
                    phase="compact_failed",
                    trigger=trigger,
                    message=str(exc),
                    attempt=attempt,
                    checkpoint="compact_failed",
                    metadata=_record_compact_checkpoint(
                        carryover_metadata,
                        checkpoint="compact_failed",
                        trigger=trigger,
                        message_count=len(retry_messages),
                        token_count=estimate_message_tokens(retry_messages),
                        attempt=attempt,
                        details={"reason": str(exc)},
                    ),
                )
                raise
            await _emit_progress(
                progress_callback,
                phase="compact_retry",
                trigger=trigger,
                message=str(exc),
                attempt=attempt,
                checkpoint="compact_retry",
                metadata=_record_compact_checkpoint(
                    carryover_metadata,
                    checkpoint="compact_retry",
                    trigger=trigger,
                    message_count=len(retry_messages),
                    token_count=estimate_message_tokens(retry_messages),
                    attempt=attempt,
                    details={"reason": str(exc)},
                ),
            )

    if not summary_text:
        await _emit_progress(
            progress_callback,
            phase="compact_failed",
            trigger=trigger,
            message=ERROR_MESSAGE_INCOMPLETE_RESPONSE,
            checkpoint="compact_failed",
            metadata=_record_compact_checkpoint(
                carryover_metadata,
                checkpoint="compact_failed",
                trigger=trigger,
                message_count=len(messages),
                token_count=pre_compact_tokens,
                details={"reason": ERROR_MESSAGE_INCOMPLETE_RESPONSE},
            ),
        )
        log.warning("Compact summary was empty — returning original messages")
        return _build_passthrough_compaction_result(
            messages,
            trigger=trigger,
            compact_kind="full",
            metadata={"reason": ERROR_MESSAGE_INCOMPLETE_RESPONSE},
        )

    # Step 4: build the new message list
    summary_content = build_compact_summary_message(
        summary_text,
        suppress_follow_up=suppress_follow_up,
        recent_preserved=len(newer) > 0,
    )
    summary_msg = ConversationMessage.from_user_text(summary_content)
    initial_post_compact_tokens = estimate_message_tokens([summary_msg, *newer])
    if hook_executor is not None:
        post_hook_result = await hook_executor.execute(
            HookEvent.POST_COMPACT,
            {
                "event": HookEvent.POST_COMPACT.value,
                "trigger": trigger,
                "model": model,
                "pre_compact_message_count": len(messages),
                "post_compact_message_count": len(newer) + 1,
                "pre_compact_tokens": pre_compact_tokens,
                "post_compact_tokens": initial_post_compact_tokens,
                "attachments": attachment_paths,
                "discovered_tools": discovered_tools,
                **(carryover_metadata or {}),
            },
        )
        hook_note = post_hook_result.reason or "\n".join(
            result.output.strip()
            for result in post_hook_result.results
            if result.output.strip()
        )
        hook_attachments = _create_hook_attachments(hook_note)
    else:
        hook_attachments = []

    compact_metadata = {
        "trigger": trigger,
        "compact_kind": "full",
        "pre_compact_message_count": len(messages),
        "pre_compact_token_count": pre_compact_tokens,
        "preserve_recent": preserve_recent,
        "tokens_freed_by_microcompact": tokens_freed,
        "pre_compact_discovered_tools": discovered_tools,
        "used_head_truncation_retry": ptl_retries > 0,
        "used_context_collapse": _metadata_has_checkpoint(carryover_metadata, "query_context_collapse_end"),
        "used_session_memory": False,
        "retry_attempts": max(0, attempt - 1 if "attempt" in locals() else 0),
        "attachments": attachment_paths,
    }
    if carryover_metadata is not None:
        checkpoints = carryover_metadata.get("compact_checkpoints")
        if isinstance(checkpoints, list):
            compact_metadata["compact_checkpoints"] = checkpoints
        compact_last = carryover_metadata.get("compact_last")
        if isinstance(compact_last, dict):
            compact_metadata["compact_last"] = compact_last

    compaction_result = CompactionResult(
        trigger=trigger,
        compact_kind="full",
        boundary_marker=create_compact_boundary_message(compact_metadata),
        summary_messages=[summary_msg],
        messages_to_keep=list(newer),
        attachments=_build_compact_attachments(older, metadata=carryover_metadata),
        hook_results=hook_attachments,
        compact_metadata=compact_metadata,
    )
    compaction_result = _finalize_compaction_result(compaction_result)
    post_compact_messages = build_post_compact_messages(compaction_result)
    post_compact_tokens = estimate_message_tokens(post_compact_messages)
    compaction_result.compact_metadata["post_compact_message_count"] = len(post_compact_messages)
    compaction_result.compact_metadata["post_compact_token_count"] = post_compact_tokens
    compaction_result.boundary_marker = create_compact_boundary_message(compaction_result.compact_metadata)
    log.info(
        "Compaction done: %d -> %d messages, ~%d -> ~%d tokens (saved ~%d)",
        len(messages), len(post_compact_messages),
        pre_compact_tokens, post_compact_tokens,
        pre_compact_tokens - post_compact_tokens,
    )
    await _emit_progress(
        progress_callback,
        phase="compact_end",
        trigger=trigger,
        message="Conversation compaction complete.",
        checkpoint="compact_end",
        metadata=_record_compact_checkpoint(
            carryover_metadata,
            checkpoint="compact_end",
            trigger=trigger,
            message_count=len(post_compact_messages),
            token_count=post_compact_tokens,
            details={
                "pre_compact_message_count": len(messages),
                "post_compact_message_count": len(post_compact_messages),
                "pre_compact_tokens": pre_compact_tokens,
                "post_compact_tokens": post_compact_tokens,
                "tokens_saved": pre_compact_tokens - post_compact_tokens,
                "attachments": attachment_paths,
                "discovered_tools": discovered_tools,
            },
        ),
    )
    return compaction_result


# ---------------------------------------------------------------------------
# Auto-compact integration (called from query loop)
# ---------------------------------------------------------------------------

async def auto_compact_if_needed(
    messages: list[ConversationMessage],
    *,
    api_client: Any,
    model: str,
    system_prompt: str = "",
    state: AutoCompactState,
    preserve_recent: int = 6,
    progress_callback: CompactProgressCallback | None = None,
    force: bool = False,
    trigger: CompactTrigger = "auto",
    hook_executor: HookExecutor | None = None,
    carryover_metadata: dict[str, Any] | None = None,
) -> tuple[list[ConversationMessage], bool]:
    """Check if auto-compact should fire, and if so, compact.

    Call this at the start of each query loop turn.

    Returns:
        (messages, was_compacted) — if compacted, messages is the new list.
    """
    if not force and not should_autocompact(messages, model, state):
        return messages, False

    log.info("Auto-compact triggered (failures=%d)", state.consecutive_failures)
    _record_compact_checkpoint(
        carryover_metadata,
        checkpoint=f"query_{trigger}_triggered",
        trigger=trigger,
        message_count=len(messages),
        token_count=estimate_message_tokens(messages),
        details={"consecutive_failures": state.consecutive_failures},
    )

    # Try microcompact first — may be enough
    messages, tokens_freed = microcompact_messages(messages)
    _record_compact_checkpoint(
        carryover_metadata,
        checkpoint="query_microcompact_end",
        trigger=trigger,
        message_count=len(messages),
        token_count=estimate_message_tokens(messages),
        details={"tokens_freed": tokens_freed},
    )
    if tokens_freed > 0 and not should_autocompact(messages, model, state):
        log.info("Microcompact freed ~%d tokens, auto-compact no longer needed", tokens_freed)
        return messages, True

    context_collapsed = try_context_collapse(messages, preserve_recent=preserve_recent)
    if context_collapsed is not None:
        await _emit_progress(
            progress_callback,
            phase="context_collapse_start",
            trigger=trigger,
            message="Collapsing oversized context before full compaction.",
            checkpoint="query_context_collapse_start",
            metadata=_record_compact_checkpoint(
                carryover_metadata,
                checkpoint="query_context_collapse_start",
                trigger=trigger,
                message_count=len(messages),
                token_count=estimate_message_tokens(messages),
            ),
        )
        messages = context_collapsed
        await _emit_progress(
            progress_callback,
            phase="context_collapse_end",
            trigger=trigger,
            message="Context collapse complete.",
            checkpoint="query_context_collapse_end",
            metadata=_record_compact_checkpoint(
                carryover_metadata,
                checkpoint="query_context_collapse_end",
                trigger=trigger,
                message_count=len(messages),
                token_count=estimate_message_tokens(messages),
            ),
        )
        if not force and not should_autocompact(messages, model, state):
            return messages, True

    session_memory = try_session_memory_compaction(
        messages,
        preserve_recent=max(preserve_recent, SESSION_MEMORY_KEEP_RECENT),
        trigger=trigger,
        metadata=carryover_metadata,
    )
    if session_memory is not None:
        await _emit_progress(
            progress_callback,
            phase="session_memory_start",
            trigger=trigger,
            message="Condensing earlier conversation into session memory.",
            checkpoint="query_session_memory_start",
            metadata=_record_compact_checkpoint(
                carryover_metadata,
                checkpoint="query_session_memory_start",
                trigger=trigger,
                message_count=len(messages),
                token_count=estimate_message_tokens(messages),
            ),
        )
        await _emit_progress(
            progress_callback,
            phase="session_memory_end",
            trigger=trigger,
            message="Session memory condensation complete.",
            checkpoint="query_session_memory_end",
            metadata=_record_compact_checkpoint(
                carryover_metadata,
                checkpoint="query_session_memory_end",
                trigger=trigger,
                message_count=len(build_post_compact_messages(session_memory)),
                token_count=estimate_message_tokens(build_post_compact_messages(session_memory)),
            ),
        )
        state.compacted = True
        state.turn_counter += 1
        state.turn_id = uuid4().hex
        state.consecutive_failures = 0
        return build_post_compact_messages(session_memory), True

    # Full compact needed
    try:
        result = await compact_conversation(
            messages,
            api_client=api_client,
            model=model,
            system_prompt=system_prompt,
            preserve_recent=preserve_recent,
            suppress_follow_up=True,
            trigger=trigger,
            progress_callback=progress_callback,
            hook_executor=hook_executor,
            carryover_metadata=carryover_metadata,
        )
        state.compacted = True
        state.turn_counter += 1
        state.turn_id = uuid4().hex
        state.consecutive_failures = 0
        return build_post_compact_messages(result), True
    except Exception as exc:
        state.consecutive_failures += 1
        _record_compact_checkpoint(
            carryover_metadata,
            checkpoint=f"query_{trigger}_failed",
            trigger=trigger,
            message_count=len(messages),
            token_count=estimate_message_tokens(messages),
            details={"reason": str(exc), "consecutive_failures": state.consecutive_failures},
        )
        log.error(
            "Auto-compact failed (attempt %d/%d): %s",
            state.consecutive_failures,
            MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
            exc,
        )
        return messages, False


# ---------------------------------------------------------------------------
# Legacy compat
# ---------------------------------------------------------------------------

def summarize_messages(
    messages: list[ConversationMessage],
    *,
    max_messages: int = 8,
) -> str:
    """Produce a compact textual summary of recent messages (legacy)."""
    selected = messages[-max_messages:]
    lines: list[str] = []
    for message in selected:
        text = message.text.strip()
        if not text:
            continue
        lines.append(f"{message.role}: {text[:300]}")
    return "\n".join(lines)


def compact_messages(
    messages: list[ConversationMessage],
    *,
    preserve_recent: int = 6,
) -> list[ConversationMessage]:
    """Replace older conversation history with a synthetic summary (legacy)."""
    if len(messages) <= preserve_recent:
        return list(messages)
    older = messages[:-preserve_recent]
    newer = messages[-preserve_recent:]
    summary = summarize_messages(older)
    if not summary:
        return list(newer)
    return [
        ConversationMessage(
            role="user",
            content=[TextBlock(text=f"[conversation summary]\n{summary}")],
        ),
        *newer,
    ]


__all__ = [
    "AUTO_COMPACT_BUFFER_TOKENS",
    "AutoCompactState",
    "CompactAttachment",
    "CompactionResult",
    "COMPACTABLE_TOOLS",
    "TIME_BASED_MC_CLEARED_MESSAGE",
    "auto_compact_if_needed",
    "build_post_compact_messages",
    "build_compact_summary_message",
    "compact_conversation",
    "compact_messages",
    "create_compact_boundary_message",
    "estimate_conversation_tokens",
    "estimate_message_tokens",
    "format_compact_summary",
    "get_autocompact_threshold",
    "get_compact_prompt",
    "microcompact_messages",
    "should_autocompact",
    "summarize_messages",
]
