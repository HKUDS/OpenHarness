"""Durable memory extraction from completed turns."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest, SupportsStreamingMessages
from openharness.engine.messages import ConversationMessage, ToolUseBlock
from openharness.memory.manager import add_memory_entry
from openharness.memory.paths import get_project_memory_dir
from openharness.memory.relevance import build_memory_manifest
from openharness.memory.scan import scan_memory_files
from openharness.memory.schema import (
    DEFAULT_MEMORY_SCOPE,
    DEFAULT_MEMORY_TYPE,
    MemoryScope,
    MemoryType,
    parse_memory_scope,
    parse_memory_type,
)
from openharness.memory.team import check_team_memory_secrets, validate_team_memory_write_path

log = logging.getLogger(__name__)

MEMORY_WRITE_TOOLS = {"write_file", "edit_file"}


@dataclass(frozen=True)
class ExtractionRecord:
    """Structured memory record proposed by the extraction pass."""

    title: str
    body: str
    memory_type: MemoryType = DEFAULT_MEMORY_TYPE
    scope: MemoryScope = DEFAULT_MEMORY_SCOPE
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of a durable memory extraction run."""

    skipped: bool
    reason: str = ""
    records: tuple[ExtractionRecord, ...] = ()
    written_paths: tuple[Path, ...] = ()


def has_memory_writes_since(
    messages: list[ConversationMessage],
    memory_dir: str | Path,
    *,
    cwd: str | Path | None = None,
) -> bool:
    """Return whether the visible turn already wrote memory files."""

    root = Path(memory_dir).expanduser().resolve()
    write_base = Path(cwd).expanduser().resolve() if cwd is not None else root
    for message in messages:
        for block in message.content:
            if not isinstance(block, ToolUseBlock):
                continue
            if block.name not in MEMORY_WRITE_TOOLS:
                continue
            raw_path = block.input.get("path") or block.input.get("file_path")
            if not raw_path:
                continue
            path = Path(str(raw_path)).expanduser()
            if not path.is_absolute():
                path = write_base / path
            try:
                path.resolve().relative_to(root)
            except ValueError:
                continue
            return True
    return False


async def extract_memories_from_turn(
    *,
    cwd: str | Path,
    api_client: SupportsStreamingMessages,
    model: str,
    messages: list[ConversationMessage],
    max_records: int = 3,
) -> ExtractionResult:
    """Ask the model for durable memory candidates and apply them."""

    memory_dir = get_project_memory_dir(cwd)
    if len(messages) < 2:
        return ExtractionResult(skipped=True, reason="not enough messages")
    if has_memory_writes_since(messages, memory_dir, cwd=cwd):
        return ExtractionResult(skipped=True, reason="main conversation already wrote memory")

    prompt = build_extraction_prompt(cwd, messages, max_records=max_records)
    final_text = ""
    async for event in api_client.stream_message(
        ApiMessageRequest(
            model=model,
            messages=[ConversationMessage.from_user_text(prompt)],
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            max_tokens=2048,
            tools=[],
        )
    ):
        if isinstance(event, ApiMessageCompleteEvent):
            final_text = event.message.text
            break
    records = parse_extraction_records(final_text, max_records=max_records)
    if not records:
        return ExtractionResult(skipped=True, reason="no durable memories proposed")
    return apply_extraction_records(cwd, records)


def build_extraction_prompt(cwd: str | Path, messages: list[ConversationMessage], *, max_records: int) -> str:
    """Build the extraction request from recent messages and manifest."""

    manifest = build_memory_manifest(scan_memory_files(cwd, max_files=80))
    transcript = "\n".join(_summarize_message(message) for message in messages[-12:])
    return (
        "Extract only durable memories from the recent conversation.\n"
        f"Return JSON with at most {max_records} records. Existing memory manifest:\n"
        f"{manifest or '(empty)'}\n\n"
        "Recent conversation:\n"
        f"{transcript}\n\n"
        "JSON schema: {\"memories\":[{\"title\":\"...\",\"type\":\"user|feedback|project|reference\","
        "\"scope\":\"private|project|team\",\"description\":\"...\",\"body\":\"...\",\"tags\":[\"...\"]}]}"
    )


