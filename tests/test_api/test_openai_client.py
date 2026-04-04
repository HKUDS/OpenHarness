"""Tests for the OpenAI-compatible API client."""

from __future__ import annotations

import json

from openharness.api.openai_client import (
    _convert_messages_to_openai,
    _convert_tools_to_openai,
)
from openharness.engine.messages import (
    ConversationMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class TestConvertToolsToOpenai:
    """Test Anthropic → OpenAI tool schema conversion."""

    def test_basic_tool(self):
        anthropic_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            }
        ]
        result = _convert_tools_to_openai(anthropic_tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["description"] == "Read a file"
        assert result[0]["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_empty_tools(self):
        assert _convert_tools_to_openai([]) == []

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {}},
            {"name": "tool_b", "description": "B", "input_schema": {}},
        ]
        result = _convert_tools_to_openai(tools)
        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool_a"
        assert result[1]["function"]["name"] == "tool_b"


class TestConvertMessagesToOpenai:
    """Test Anthropic → OpenAI message format conversion."""

    def test_system_prompt(self):
        messages: list[ConversationMessage] = []
        result = _convert_messages_to_openai(messages, "You are helpful.")
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."

    def test_no_system_prompt(self):
        messages = [ConversationMessage.from_user_text("hi")]
        result = _convert_messages_to_openai(messages, None)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hi"

    def test_user_text_message(self):
        messages = [ConversationMessage.from_user_text("hello")]
        result = _convert_messages_to_openai(messages, None)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}

    def test_assistant_text_message(self):
        msg = ConversationMessage(
            role="assistant", content=[TextBlock(text="I'll help you.")]
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll help you."
        assert "tool_calls" not in result[0]

    def test_assistant_with_tool_calls(self):
        msg = ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="Let me read that file."),
                ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"}),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me read that file."
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        assert json.loads(tc["function"]["arguments"]) == {"path": "/tmp/x"}

    def test_tool_result_messages(self):
        # User message containing tool results
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="call_1", content="file contents here", is_error=False
                ),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == "file contents here"

    def test_full_conversation_round_trip(self):
        """Test a complete user → assistant(tool_call) → user(tool_result) → assistant flow."""
        messages = [
            ConversationMessage.from_user_text("Read /tmp/test.txt"),
            ConversationMessage(
                role="assistant",
                content=[
                    TextBlock(text="I'll read that."),
                    ToolUseBlock(
                        id="call_abc", name="read_file", input={"path": "/tmp/test.txt"}
                    ),
                ],
            ),
            ConversationMessage(
                role="user",
                content=[
                    ToolResultBlock(
                        tool_use_id="call_abc", content="hello world", is_error=False
                    )
                ],
            ),
            ConversationMessage(
                role="assistant",
                content=[TextBlock(text="The file contains: hello world")],
            ),
        ]
        result = _convert_messages_to_openai(messages, "Be helpful")
        assert result[0] == {"role": "system", "content": "Be helpful"}
        assert result[1] == {"role": "user", "content": "Read /tmp/test.txt"}
        assert result[2]["role"] == "assistant"
        assert len(result[2]["tool_calls"]) == 1
        assert result[3]["role"] == "tool"
        assert result[3]["tool_call_id"] == "call_abc"
        assert result[4]["role"] == "assistant"
        assert result[4]["content"] == "The file contains: hello world"

    def test_multiple_tool_results(self):
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="c1", content="result1", is_error=False),
                ToolResultBlock(tool_use_id="c2", content="result2", is_error=True),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "c1"
        assert result[1]["tool_call_id"] == "c2"
