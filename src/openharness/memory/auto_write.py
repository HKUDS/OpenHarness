"""Helpers for automatic durable memory writes."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openharness.engine.messages import ConversationMessage, TextBlock, ToolResultBlock, ToolUseBlock
from openharness.memory.manager import upsert_memory_entry
from openharness.memory.memdir import load_memory_review_snapshot
from openharness.personalization.extractor import extract_facts_from_text
from openharness.skills.loader import load_skill_registry, strip_skill_frontmatter

MEMORY_POLICY_SKILL_NAME = "durable-memory-policy"
MEMORY_REVIEW_SKILL_NAME = "durable-memory-reviewer"

AUTO_MEMORY_REVIEW_SYSTEM_PROMPT = """You are OpenHarness's internal durable-memory reviewer.

Your operating procedure is provided by the loaded durable-memory-policy and durable-memory-reviewer skills.
Follow that skill when deciding whether the completed turn should update persistent memory.
If no memory update is needed, reply with exactly NO_MEMORY_UPDATE.
After finishing all required writes, reply with exactly MEMORY_REVIEW_COMPLETE."""


def _truncate(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def _message_text(message: ConversationMessage) -> str:
    chunks: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock) and block.text.strip():
            chunks.append(block.text.strip())
        elif isinstance(block, ToolResultBlock) and block.content.strip():
            chunks.append(f"[tool_result]\n{block.content.strip()}")
        elif isinstance(block, ToolUseBlock):
            chunks.append(f"[tool_use] {block.name}")
    return "\n\n".join(chunk for chunk in chunks if chunk)


def _load_memory_skill_contents(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings=None,
) -> dict[str, str]:
    registry = load_skill_registry(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        settings=settings,
    )
    contents: dict[str, str] = {}
    for skill_name in (MEMORY_POLICY_SKILL_NAME, MEMORY_REVIEW_SKILL_NAME):
        skill = registry.get(skill_name)
        contents[skill_name] = strip_skill_frontmatter(skill.content).strip() if skill is not None else ""
    return contents


def load_memory_policy_skill_content(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings=None,
) -> str:
    """Load the shared durable-memory policy skill content."""
    return _load_memory_skill_contents(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        settings=settings,
    ).get(MEMORY_POLICY_SKILL_NAME, "")


def load_memory_review_skill_content(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
) -> str:
    """Load the durable-memory-reviewer skill content.

    This makes automatic memory review follow the same skill loading path as the
    interactive runtime, so bundled, user, or plugin overrides can replace the
    default reviewer instructions.
    """
    return _load_memory_skill_contents(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
    ).get(MEMORY_REVIEW_SKILL_NAME, "")


def build_turn_memory_review_prompt(
    messages: list[ConversationMessage],
    cwd: str | Path,
    *,
    max_messages: int = 8,
    repeat_prompt_candidates: list[dict[str, object]] | None = None,
) -> str:
    """Build the transcript payload for one automatic memory review pass."""
    recent_messages = messages[-max_messages:]
    rendered_messages: list[str] = []
    extracted_text_parts: list[str] = []

    for message in recent_messages:
        rendered = _message_text(message)
        if not rendered:
            continue
        extracted_text_parts.append(rendered)
        rendered_messages.append(f"## {message.role.title()}\n{_truncate(rendered, 1600)}")

    lines = ["# Completed Conversation Turn", ""]
    if rendered_messages:
        lines.extend(rendered_messages)
    else:
        lines.append("(No textual content to review.)")

    fact_candidates = extract_facts_from_text("\n".join(extracted_text_parts))
    if fact_candidates:
        lines.extend(["", "# Deterministic Fact Candidates"])
        for fact in fact_candidates:
            lines.append(f"- {fact['key']} -> {fact['value']}")

    memory_snapshot = load_memory_review_snapshot(cwd, max_entries=12)
    if memory_snapshot:
        lines.extend(["", memory_snapshot])

    if repeat_prompt_candidates:
        lines.extend(["", "# Repeated User Prompt Candidates"])
        for candidate in repeat_prompt_candidates:
            prompt_text = str(candidate.get("prompt") or "").strip()
            count = candidate.get("count", 0)
            count_value = int(count) if isinstance(count, (int, float)) else 0
            if not prompt_text or count_value <= 0:
                continue
            lines.append(f"- Asked {count_value} times this session: {prompt_text}")
        lines.extend(
            [
                "",
                "Repeated prompts can indicate a stable workflow preference or default tool choice when they are likely to matter in future sessions.",
            ]
        )

    lines.extend(
        [
            "",
            "# Review Instruction",
            "Write memory only when the value is clearly durable across future sessions.",
        ]
    )
    return "\n".join(lines)


def build_turn_memory_review_messages(
    messages: list[ConversationMessage],
    cwd: str | Path,
    *,
    max_messages: int = 8,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    repeat_prompt_candidates: list[dict[str, object]] | None = None,
) -> list[ConversationMessage]:
    """Build the full message list for one automatic memory review pass."""
    review_prompt = build_turn_memory_review_prompt(
        messages,
        cwd,
        max_messages=max_messages,
        repeat_prompt_candidates=repeat_prompt_candidates,
    )
    if not review_prompt.strip():
        return []

    review_messages: list[ConversationMessage] = []
    skill_contents = _load_memory_skill_contents(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
    )
    policy_content = skill_contents.get(MEMORY_POLICY_SKILL_NAME, "")
    reviewer_content = skill_contents.get(MEMORY_REVIEW_SKILL_NAME, "")
    if policy_content:
        review_messages.append(ConversationMessage.from_user_text(policy_content))
    if reviewer_content:
        review_messages.append(ConversationMessage.from_user_text(reviewer_content))
    review_messages.append(ConversationMessage.from_user_text(review_prompt))
    return review_messages


def sync_fact_memories(cwd: str | Path, facts: list[dict]) -> int:
    """Persist extracted durable facts into project memory as keyed entries."""
    changed = 0
    for fact in facts:
        key = str(fact.get("key") or "").strip()
        value = str(fact.get("value") or "").strip()
        label = str(fact.get("label") or fact.get("type") or "Fact").strip()
        fact_type = str(fact.get("type") or "environment").strip()
        if not key or not value:
            continue
        title = f"{label}: {value}"
        description = f"Auto-captured durable fact for {label.lower()}"
        content = (
            f"{label}: `{value}`\n\n"
            f"Captured automatically from conversation history as durable {fact_type.replace('_', ' ')} context."
        )
        _, status = upsert_memory_entry(
            cwd,
            key=key,
            title=title,
            description=description,
            memory_type=fact_type,
            content=content,
        )
        if status != "unchanged":
            changed += 1
    return changed