from __future__ import annotations

from openharness.engine.messages import (
    ConversationMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    sanitize_conversation_messages,
)


def test_sanitize_conversation_messages_keeps_complete_tool_turn():
    messages = [
        ConversationMessage.from_user_text("edit the file"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="write_file:234", name="write_file", input={"path": "x"})],
        ),
        ConversationMessage(
            role="user",
            content=[ToolResultBlock(tool_use_id="write_file:234", content="ok", is_error=False)],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == messages


def test_sanitize_conversation_messages_drops_dangling_trailing_tool_use():
    messages = [
        ConversationMessage.from_user_text("edit the file"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="write_file:234", name="write_file", input={"path": "x"})],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == [ConversationMessage.from_user_text("edit the file")]


def test_sanitize_conversation_messages_drops_orphan_tool_results_but_keeps_user_text():
    messages = [
        ConversationMessage.from_user_text("hello"),
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="missing_call", content="stale", is_error=True),
                TextBlock(text="new prompt"),
            ],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == [
        ConversationMessage.from_user_text("hello"),
        ConversationMessage(role="user", content=[TextBlock(text="new prompt")]),
    ]
