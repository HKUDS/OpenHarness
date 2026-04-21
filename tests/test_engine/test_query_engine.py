"""Tests for the query engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiRetryEvent, ApiTextDeltaEvent
from openharness.api.errors import RequestFailure
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings, Settings
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.engine.query_engine import QueryEngine
from openharness.prompts.context import build_runtime_system_prompt
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.tasks import get_task_manager
from openharness.tools import create_default_tool_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResult
from openharness.tools.glob_tool import GlobTool
from openharness.tools.grep_tool import GrepTool
from pydantic import BaseModel
from openharness.engine.messages import ToolResultBlock
from openharness.hooks import HookExecutionContext, HookExecutor, HookEvent
from openharness.hooks.loader import HookRegistry
from openharness.hooks.schemas import PromptHookDefinition
from openharness.engine.query import QueryContext, _execute_tool_call


@dataclass
class _FakeResponse:
    message: ConversationMessage
    usage: UsageSnapshot


class FakeApiClient:
    """Deterministic streaming client used by query tests."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)

    async def stream_message(self, request):
        del request
        response = self._responses.pop(0)
        for block in response.message.content:
            if isinstance(block, TextBlock) and block.text:
                yield ApiTextDeltaEvent(text=block.text)
        yield ApiMessageCompleteEvent(
            message=response.message,
            usage=response.usage,
            stop_reason=None,
        )


