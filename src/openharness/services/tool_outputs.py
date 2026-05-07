"""Tool-output context budget helpers."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

DEFAULT_TOOL_OUTPUT_INLINE_CHARS = 16_000
DEFAULT_TOOL_OUTPUT_PREVIEW_CHARS = 3_000
DEFAULT_MICROCOMPACT_TOOL_RESULT_CHARS = 4_000


def _read_positive_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        log.warning("Ignoring invalid %s=%r", name, raw)
        return default


def tool_output_inline_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_INLINE_CHARS",
        DEFAULT_TOOL_OUTPUT_INLINE_CHARS,
        minimum=256,
    )


def tool_output_preview_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_PREVIEW_CHARS",
        DEFAULT_TOOL_OUTPUT_PREVIEW_CHARS,
        minimum=128,
    )


def microcompact_tool_result_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_MICROCOMPACT_TOOL_RESULT_CHARS",
        DEFAULT_MICROCOMPACT_TOOL_RESULT_CHARS,
        minimum=256,
    )


def is_microcompactable_tool_result(tool_name: str, content: str) -> bool:
    """Return True when a tool result should be eligible for old-result clearing."""
    normalized = tool_name.strip()
    if normalized.startswith("mcp__"):
        return True
    return len(content) >= microcompact_tool_result_chars()
