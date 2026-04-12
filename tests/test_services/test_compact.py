"""Tests for compaction and token estimation helpers."""

from __future__ import annotations

import asyncio

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock, ToolUseBlock
from openharness.hooks import HookEvent
from openharness.services import (
    build_post_compact_messages,
    compact_conversation,
    compact_messages,
    estimate_conversation_tokens,
    estimate_message_tokens,
    estimate_tokens,
    summarize_messages,
)
from openharness.services.compact import (
    AutoCompactState,
    auto_compact_if_needed,
    get_autocompact_threshold,
    should_autocompact,
    try_context_collapse,
    try_session_memory_compaction,
)


def test_token_estimation_helpers():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_message_tokens(["abcd", "abcdefgh"]) == 3


def test_compact_and_summarize_messages():
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="first question")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="first answer")]),
        ConversationMessage(role="user", content=[TextBlock(text="second question")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="second answer")]),
    ]

    summary = summarize_messages(messages, max_messages=2)
    assert "user: second question" in summary
    assert "assistant: second answer" in summary

    compacted = compact_messages(messages, preserve_recent=2)
    assert len(compacted) == 3
    assert "[conversation summary]" in compacted[0].text
    assert estimate_conversation_tokens(compacted) >= 1


class _CompactApiClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def stream_message(self, request):
        del request
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if asyncio.iscoroutinefunction(response):
            await response()
            return
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=response)]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class _HookExecutorStub:
    def __init__(self) -> None:
        self.events: list[tuple[HookEvent, dict[str, object]]] = []

    async def execute(self, event: HookEvent, payload: dict[str, object]):
        self.events.append((event, payload))
        from openharness.hooks.types import AggregatedHookResult

        return AggregatedHookResult()


def test_try_session_memory_compaction_reduces_long_history():
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text=(f"user {index} " * 200).strip())])
        if index % 2 == 0
        else ConversationMessage(role="assistant", content=[TextBlock(text=(f"assistant {index} " * 200).strip())])
        for index in range(20)
    ]

    result = try_session_memory_compaction(messages)

    assert result is not None
    rebuilt = build_post_compact_messages(result)
    assert len(rebuilt) < len(messages)
    assert rebuilt[0].text.startswith("[Compact boundary marker]")
    assert any("Session memory summary" in message.text for message in rebuilt)


def test_try_context_collapse_trims_oversized_messages():
    giant = ("alpha " * 1200).strip()
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text=giant)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=giant)]),
        ConversationMessage(role="user", content=[TextBlock(text=giant)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=giant)]),
        ConversationMessage(role="user", content=[TextBlock(text=giant)]),
        ConversationMessage(role="assistant", content=[TextBlock(text="keep recent")]),
        ConversationMessage(role="user", content=[TextBlock(text="latest")]),
    ]

    result = try_context_collapse(messages, preserve_recent=2)

    assert result is not None
    assert "[collapsed" in result[0].text


@pytest.mark.asyncio
async def test_compact_conversation_retries_after_incomplete_response():
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="alpha")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="beta")]),
        ConversationMessage(role="user", content=[TextBlock(text="gamma")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="delta")]),
        ConversationMessage(role="user", content=[TextBlock(text="epsilon")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="zeta")]),
        ConversationMessage(role="user", content=[TextBlock(text="eta")]),
    ]

    compacted = await compact_conversation(
        messages,
        api_client=_CompactApiClient(["", "<summary>condensed</summary>"]),
        model="claude-test",
    )

    rebuilt = build_post_compact_messages(compacted)
    assert rebuilt[0].text.startswith("[Compact boundary marker]")
    assert any(message.text.startswith("This session is being continued") for message in rebuilt)


@pytest.mark.asyncio
async def test_compact_conversation_runs_hooks_and_preserves_carryover_state(tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00\x04\x00\x01\xf6\x178U"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    hook_executor = _HookExecutorStub()
    messages = [
        ConversationMessage(role="user", content=[ImageBlock.from_path(image_path)]),
        ConversationMessage(role="assistant", content=[TextBlock(text="Looking at the attachment")]),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(name="read_file", input={"path": str(image_path)})],
        ),
        ConversationMessage(role="user", content=[TextBlock(text="Please keep going")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="Working through it")]),
        ConversationMessage(role="user", content=[TextBlock(text="And preserve context")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="Sure")]),
    ]

    compacted = await compact_conversation(
        messages,
        api_client=_CompactApiClient(["<summary>condensed</summary>"]),
        model="claude-test",
        preserve_recent=2,
        hook_executor=hook_executor,
        carryover_metadata={
            "permission_mode": "plan",
            "session_id": "sess123",
            "task_focus_state": {
                "goal": "Confirm issue #98 and fix the logger formatting bug",
                "recent_goals": [
                    "Look into issue #98",
                    "Confirm issue #98 and fix the logger formatting bug",
                ],
                "active_artifacts": [str(image_path), "src/openharness/channels/impl/matrix.py:398"],
                "verified_state": ["Issue #98 is about logger placeholder formatting"],
                "next_step": "Patch the logger formatting and rerun focused tests",
            },
            "read_file_state": [
                {
                    "path": str(image_path),
                    "span": "lines 1-20",
                    "preview": "1\tPNG header",
                    "timestamp": 123.0,
                }
            ],
            "invoked_skills": ["pikastream-video-meeting"],
            "async_agent_state": ["Spawned async agent [task_id=task_123]"],
            "recent_work_log": ["Ran pytest -q tests/test_compact.py [41 passed]"],
            "recent_verified_work": [
                "Issue #98 is about logger placeholder formatting",
                "matrix.py still contains mixed {} / %s logging",
            ],
            "compact_last": {"checkpoint": "query_auto_triggered", "token_count": 12345},
        },
    )

    assert [event for event, _payload in hook_executor.events] == [HookEvent.PRE_COMPACT, HookEvent.POST_COMPACT]
    rebuilt = build_post_compact_messages(compacted)
    joined = "\n\n".join(message.text for message in rebuilt)
    assert rebuilt[0].text.startswith("[Compact boundary marker]")
    assert any(message.text.startswith("This session is being continued") for message in rebuilt)
    assert "[Compact attachment: task_focus]" in joined
    assert "Current working focus" in joined
    assert "logger formatting bug" in joined
    assert "[Compact attachment: recent_verified_work]" in joined
    assert "Issue #98 is about logger placeholder formatting" in joined
    assert "[Compact attachment: plan]" in joined
    assert "Plan mode is still active" in joined
    assert str(image_path) in joined
    assert "[Compact attachment: recent_files]" in joined
    assert "Recently read files" in joined
    assert "[Compact attachment: invoked_skills]" in joined
    assert "[Compact attachment: async_agents]" in joined
    assert "[Compact attachment: recent_work_log]" in joined
    assert "41 passed" in joined


