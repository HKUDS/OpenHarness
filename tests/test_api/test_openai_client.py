"""Tests for the OpenAI-compatible API client."""

from __future__ import annotations

import json

import httpx

import pytest

from openharness.api.client import ApiMessageRequest
from openharness.api.openai_client import (
    OpenAICompatibleClient,
    _convert_messages_to_openai,
    _convert_tools_to_openai,
    _normalize_openai_base_url,
    _strip_think_blocks,
    _token_limit_param_for_model,
)
from openharness.engine.messages import (
    ConversationMessage,
    ImageBlock,
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

    def test_user_multimodal_message(self):
        messages = [
            ConversationMessage(
                role="user",
                content=[
                    TextBlock(text="Please describe this image."),
                    ImageBlock(media_type="image/png", data="YWJj", source_path="/tmp/example.png"),
                ],
            )
        ]
        result = _convert_messages_to_openai(messages, None)
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0] == {"type": "text", "text": "Please describe this image."}
        assert result[0]["content"][1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,YWJj"},
        }

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


class TestNormalizeOpenAIBaseUrl:
    def test_preserves_explicit_v1_path(self):
        assert _normalize_openai_base_url("https://jarodfund.xyz/openai/v1") == "https://jarodfund.xyz/openai/v1"

    def test_adds_default_v1_when_path_missing(self):
        assert _normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"

    def test_strips_trailing_slash_without_dropping_path(self):
        assert _normalize_openai_base_url("https://api.example.com/openai/v1/") == "https://api.example.com/openai/v1"


class TestTokenLimitParams:
    def test_gpt5_uses_max_completion_tokens(self):
        assert _token_limit_param_for_model("gpt-5.4", 4096) == {"max_completion_tokens": 4096}

    def test_legacy_chat_models_keep_max_tokens(self):
        assert _token_limit_param_for_model("gpt-4o", 4096) == {"max_tokens": 4096}


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class _FakeChunk:
    def __init__(self) -> None:
        self.choices = []
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs

        async def _stream():
            yield _FakeChunk()

        return _stream()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


@pytest.mark.asyncio
async def test_openai_client_uses_full_base_url_path_for_requests():
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-4o-mini",
                "choices": [],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    transport = httpx.MockTransport(_handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://jarodfund.xyz/openai/v1",
    )
    client._client._client = http_client

    request = ApiMessageRequest(
        model="gpt-4o-mini",
        messages=[ConversationMessage.from_user_text("Explain the codebase")],
    )
    events = [event async for event in client.stream_message(request)]

    assert events
    assert seen_urls == ["https://jarodfund.xyz/openai/v1/chat/completions"]
    await http_client.aclose()


def test_openai_client_init_normalizes_base_url(monkeypatch):
    captured: dict[str, object] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.openai_client.AsyncOpenAI", _StubAsyncOpenAI)
    OpenAICompatibleClient(api_key="test-key", base_url="https://jarodfund.xyz/openai/v1/")

    assert captured["base_url"] == "https://jarodfund.xyz/openai/v1"


def test_openai_client_init_passes_timeout(monkeypatch):
    captured: dict[str, object] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.openai_client.AsyncOpenAI", _StubAsyncOpenAI)
    OpenAICompatibleClient(api_key="test-key", timeout=45.0)

    assert captured["timeout"] == 45.0



class TestStreamMessageTokenParams:
    @pytest.mark.asyncio
    async def test_gpt5_stream_uses_max_completion_tokens(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.chat.completions.last_kwargs is not None
        assert "max_completion_tokens" in fake_sdk.chat.completions.last_kwargs
        assert "max_tokens" not in fake_sdk.chat.completions.last_kwargs

    @pytest.mark.asyncio
    async def test_gpt4o_stream_keeps_max_tokens(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-4o",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.chat.completions.last_kwargs is not None
        assert "max_tokens" in fake_sdk.chat.completions.last_kwargs
        assert "max_completion_tokens" not in fake_sdk.chat.completions.last_kwargs


class TestStripThinkBlocks:
    """Unit tests for the _strip_think_blocks streaming helper."""

    def test_no_think_tags_passthrough(self):
        visible, leftover = _strip_think_blocks("Hello world")
        assert visible == "Hello world"
        assert leftover == ""

    def test_complete_think_block_removed(self):
        visible, leftover = _strip_think_blocks("<think>internal reasoning</think>answer")
        assert visible == "answer"
        assert leftover == ""

    def test_multiline_think_block_removed(self):
        buf = "<think>\nstep 1\nstep 2\n</think>final answer"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "final answer"
        assert leftover == ""

    def test_unclosed_think_held_in_leftover(self):
        # Streaming chunk ends before </think> arrives
        visible, leftover = _strip_think_blocks("prefix<think>partial reasoning")
        assert visible == "prefix"
        assert leftover == "<think>partial reasoning"

    def test_empty_string(self):
        visible, leftover = _strip_think_blocks("")
        assert visible == ""
        assert leftover == ""

    def test_only_think_block(self):
        visible, leftover = _strip_think_blocks("<think>all hidden</think>")
        assert visible == ""
        assert leftover == ""

    def test_multiple_think_blocks(self):
        buf = "<think>a</think>text1<think>b</think>text2"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "text1text2"
        assert leftover == ""

    def test_text_before_unclosed_think(self):
        visible, leftover = _strip_think_blocks("before<think>unclosed")
        assert visible == "before"
        assert leftover == "<think>unclosed"

    def test_closed_then_unclosed(self):
        # One complete block followed by a new unclosed one (cross-chunk scenario)
        buf = "<think>done</think>visible<think>still open"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "visible"
        assert leftover == "<think>still open"

    def test_partial_open_tag_is_held_for_next_chunk(self):
        visible, leftover = _strip_think_blocks("prefix<thi")
        assert visible == "prefix"
        assert leftover == "<thi"

    def test_partial_open_tag_after_closed_block_is_held(self):
        buf = "<think>done</think>visible<thi"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "visible"
        assert leftover == "<thi"

    def test_split_open_tag_across_chunks_does_not_leak_reasoning(self):
        buf = ""

        buf += "<thi"
        visible, buf = _strip_think_blocks(buf)
        assert visible == ""
        assert buf == "<thi"

        buf += "nk>secret</think>answer"
        visible, buf = _strip_think_blocks(buf)
        assert visible == "answer"
        assert buf == ""