class StaticApiClient:
    """Fake client that always returns one fixed assistant message."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class RetryThenSuccessApiClient:
    async def stream_message(self, request):
        del request
        yield ApiRetryEvent(message="rate limited", attempt=1, max_attempts=4, delay_seconds=1.5)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="after retry")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class PromptTooLongThenSuccessApiClient:
    def __init__(self) -> None:
        self._calls = 0

    async def stream_message(self, request):
        self._calls += 1
        if self._calls == 1:
            raise RequestFailure("prompt too long")
        if self._calls == 2:
            yield ApiMessageCompleteEvent(
                message=ConversationMessage(role="assistant", content=[TextBlock(text="<summary>compressed</summary>")]),
                usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                stop_reason=None,
            )
            return
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="after reactive compact")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class EmptyAssistantApiClient:
    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class CoordinatorLoopApiClient:
    def __init__(self) -> None:
        self.requests = []
        self._calls = 0

    async def stream_message(self, request):
        self.requests.append(request)
        self._calls += 1
        if self._calls == 1:
            yield ApiMessageCompleteEvent(
                message=ConversationMessage(
                    role="assistant",
                    content=[
                        TextBlock(text="Launching a worker."),
                        ToolUseBlock(
                            id="toolu_agent_1",
                            name="agent",
                            input={
                                "description": "inspect coordinator wiring",
                                "prompt": "check whether coordinator mode is active",
                                "subagent_type": "worker",
                                "mode": "in_process_teammate",
                            },
                        ),
                    ],
                ),
                usage=UsageSnapshot(input_tokens=2, output_tokens=2),
                stop_reason=None,
            )
            return
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="Worker launched; coordinator mode is active.")]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=2),
            stop_reason=None,
        )


class _NoopApiClient:
    async def stream_message(self, request):
        del request
        if False:
            yield None


@pytest.mark.asyncio
async def test_query_engine_plain_text_reply(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Hello from the model.")],
                    ),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                )
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    assert isinstance(events[0], AssistantTextDelta)
    assert events[0].text == "Hello from the model."
    assert isinstance(events[-1], AssistantTurnComplete)
    assert engine.total_usage.input_tokens == 10
    assert engine.total_usage.output_tokens == 5
    assert len(engine.messages) == 2


@pytest.mark.asyncio
async def test_query_engine_executes_tool_calls(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="I will inspect the file."),
                            ToolUseBlock(
                                id="toolu_123",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 2},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=4, output_tokens=3),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="The file contains alpha and beta.")],
                    ),
                    usage=UsageSnapshot(input_tokens=8, output_tokens=6),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("read the file")]

    assert any(isinstance(event, ToolExecutionStarted) for event in events)
    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert len(tool_results) == 1
    assert "alpha" in tool_results[0].output
    assert isinstance(events[-1], AssistantTurnComplete)
    assert "alpha and beta" in events[-1].message.text
    assert len(engine.messages) == 4


@pytest.mark.asyncio
async def test_query_engine_coordinator_mode_uses_coordinator_prompt_and_runs_agent_loop(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")

    api_client = CoordinatorLoopApiClient()
    system_prompt = build_runtime_system_prompt(Settings(), cwd=tmp_path, latest_user_prompt="investigate issue")
    engine = QueryEngine(
        api_client=api_client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt=system_prompt,
    )

    events = [event async for event in engine.submit_message("investigate issue")]

    assert len(api_client.requests) == 2
    assert "You are a **coordinator**." in api_client.requests[0].system_prompt
    assert "Coordinator User Context" not in api_client.requests[0].system_prompt
    coordinator_context_messages = [
        msg for msg in api_client.requests[0].messages if msg.role == "user" and "Coordinator User Context" in msg.text
    ]
    assert len(coordinator_context_messages) == 1
    assert "Workers spawned via the agent tool have access to these tools" in coordinator_context_messages[0].text
    assert any(isinstance(event, ToolExecutionStarted) and event.tool_name == "agent" for event in events)
    agent_results = [event for event in events if isinstance(event, ToolExecutionCompleted) and event.tool_name == "agent"]
    assert len(agent_results) == 1
    assert isinstance(events[-1], AssistantTurnComplete)
    assert "coordinator mode is active" in events[-1].message.text


@pytest.mark.asyncio
async def test_query_engine_allows_unbounded_turns_when_max_turns_is_none(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="I will inspect the file."),
                            ToolUseBlock(
                                id="toolu_123",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 2},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=4, output_tokens=3),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="The file contains alpha and beta.")],
                    ),
                    usage=UsageSnapshot(input_tokens=8, output_tokens=6),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        max_turns=None,
    )

    events = [event async for event in engine.submit_message("read the file")]

    assert isinstance(events[-1], AssistantTurnComplete)
    assert "alpha and beta" in events[-1].message.text
    assert engine.max_turns is None


@pytest.mark.asyncio
async def test_query_engine_surfaces_retry_status_events(tmp_path: Path):
    engine = QueryEngine(
        api_client=RetryThenSuccessApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    assert any(isinstance(event, StatusEvent) and "retrying in 1.5s" in event.message for event in events)
    assert isinstance(events[-1], AssistantTurnComplete)


@pytest.mark.asyncio
async def test_query_engine_emits_compact_progress_before_reply(tmp_path: Path, monkeypatch):
    long_text = "alpha " * 50000
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: True)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="<summary>trimmed</summary>")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="after compact")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-sonnet-4-6",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ]
    )

    events = [event async for event in engine.submit_message("hello")]

    hooks_start_index = next(i for i, event in enumerate(events) if isinstance(event, CompactProgressEvent) and event.phase == "hooks_start")
    compact_start_index = next(i for i, event in enumerate(events) if isinstance(event, CompactProgressEvent) and event.phase == "compact_start")
    final_index = next(i for i, event in enumerate(events) if isinstance(event, AssistantTurnComplete))
    assert hooks_start_index < compact_start_index
    assert compact_start_index < final_index
    assert any(isinstance(event, CompactProgressEvent) and event.phase == "compact_end" for event in events)


@pytest.mark.asyncio
async def test_query_engine_reactive_compacts_after_prompt_too_long(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: False)
    engine = QueryEngine(
        api_client=PromptTooLongThenSuccessApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text="one")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="two")]),
            ConversationMessage(role="user", content=[TextBlock(text="three")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="four")]),
            ConversationMessage(role="user", content=[TextBlock(text="five")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="six")]),
            ConversationMessage(role="user", content=[TextBlock(text="seven")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="eight")]),
        ]
    )

    events = [event async for event in engine.submit_message("nine")]

    assert any(
        isinstance(event, CompactProgressEvent)
        and event.trigger == "reactive"
        and event.phase == "compact_start"
        for event in events
    )
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "after reactive compact"


@pytest.mark.asyncio
async def test_query_engine_tracks_recent_read_files_and_skills(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")
    registry = create_default_tool_registry()
    skill_tool = registry.get("skill")
    assert skill_tool is not None

    async def _fake_skill_execute(arguments, context):
        del context
        return ToolResult(output=f"Loaded skill: {arguments.name}")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(skill_tool, "execute", _fake_skill_execute)

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(name="read_file", input={"path": str(sample)}),
                            ToolUseBlock(name="skill", input={"name": "demo-skill"}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={},
    )

    try:
        events = [event async for event in engine.submit_message("track context")]
    finally:
        monkeypatch.undo()

    assert isinstance(events[-1], AssistantTurnComplete)
    read_state = engine._tool_metadata.get("read_file_state")
    assert isinstance(read_state, list) and read_state
    assert read_state[-1]["path"] == str(sample.resolve())
    assert "alpha" in read_state[-1]["preview"]
    task_focus = engine.tool_metadata.get("task_focus_state")
    assert isinstance(task_focus, dict)
    assert "track context" in task_focus.get("goal", "")
    assert str(sample.resolve()) in task_focus.get("active_artifacts", [])
    invoked_skills = engine._tool_metadata.get("invoked_skills")
    assert isinstance(invoked_skills, list)
    assert invoked_skills[-1] == "demo-skill"
    verified = engine.tool_metadata.get("recent_verified_work")
    assert isinstance(verified, list)
    assert any("Inspected file" in entry for entry in verified)
    assert any("Loaded skill demo-skill" in entry for entry in verified)


@pytest.mark.asyncio
async def test_query_engine_tracks_async_agent_activity(tmp_path: Path, monkeypatch):
    registry = create_default_tool_registry()
    agent_tool = registry.get("agent")
    assert agent_tool is not None

    async def _fake_execute(arguments, context):
        del arguments, context
        return ToolResult(output="Spawned agent worker@team (task_id=task_123, backend=subprocess)")

    monkeypatch.setattr(agent_tool, "execute", _fake_execute)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                name="agent",
                                input={"description": "Inspect CI", "prompt": "Inspect CI"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="spawned")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={},
    )

    events = [event async for event in engine.submit_message("spawn helper")]

    assert isinstance(events[-1], AssistantTurnComplete)
    async_state = engine._tool_metadata.get("async_agent_state")
    assert isinstance(async_state, list)
    assert async_state[-1].startswith("Spawned async agent")
    async_tasks = engine._tool_metadata.get("async_agent_tasks")
    assert isinstance(async_tasks, list)
    assert async_tasks[-1]["agent_id"] == "worker@team"
    assert async_tasks[-1]["task_id"] == "task_123"
    assert async_tasks[-1]["notification_sent"] is False


@pytest.mark.asyncio
async def test_query_engine_respects_pre_tool_hook_blocks(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\n", encoding="utf-8")
    registry = HookRegistry()
    registry.register(
        HookEvent.PRE_TOOL_USE,
        PromptHookDefinition(prompt="reject", matcher="read_file"),
    )

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_999",
                                name="read_file",
                                input={"path": str(sample)},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=HookExecutor(
            registry,
            HookExecutionContext(
                cwd=tmp_path,
                api_client=StaticApiClient('{"ok": false, "reason": "no reading"}'),
                default_model="claude-test",
            ),
        ),
    )

    events = [event async for event in engine.submit_message("read file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "no reading" in tool_results[0].output


class _RecordingHookExecutor:
    """Duck-typed hook executor that records every fired event + payload."""

    def __init__(self) -> None:
        self.calls: list[tuple[HookEvent, dict]] = []

    async def execute(self, event: HookEvent, payload: dict):
        from openharness.hooks.types import AggregatedHookResult

        self.calls.append((event, dict(payload)))
        return AggregatedHookResult(results=[])


@pytest.mark.asyncio
async def test_user_prompt_submit_hook_fires(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=StaticApiClient("done"),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("hello world")]

    user_prompt_calls = [c for c in recorder.calls if c[0] == HookEvent.USER_PROMPT_SUBMIT]
    assert len(user_prompt_calls) == 1
    assert user_prompt_calls[0][1]["event"] == "user_prompt_submit"
    assert user_prompt_calls[0][1]["prompt"] == "hello world"


@pytest.mark.asyncio
async def test_stop_hook_fires_on_clean_turn(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=StaticApiClient("all done"),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("hi")]

    stop_calls = [c for c in recorder.calls if c[0] == HookEvent.STOP]
    assert len(stop_calls) == 1
    assert stop_calls[0][1]["event"] == "stop"
    assert stop_calls[0][1]["stop_reason"] == "tool_uses_empty"


@pytest.mark.asyncio
async def test_stop_hook_does_not_fire_when_tool_uses_present(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\n", encoding="utf-8")
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_1",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 1},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="wrapped up")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("read the file")]

    stop_calls = [c for c in recorder.calls if c[0] == HookEvent.STOP]
    # STOP fires exactly once — at the end of the second turn (no tool_uses),
    # NOT after the first turn that contained a tool_use.
    assert len(stop_calls) == 1


@pytest.mark.asyncio
async def test_notification_hook_fires_on_permission_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    prompt_tool_calls: list[tuple[str, str]] = []

    async def _permission_prompt(tool_name: str, reason: str) -> bool:
        prompt_tool_calls.append((tool_name, reason))
        # Assert the NOTIFICATION hook fired before this callback was invoked.
        notif = [c for c in recorder.calls if c[0] == HookEvent.NOTIFICATION]
        assert notif, "notification hook must fire before permission prompt"
        return False  # deny — keeps the turn short

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_bash_1",
                                name="bash",
                                input={"command": "echo hi"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="denied")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.DEFAULT)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        permission_prompt=_permission_prompt,
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("run something")]

    notification_calls = [c for c in recorder.calls if c[0] == HookEvent.NOTIFICATION]
    assert len(notification_calls) == 1
    payload = notification_calls[0][1]
    assert payload["event"] == "notification"
    assert payload["notification_type"] == "permission_prompt"
    assert payload["tool_name"] == "bash"
    # The permission prompt callback was invoked (confirms the hook fired on the
    # correct branch, not on the silently-denied branch).
    assert prompt_tool_calls


@pytest.mark.asyncio
async def test_subagent_stop_hook_fires_when_spawned_agent_finishes(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_agent_1",
                                name="agent",
                                input={
                                    "description": "quick worker run",
                                    "prompt": "ready",
                                    "subagent_type": "worker",
                                    "mode": "local_agent",
                                    "command": 'python -u -c "import sys; print(sys.stdin.readline().strip())"',
                                },
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=2, output_tokens=2),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="worker done")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("run a worker")]

    manager = get_task_manager()
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline:
        subagent_stop_calls = [c for c in recorder.calls if c[0] == HookEvent.SUBAGENT_STOP]
        if subagent_stop_calls:
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("subagent_stop hook did not fire")

    subagent_stop_calls = [c for c in recorder.calls if c[0] == HookEvent.SUBAGENT_STOP]
    assert len(subagent_stop_calls) == 1
    payload = subagent_stop_calls[0][1]
    assert payload["event"] == "subagent_stop"
    assert payload["agent_id"] == "worker@default"
    assert payload["subagent_type"] == "worker"
    assert payload["mode"] == "local_agent"
    assert payload["status"] == "completed"
    assert payload["return_code"] == 0

    task = manager.get_task(payload["task_id"])
    assert task is not None
    assert task.status == "completed"


def _tool_context(tmp_path: Path, registry: ToolRegistry, settings: PermissionSettings) -> QueryContext:
    return QueryContext(
        api_client=_NoopApiClient(),
        tool_registry=registry,
        permission_checker=PermissionChecker(settings),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        max_tokens=1,
        max_turns=1,
    )


@pytest.mark.asyncio
async def test_execute_tool_call_blocks_sensitive_directory_roots(tmp_path: Path):
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()
    (sensitive_dir / "id_rsa").write_text("PRIVATE KEY MATERIAL\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(GrepTool())

    result = await _execute_tool_call(
        _tool_context(tmp_path, registry, PermissionSettings(mode=PermissionMode.DEFAULT)),
        "grep",
        "toolu_grep",
        {"pattern": "PRIVATE", "root": str(sensitive_dir), "file_glob": "*"},
    )

    assert result.is_error is True
    assert "sensitive credential path" in result.content


@pytest.mark.asyncio
async def test_execute_tool_call_applies_path_rules_to_directory_roots(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "secret.txt").write_text("classified\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(GlobTool())

    result = await _execute_tool_call(
        _tool_context(
            tmp_path,
            registry,
            PermissionSettings(
                mode=PermissionMode.DEFAULT,
                path_rules=[{"pattern": str(blocked_dir) + "/*", "allow": False}],
            ),
        ),
        "glob",
        "toolu_glob",
        {"pattern": "*", "root": str(blocked_dir)},
    )

    assert result.is_error is True
    assert str(blocked_dir) in result.content


@pytest.mark.asyncio
async def test_execute_tool_call_returns_actionable_reason_when_user_denies_confirmation(tmp_path: Path):
    async def _deny(_tool_name: str, _reason: str) -> bool:
        return False

    result = await _execute_tool_call(
        QueryContext(
            api_client=_NoopApiClient(),
            tool_registry=create_default_tool_registry(),
            permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.DEFAULT)),
            cwd=tmp_path,
            model="claude-test",
            system_prompt="system",
            max_tokens=1,
            max_turns=1,
            permission_prompt=_deny,
        ),
        "bash",
        "toolu_bash",
        {"command": "mkdir -p scratch-dir"},
    )

    assert result.is_error is True
    assert "Mutating tools require user confirmation" in result.content
    assert "/permissions full_auto" in result.content


@pytest.mark.asyncio
async def test_query_engine_executes_ask_user_tool(tmp_path: Path):
    async def _answer(question: str) -> str:
        assert question == "Which color?"
        return "green"

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_ask",
                                name="ask_user_question",
                                input={"question": "Which color?"},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Picked green.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        ask_user_prompt=_answer,
    )

    events = [event async for event in engine.submit_message("pick a color")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].output == "green"
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Picked green."


@pytest.mark.asyncio
async def test_query_engine_applies_path_rules_to_relative_read_file_targets(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    secret = blocked_dir / "secret.txt"
    secret.write_text("top-secret\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_blocked_read",
                                name="read_file",
                                input={"path": "blocked/secret.txt", "offset": 0, "limit": 1},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(
            PermissionSettings(
                mode=PermissionMode.DEFAULT,
                path_rules=[{"pattern": str((blocked_dir / "*").resolve()), "allow": False}],
            )
        ),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("read blocked file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "matches deny rule" in tool_results[0].output


@pytest.mark.asyncio
async def test_query_engine_applies_path_rules_to_write_file_targets_in_full_auto(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    target = blocked_dir / "output.txt"

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_blocked_write",
                                name="write_file",
                                input={"path": "blocked/output.txt", "content": "poc"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(
            PermissionSettings(
                mode=PermissionMode.FULL_AUTO,
                path_rules=[{"pattern": str((blocked_dir / "*").resolve()), "allow": False}],
            )
        ),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("write blocked file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "matches deny rule" in tool_results[0].output
    assert target.exists() is False


class _OkInput(BaseModel):
    pass


class _OkTool(BaseTool):
    name = "ok_tool"
    description = "Returns success."
    input_model = _OkInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(output="ok")


class _BoomTool(BaseTool):
    name = "boom_tool"
    description = "Always raises."
    input_model = _OkInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_query_engine_synthesizes_tool_result_when_parallel_tool_raises(tmp_path: Path):
    """Parallel tool calls must each yield a tool_result even when one tool raises.

    Regression for the case where ``asyncio.gather`` (without
    ``return_exceptions=True``) propagated the first exception, abandoned the
    sibling coroutines, and left the conversation with un-replied ``tool_use``
    blocks — Anthropic's API then rejects the next request on the session.
    """

    registry = ToolRegistry()
    registry.register(_OkTool())
    registry.register(_BoomTool())

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="Running two tools."),
                            ToolUseBlock(id="toolu_ok", name="ok_tool", input={}),
                            ToolUseBlock(id="toolu_boom", name="boom_tool", input={}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Recovered from the failure.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("run both tools")]

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    completed_by_name = {event.tool_name: event for event in completed}
    assert set(completed_by_name) == {"ok_tool", "boom_tool"}
    assert completed_by_name["ok_tool"].is_error is False
    assert completed_by_name["ok_tool"].output == "ok"
    assert completed_by_name["boom_tool"].is_error is True
    assert "RuntimeError" in completed_by_name["boom_tool"].output
    assert "boom" in completed_by_name["boom_tool"].output

    user_tool_messages = [
        msg for msg in engine.messages if msg.role == "user" and any(isinstance(block, ToolResultBlock) for block in msg.content)
    ]
    assert len(user_tool_messages) == 1
    result_blocks = [block for block in user_tool_messages[0].content if isinstance(block, ToolResultBlock)]
    assert {block.tool_use_id for block in result_blocks} == {"toolu_ok", "toolu_boom"}

    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Recovered from the failure."


@pytest.mark.asyncio
async def test_query_engine_drops_empty_assistant_messages(tmp_path: Path):
    engine = QueryEngine(
        api_client=EmptyAssistantApiClient(),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    assert any(isinstance(event, ErrorEvent) for event in events)
    assert not any(isinstance(event, AssistantTurnComplete) for event in events)
    assert len(engine.messages) == 1
    assert engine.messages[0].role == "user"
