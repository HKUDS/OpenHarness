from __future__ import annotations

import json
from typing import Any

import pytest

from openharness.api.client import ApiMessageRequest, ApiMessageCompleteEvent, ApiTextDeltaEvent
from openharness.api.codex_client import (
    CodexApiClient,
    _convert_messages_to_codex,
    _format_codex_stream_error,
    _resolve_codex_url,
)
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock, ToolResultBlock, ToolUseBlock


class _FakeStreamResponse:
    def __init__(self, *, status_code: int = 200, lines: list[str] | None = None, body: str = "") -> None:
        self.status_code = status_code
        self._lines = lines or []
        self._body = body.encode("utf-8")

    async def __aenter__(self) -> "_FakeStreamResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncClient:
    def __init__(self, response: _FakeStreamResponse, sink: dict[str, Any]) -> None:
        self._response = response
        self._sink = sink

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        self._sink["method"] = method
        self._sink["url"] = url
        self._sink["headers"] = headers
        self._sink["json"] = json
        return self._response


def _b64url(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fake_codex_token() -> str:
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct_test"}}
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}.sig"


def test_convert_messages_to_codex():
    messages = [
        ConversationMessage.from_user_text("Inspect file"),
        ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="I'll inspect it."),
                ToolUseBlock(id="call_123", name="read_file", input={"path": "README.md"}),
            ],
        ),
        ConversationMessage(
            role="user",
            content=[ToolResultBlock(tool_use_id="call_123", content="hello", is_error=False)],
        ),
    ]

    converted = _convert_messages_to_codex(messages)

    assert converted[0] == {
        "role": "user",
        "content": [{"type": "input_text", "text": "Inspect file"}],
    }
    assert converted[1]["type"] == "message"
    assert converted[1]["role"] == "assistant"
    assert converted[2]["type"] == "function_call"
    assert converted[2]["call_id"] == "call_123"
    assert json.loads(converted[2]["arguments"]) == {"path": "README.md"}
    assert converted[3] == {
        "type": "function_call_output",
        "call_id": "call_123",
        "output": "hello",
    }


def test_convert_user_message_with_tool_result_before_text_to_codex():
    messages = [
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="call_123", content="done", is_error=False),
                TextBlock(text="next request"),
            ],
        )
    ]

    converted = _convert_messages_to_codex(messages)

    assert converted == [
        {"type": "function_call_output", "call_id": "call_123", "output": "done"},
        {"role": "user", "content": [{"type": "input_text", "text": "next request"}]},
    ]



def test_convert_multimodal_user_message_to_codex():
    messages = [
        ConversationMessage(
            role="user",
            content=[
                TextBlock(text="What is in this image?"),
                ImageBlock(media_type="image/png", data="YWJj", source_path="/tmp/example.png"),
            ],
        )
    ]

    converted = _convert_messages_to_codex(messages)

    assert converted == [{
        "role": "user",
        "content": [
            {"type": "input_text", "text": "What is in this image?"},
            {"type": "input_image", "image_url": "data:image/png;base64,YWJj"},
        ],
    }]


def test_resolve_codex_url_ignores_unrelated_base_url():
    assert _resolve_codex_url("https://api.moonshot.cn/anthropic") == "https://chatgpt.com/backend-api/codex/responses"


def test_format_codex_stream_error_includes_code_and_request_id():
    message = _format_codex_stream_error(
        {
            "type": "error",
            "message": "Upstream overloaded",
            "code": "overloaded",
            "request_id": "req_123",
        },
        fallback="Codex error",
    )
    assert message == "Upstream overloaded (code=overloaded) [request_id=req_123]"


@pytest.mark.asyncio
async def test_codex_client_streams_text(monkeypatch):
    sink: dict[str, Any] = {}
    response = _FakeStreamResponse(
        lines=[
            'event: response.output_item.added',
            'data: {"type":"response.output_item.added","item":{"id":"msg_1","type":"message","content":[],"role":"assistant"}}',
            "",
            'event: response.output_text.delta',
            'data: {"type":"response.output_text.delta","delta":"CODE"}',
            "",
            'event: response.output_text.delta',
            'data: {"type":"response.output_text.delta","delta":"X_OK"}',
            "",
            'event: response.output_item.done',
            'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","content":[{"type":"output_text","text":"CODEX_OK","annotations":[]}]}}',
            "",
            'event: response.completed',
            'data: {"type":"response.completed","response":{"status":"completed","usage":{"input_tokens":12,"output_tokens":3}}}',
            "",
        ]
    )
    monkeypatch.setattr(
        "openharness.api.codex_client.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response, sink),
    )

    client = CodexApiClient(_fake_codex_token())
    request = ApiMessageRequest(
        model="gpt-5.4",
        messages=[ConversationMessage.from_user_text("hi")],
        system_prompt="Be helpful.",
    )
    events = [event async for event in client.stream_message(request)]

    assert [event.text for event in events if isinstance(event, ApiTextDeltaEvent)] == ["CODE", "X_OK"]
    complete = next(event for event in events if isinstance(event, ApiMessageCompleteEvent))
    assert complete.message.text == "CODEX_OK"
    assert complete.usage.input_tokens == 12
    assert complete.usage.output_tokens == 3
    assert sink["url"].endswith("/codex/responses")
    assert sink["json"]["instructions"] == "Be helpful."
    assert sink["headers"]["OpenAI-Beta"] == "responses=experimental"


@pytest.mark.asyncio
async def test_codex_client_emits_tool_use(monkeypatch):
    sink: dict[str, Any] = {}
    response = _FakeStreamResponse(
        lines=[
            'data: {"type":"response.output_item.added","item":{"id":"fc_1","type":"function_call","arguments":"","call_id":"call_abc","name":"glob"}}',
            "",
            'data: {"type":"response.output_item.done","item":{"id":"fc_1","type":"function_call","arguments":"{\\"pattern\\":\\"src/**/*.py\\"}","call_id":"call_abc","name":"glob"}}',
            "",
            'data: {"type":"response.completed","response":{"status":"completed","usage":{"input_tokens":7,"output_tokens":2}}}',
            "",
        ]
    )
    monkeypatch.setattr(
        "openharness.api.codex_client.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response, sink),
    )

    client = CodexApiClient(_fake_codex_token())
    request = ApiMessageRequest(
        model="gpt-5.4",
        messages=[ConversationMessage.from_user_text("glob")],
        system_prompt="Use tools.",
        tools=[{"name": "glob", "description": "find files", "input_schema": {"type": "object"}}],
    )
    events = [event async for event in client.stream_message(request)]

    complete = next(event for event in events if isinstance(event, ApiMessageCompleteEvent))
    assert complete.stop_reason == "tool_use"
    assert len(complete.message.tool_uses) == 1
    tool_use = complete.message.tool_uses[0]
    assert tool_use.id == "call_abc"
    assert tool_use.name == "glob"
    assert tool_use.input == {"pattern": "src/**/*.py"}
    assert sink["json"]["tools"][0]["name"] == "glob"
