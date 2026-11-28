from __future__ import annotations

from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock
from openharness.api.client import AnthropicApiClient, OAUTH_BETA_HEADER


def test_anthropic_client_adds_oauth_beta_header(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(auth_token="oauth-token")

    assert captured["auth_token"] == "oauth-token"
    assert captured["default_headers"] == {"anthropic-beta": OAUTH_BETA_HEADER}


def test_anthropic_client_uses_api_key_without_oauth_beta(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.client.AsyncAnthropic", _FakeAsyncAnthropic)

    AnthropicApiClient(api_key="api-key")

    assert captured["api_key"] == "api-key"
    assert "default_headers" not in captured


def test_anthropic_client_adds_claude_oauth_identity_headers(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.client.AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setattr(
        "openharness.auth.external.get_claude_code_version",
        lambda: "2.1.92",
    )
    monkeypatch.setattr(
        "openharness.auth.external.get_claude_code_session_id",
        lambda: "session-123",
    )
    monkeypatch.setattr(
        "openharness.api.client.get_claude_code_session_id",
        lambda: "session-123",
    )
    monkeypatch.setattr(
        "openharness.api.client.claude_attribution_header",
        lambda: "x-anthropic-billing-header: cc_version=2.1.92; cc_entrypoint=cli;",
    )

    AnthropicApiClient(auth_token="oauth-token", claude_oauth=True)

    headers = captured["default_headers"]
    assert captured["auth_token"] == "oauth-token"
    assert headers["x-app"] == "cli"
    assert headers["user-agent"] == "claude-cli/2.1.92 (external, cli)"
    assert headers["X-Claude-Code-Session-Id"] == "session-123"
    assert "oauth-2025-04-20" in headers["anthropic-beta"]
    assert "claude-code-20250219" in headers["anthropic-beta"]


def test_conversation_message_serializes_image_block_for_anthropic():
    message = ConversationMessage(
        role="user",
        content=[
            TextBlock(text="Describe this."),
            ImageBlock(media_type="image/png", data="YWJj", source_path="/tmp/example.png"),
        ],
    )

    assert message.to_api_param() == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this."},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "YWJj",
                },
            },
        ],
    }


def test_anthropic_client_refreshes_claude_token_on_request(monkeypatch):
    captured_tokens: list[str] = []

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def __aiter__(self):
            if False:
                yield None
            return

        async def get_final_message(self):
            class _Usage:
                input_tokens = 1
                output_tokens = 1

            class _Message:
                usage = _Usage()
                stop_reason = "end_turn"
                role = "assistant"
                content = []

            return _Message()

    class _FakeMessages:
        def __init__(self):
            self.last_params = None

        def stream(self, **params):
            self.last_params = params
            return _FakeStream()

    class _FakeBeta:
        def __init__(self):
            self.messages = _FakeMessages()

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured_tokens.append(kwargs["auth_token"])
            self.beta = _FakeBeta()
            self.messages = _FakeMessages()

    monkeypatch.setattr("openharness.api.client.AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setattr(
        "openharness.auth.external.get_claude_code_session_id",
        lambda: "session-123",
    )
    monkeypatch.setattr(
        "openharness.api.client.get_claude_code_session_id",
        lambda: "session-123",
    )
    monkeypatch.setattr(
        "openharness.api.client.claude_attribution_header",
        lambda: "x-anthropic-billing-header: cc_version=2.1.92; cc_entrypoint=cli;",
    )

    current_token = {"value": "initial-token"}

    client = AnthropicApiClient(
        auth_token="initial-token",
        claude_oauth=True,
        auth_token_resolver=lambda: current_token["value"],
    )
    current_token["value"] = "refreshed-token"

    from openharness.api.client import ApiMessageRequest

    async def _run():
        events = []
        async for event in client.stream_message(
            ApiMessageRequest(
                model="claude-sonnet-4-6",
                messages=[],
                system_prompt="system prompt",
            )
        ):
            events.append(event)
        return events

    import asyncio

    events = asyncio.run(_run())

    assert captured_tokens == ["initial-token", "refreshed-token"]
    assert events
    assert client._client.beta.messages.last_params["metadata"] == {
        "user_id": '{"device_id":"openharness","session_id":"session-123","account_uuid":""}'
    }
    assert "oauth-2025-04-20" in client._client.beta.messages.last_params["betas"]
    system_blocks = client._client.beta.messages.last_params["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["type"] == "text"
    assert system_blocks[0]["text"].startswith(
        "x-anthropic-billing-header: cc_version=2.1.92; cc_entrypoint=cli;\n"
    )
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}


