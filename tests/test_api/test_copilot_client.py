"""Tests for the GitHub Copilot API client."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from openharness.api.copilot_auth import (
    save_copilot_auth,
)
from openharness.api.copilot_client import CopilotClient
from openharness.api.errors import AuthenticationFailure
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


class FakeInnerClient:
    """Stand-in for ``OpenAICompatibleClient`` returned after init."""

    def __init__(self) -> None:
        self.last_request: ApiMessageRequest | None = None
        self._client = type("FakeSDKClient", (), {"api_key": None})()

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        self.last_request = request
        msg = ConversationMessage(role="assistant", content=[TextBlock(text="Hello from Copilot")])
        yield ApiTextDeltaEvent(text="Hello from Copilot")
        yield ApiMessageCompleteEvent(
            message=msg,
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestCopilotClientInit:
    """Test CopilotClient construction and auth validation."""

    def test_raises_when_no_token(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        with pytest.raises(AuthenticationFailure, match="No GitHub Copilot token"):
            CopilotClient()

    def test_succeeds_with_explicit_token(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        client = CopilotClient(github_token="gho_explicit")
        assert client._token == "gho_explicit"
        assert client._enterprise_url is None

    def test_loads_from_persisted_token(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_persisted")
        client = CopilotClient()
        assert client._token == "gho_persisted"

    def test_explicit_token_takes_precedence(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_persisted")
        client = CopilotClient(github_token="gho_override")
        assert client._token == "gho_override"

    def test_enterprise_url_from_auth_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_ent", enterprise_url="company.ghe.com")
        client = CopilotClient()
        assert client._enterprise_url == "company.ghe.com"

    def test_explicit_enterprise_url_takes_precedence(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_ent", enterprise_url="old.ghe.com")
        client = CopilotClient(github_token="gho_x", enterprise_url="new.ghe.com")
        assert client._enterprise_url == "new.ghe.com"

    def test_inner_client_uses_correct_api_base(self, tmp_path: Path, monkeypatch):
        """The inner OpenAI client should be pointed at the correct API base."""
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        client = CopilotClient(github_token="gho_test")
        # Default: public GitHub
        assert client._inner._client.base_url is not None

    def test_inner_client_enterprise_base(self, tmp_path: Path, monkeypatch):
        """Enterprise URL should produce the correct Copilot API base."""
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        save_copilot_auth("gho_ent", enterprise_url="company.ghe.com")
        client = CopilotClient()
        # The inner client should use the enterprise API base
        base = str(client._inner._client.base_url)
        assert "copilot-api.company.ghe.com" in base


# ---------------------------------------------------------------------------
# stream_message tests
# ---------------------------------------------------------------------------


class TestStreamMessage:
    """Test that stream_message delegates to the inner client."""

    @pytest.mark.asyncio
    async def test_delegates_to_inner_client(self, tmp_path: Path, monkeypatch):
        """stream_message should yield events from the inner client's stream_message."""
        monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "cfg"))
        fake_inner = FakeInnerClient()

        client = CopilotClient(github_token="gho_stream")
        # Inject the fake inner client directly
        client._inner = fake_inner

        request = ApiMessageRequest(
            model="gpt-4o",
            messages=[ConversationMessage.from_user_text("Hello")],
        )

        events: list[ApiStreamEvent] = []
        async for event in client.stream_message(request):
            events.append(event)

        assert len(events) == 2
        assert isinstance(events[0], ApiTextDeltaEvent)
        assert events[0].text == "Hello from Copilot"
        assert isinstance(events[1], ApiMessageCompleteEvent)
        assert events[1].stop_reason == "end_turn"
        assert fake_inner.last_request == request