EXTRACTION_SYSTEM_PROMPT = """You maintain OpenHarness durable memory.
Save only stable, future-useful facts that are not derivable from current files,
git history, or documentation. Prefer updating existing memories conceptually
over duplicating them. Do not save secrets. If nothing is worth saving, return
{"memories": []}.
"""


def parse_extraction_records(text: str, *, max_records: int = 3) -> tuple[ExtractionRecord, ...]:
    """Parse JSON memory extraction output."""

    try:
        payload = json.loads(_extract_json_object(text))
    except json.JSONDecodeError:
        return ()
    raw_records = payload.get("memories") if isinstance(payload, dict) else None
    if not isinstance(raw_records, list):
        return ()
    records: list[ExtractionRecord] = []
    for item in raw_records[:max_records]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title or not body:
            continue
        memory_type = parse_memory_type(item.get("type"), default=DEFAULT_MEMORY_TYPE) or DEFAULT_MEMORY_TYPE
        scope = parse_memory_scope(item.get("scope"), default=DEFAULT_MEMORY_SCOPE) or DEFAULT_MEMORY_SCOPE
        tags_raw = item.get("tags") or ()
        tags = tuple(str(tag).strip() for tag in tags_raw if str(tag).strip()) if isinstance(tags_raw, list) else ()
        records.append(
            ExtractionRecord(
                title=title,
                body=body,
                memory_type=memory_type,
                scope=scope,
                description=str(item.get("description") or "").strip(),
                tags=tags,
            )
        )
    return tuple(records)


def apply_extraction_records(cwd: str | Path, records: tuple[ExtractionRecord, ...]) -> ExtractionResult:
    """Write accepted records to durable memory."""

    written: list[Path] = []
    for record in records:
        if record.scope == "team":
            secret_error = check_team_memory_secrets(record.body)
            if secret_error:
                log.warning("memory extraction skipped team record %r: %s", record.title, secret_error)
                continue
            path, error = validate_team_memory_write_path(cwd, f"{record.title}.md")
            if error or path is None:
                log.warning("memory extraction skipped team record %r: %s", record.title, error)
                continue
        written.append(
            add_memory_entry(
                cwd,
                record.title,
                record.body,
                memory_type=record.memory_type,
                scope=record.scope,
                description=record.description,
                tags=record.tags,
            )
        )
    return ExtractionResult(skipped=not bool(written), reason="" if written else "all records rejected", records=records, written_paths=tuple(written))


def validate_extraction_tool_request(tool_name: str, tool_input: dict[str, Any], memory_dir: str | Path) -> tuple[bool, str]:
    """Permission guard for extraction-like agents."""

    if tool_name in {"read_file", "grep", "glob"}:
        return True, ""
    if tool_name == "bash":
        command = str(tool_input.get("command") or "")
        if _is_read_only_shell(command):
            return True, ""
        return False, "memory extraction may only run read-only shell commands"
    if tool_name in {"write_file", "edit_file"}:
        raw_path = str(tool_input.get("path") or tool_input.get("file_path") or "")
        if not raw_path:
            return False, "memory extraction write requires a path"
        root = Path(memory_dir).expanduser().resolve()
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = root / path
        try:
            path.resolve().relative_to(root)
        except ValueError:
            return False, f"memory extraction writes must stay within {root}"
        return True, ""
    return False, f"memory extraction cannot use tool {tool_name}"


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _summarize_message(message: ConversationMessage) -> str:
    text = " ".join(message.text.split())
    if text:
        return f"{message.role}: {text[:1200]}"
    if message.tool_uses:
        return f"{message.role}: tool calls -> {', '.join(block.name for block in message.tool_uses)}"
    return f"{message.role}: [non-text content]"


def _is_read_only_shell(command: str) -> bool:
    lowered = command.strip().lower()
    if not lowered:
        return False
    denied = (" > ", ">>", " rm ", " mv ", " cp ", " sed -i", " tee ", "python -c", "python3 -c")
    if any(marker in f" {lowered} " for marker in denied):
        return False
    first = lowered.split(maxsplit=1)[0]
    return first in {"ls", "pwd", "cat", "head", "tail", "rg", "grep", "find", "git", "wc", "sed", "awk", "stat"}
