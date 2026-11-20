"""Core engine exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from openharness.engine.messages import (
        ConversationMessage,
        ImageBlock,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
    )
    from openharness.engine.query_engine import QueryEngine
    from openharness.engine.stream_events import (
        AssistantTextDelta,
        AssistantThinkingDelta,
        AssistantTurnComplete,
        ToolExecutionCompleted,
        ToolExecutionStarted,
    )

__all__ = [
    "AssistantTextDelta",
    "AssistantThinkingDelta",
    "AssistantTurnComplete",
    "ConversationMessage",
    "ImageBlock",
    "QueryEngine",
    "TextBlock",
    "ToolExecutionCompleted",
    "ToolExecutionStarted",
    "ToolResultBlock",
    "ToolUseBlock",
]


def __getattr__(name: str):
    if name in {"ConversationMessage", "ImageBlock", "TextBlock", "ToolResultBlock", "ToolUseBlock"}:
        from openharness.engine.messages import (
            ConversationMessage,
            ImageBlock,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        return {
            "ConversationMessage": ConversationMessage,
            "ImageBlock": ImageBlock,
            "TextBlock": TextBlock,
            "ToolResultBlock": ToolResultBlock,
            "ToolUseBlock": ToolUseBlock,
        }[name]

    if name == "QueryEngine":
        from openharness.engine.query_engine import QueryEngine

        return QueryEngine

    if name in {
        "AssistantTextDelta",
        "AssistantThinkingDelta",
        "AssistantTurnComplete",
        "ToolExecutionCompleted",
        "ToolExecutionStarted",
    }:
        from openharness.engine.stream_events import (
            AssistantTextDelta,
            AssistantThinkingDelta,
            AssistantTurnComplete,
            ToolExecutionCompleted,
            ToolExecutionStarted,
        )

        return {
            "AssistantTextDelta": AssistantTextDelta,
            "AssistantThinkingDelta": AssistantThinkingDelta,
            "AssistantTurnComplete": AssistantTurnComplete,
            "ToolExecutionCompleted": ToolExecutionCompleted,
            "ToolExecutionStarted": ToolExecutionStarted,
        }[name]

    raise AttributeError(name)
