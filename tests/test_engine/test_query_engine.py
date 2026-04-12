"""Tests for the query engine."""

from __future__ import annotations

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
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolRegistry, ToolResult
from openharness.tools.glob_tool import GlobTool
from openharness.tools.grep_tool import GrepTool
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
        permission_checker=PermissionChecker(PermissionSettings()),
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
        permission_checker=PermissionChecker(PermissionSettings()),
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
        permission_checker=PermissionChecker(PermissionSettings()),
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