def _make_fake_anthropic_env(monkeypatch, *, usage_obj=None):
    captured: dict[str, object] = {}

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def __aiter__(self):
            if False:
                yield None
            return

        async def get_final_message(self):
            class _DefaultUsage:
                input_tokens = 12
                output_tokens = 4
                cache_creation_input_tokens = 1200
                cache_read_input_tokens = 800

            class _Message:
                usage = usage_obj if usage_obj is not None else _DefaultUsage()
                stop_reason = "end_turn"
                role = "assistant"
                content = []

            return _Message()

    class _FakeMessages:
        def __init__(self):
            self.last_params = None

        def stream(self, **params):
            self.last_params = params
            captured["last_params"] = params
            return _FakeStream()

    class _FakeBeta:
        def __init__(self):
            self.messages = _FakeMessages()

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.beta = _FakeBeta()
            self.messages = _FakeMessages()

    monkeypatch.setattr("openharness.api.client.AsyncAnthropic", _FakeAsyncAnthropic)
    return captured


def test_anthropic_client_places_prompt_caching_breakpoints_and_parses_cached_usage(monkeypatch):
    import asyncio
    from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest

    captured = _make_fake_anthropic_env(monkeypatch)
    client = AnthropicApiClient(api_key="test-key")

    tools = [
        {"name": "read_file", "description": "Read", "input_schema": {"type": "object"}},
        {"name": "bash", "description": "Shell", "input_schema": {"type": "object"}},
    ]
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="Inspect the repo")]),
    ]

    async def _run():
        return [
            ev
            async for ev in client.stream_message(
                ApiMessageRequest(
                    model="claude-sonnet-4-6",
                    messages=messages,
                    system_prompt="Shared system prompt",
                    tools=tools,
                )
            )
        ]

    events = asyncio.run(_run())
    params = captured["last_params"]

    # Caller inputs are not mutated in-place.
    assert "cache_control" not in tools[0]
    assert "cache_control" not in tools[1]

    # Tools get breakpoint on last tool only.
    assert "cache_control" not in params["tools"][0]
    assert params["tools"][1]["cache_control"] == {"type": "ephemeral"}

    # System prompt is wrapped as a cacheable text block.
    assert params["system"] == [
        {
            "type": "text",
            "text": "Shared system prompt",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # Latest cacheable message block gets a breakpoint, total <= 4.
    assert params["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}

    complete = [ev for ev in events if isinstance(ev, ApiMessageCompleteEvent)][0]
    assert complete.usage.input_tokens == 12
    assert complete.usage.output_tokens == 4
    assert complete.usage.cache_creation_input_tokens == 1200
    assert complete.usage.cache_read_input_tokens == 800
    assert complete.usage.total_input_tokens == 2012
    assert complete.usage.total_tokens == 2016


def test_apply_prompt_caching_respects_max_four_breakpoints_and_skips_empty_blocks():
    from openharness.api.client import _apply_prompt_caching, _count_cache_breakpoints

    # Pre-existing 3 breakpoints in messages + 1 in tools leaves 0 budget for system.
    params = {
        "system": "System instructions",
        "tools": [{"name": "t1", "input_schema": {"type": "object"}}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": "b", "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": "c", "cache_control": {"type": "ephemeral"}},
                ],
            }
        ],
    }
    _apply_prompt_caching(params)
    assert _count_cache_breakpoints(params) == 4
    assert params["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["system"] == "System instructions"

    # Empty text blocks and string content must not receive invalid cache_control.
    sparse_params = {
        "system": "   ",
        "messages": [
            {"role": "user", "content": "plain string"},
            {"role": "assistant", "content": [{"type": "thinking", "thinking": "..."}]},
            {"role": "user", "content": [{"type": "text", "text": ""}]},
        ],
    }
    _apply_prompt_caching(sparse_params)
    assert _count_cache_breakpoints(sparse_params) == 0
    assert sparse_params["system"] == "   "
    assert sparse_params["messages"][0]["content"] == "plain string"


def test_cost_tracker_accumulates_cached_token_usage():
    from openharness.api.usage import UsageSnapshot
    from openharness.engine.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.add(
        UsageSnapshot(
            input_tokens=10,
            output_tokens=5,
            cache_creation_input_tokens=1000,
            cache_read_input_tokens=0,
        )
    )
    tracker.add(
        UsageSnapshot(
            input_tokens=20,
            output_tokens=10,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=1000,
        )
    )

    total = tracker.total
    assert total.input_tokens == 30
    assert total.output_tokens == 15
    assert total.cache_creation_input_tokens == 1000
    assert total.cache_read_input_tokens == 1000
    assert total.total_input_tokens == 2030
    assert total.total_tokens == 2045


def test_anthropic_client_prompt_caching_can_be_disabled(monkeypatch):
    import asyncio
    from openharness.api.client import ApiMessageRequest

    captured = _make_fake_anthropic_env(monkeypatch)
    client = AnthropicApiClient(api_key="test-key", prompt_caching=False)

    async def _run():
        return [
            ev
            async for ev in client.stream_message(
                ApiMessageRequest(
                    model="claude-sonnet-4-6",
                    messages=[ConversationMessage.from_user_text("hi")],
                    system_prompt="System prompt",
                    tools=[{"name": "bash", "input_schema": {"type": "object"}}],
                )
            )
        ]

    asyncio.run(_run())
    params = captured["last_params"]
    assert params["system"] == "System prompt"
    assert "cache_control" not in params["tools"][0]
    assert "cache_control" not in params["messages"][0]["content"][0]