@pytest.mark.asyncio
async def test_compact_post_messages_keep_boundary_summary_recent_then_attachments():
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="first")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="second")]),
        ConversationMessage(role="user", content=[TextBlock(text="third")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="fourth")]),
        ConversationMessage(role="user", content=[TextBlock(text="fifth")]),
        ConversationMessage(role="assistant", content=[TextBlock(text="sixth")]),
        ConversationMessage(role="user", content=[TextBlock(text="seventh")]),
    ]

    compacted = await compact_conversation(
        messages,
        api_client=_CompactApiClient(["<summary>condensed</summary>"]),
        model="claude-test",
        preserve_recent=2,
        carryover_metadata={
            "task_focus_state": {
                "goal": "Stabilize compact carry-over",
                "recent_goals": ["Stabilize compact carry-over"],
                "active_artifacts": ["/tmp/demo.py"],
                "verified_state": ["Focused compact test fixture prepared"],
                "next_step": "Run the focused compact tests",
            },
            "read_file_state": [{"path": "/tmp/demo.py", "span": "lines 1-20", "preview": "print('hi')"}],
            "recent_work_log": ["Ran pytest -q tests/test_services/test_compact.py [ok]"],
            "recent_verified_work": ["Focused compact test fixture prepared"],
        },
    )

    rebuilt = build_post_compact_messages(compacted)

    assert rebuilt[0].text.startswith("[Compact boundary marker]")
    assert rebuilt[1].text.startswith("This session is being continued")
    assert rebuilt[2].text == "sixth"
    assert rebuilt[3].text == "seventh"
    assert rebuilt[4].text.startswith("[Compact attachment:")
    assert any("[Compact attachment: task_focus]" in message.text for message in rebuilt)


@pytest.mark.asyncio
async def test_auto_compact_records_richer_checkpoint_metadata(monkeypatch):
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: True)
    long_text = "alpha " * 50000
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
    ]
    metadata: dict[str, object] = {}

    result, was_compacted = await auto_compact_if_needed(
        messages,
        api_client=_CompactApiClient(["<summary>condensed</summary>"]),
        model="claude-sonnet-4-6",
        state=AutoCompactState(),
        carryover_metadata=metadata,
    )

    assert was_compacted is True
    assert result[0].text.startswith("[Compact boundary marker]")
    checkpoints = metadata.get("compact_checkpoints")
    assert isinstance(checkpoints, list)
    checkpoint_names = [entry["checkpoint"] for entry in checkpoints]
    assert "query_auto_triggered" in checkpoint_names
    assert "query_microcompact_end" in checkpoint_names
    assert "compact_end" in checkpoint_names
    assert isinstance(metadata.get("compact_last"), dict)
    assert metadata["compact_last"]["checkpoint"] == "compact_end"


@pytest.mark.asyncio
async def test_auto_compact_if_needed_returns_original_messages_after_timeout(monkeypatch):
    async def _stall():
        await asyncio.sleep(0.05)

    monkeypatch.setattr("openharness.services.compact.COMPACT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: True)
    long_text = "alpha " * 50000
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
    ]

    result, was_compacted = await auto_compact_if_needed(
        messages,
        api_client=_CompactApiClient([_stall]),
        model="claude-sonnet-4-6",
        state=AutoCompactState(),
    )

    assert was_compacted is False
    assert result == messages


def test_get_autocompact_threshold_respects_manual_override():
    assert get_autocompact_threshold(
        "claude-sonnet-4-6",
        auto_compact_threshold_tokens=12345,
    ) == 12345


def test_should_autocompact_uses_custom_context_window():
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="alpha " * 6000)]),
    ]
    assert should_autocompact(
        messages,
        "claude-sonnet-4-6",
        AutoCompactState(),
        context_window_tokens=4000,
    ) is True
