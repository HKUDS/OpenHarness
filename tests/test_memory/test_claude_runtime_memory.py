"""Tests for Claude Code-inspired memory runtime behavior."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.commands.registry import CommandContext, create_default_command_registry
from openharness.config.settings import Settings
from openharness.engine.messages import ConversationMessage, ToolUseBlock
from openharness.engine.query_engine import QueryEngine
from openharness.memory import add_memory_entry, get_project_memory_dir
from openharness.memory.agent import (
    ensure_agent_memory_vault,
    get_agent_memory_entrypoint,
    initialize_agent_memory_from_snapshot,
)
from openharness.memory.relevance import format_relevant_memories, select_relevant_memories
from openharness.memory.schema import (
    memory_freshness_text,
    parse_memory_scope,
    parse_memory_type,
    truncate_entrypoint_content,
)
from openharness.memory.team import (
    check_team_memory_secrets,
    ensure_team_memory_vault,
    validate_team_memory_write_path,
)
from openharness.permissions import PermissionChecker
from openharness.services.memory_extract import (
    extract_memories_from_turn,
    has_memory_writes_since,
    parse_extraction_records,
    validate_extraction_tool_request,
)
from openharness.services.session_memory import (
    get_session_memory_content,
    get_session_memory_path,
    update_session_memory_file,
)
from openharness.tools import create_default_tool_registry


class _FakeApiClient:
    def __init__(self, text: str = "done") -> None:
        self.text = text
        self.requests = []

    async def stream_message(self, request):
        self.requests.append(request)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage.from_user_text(self.text).model_copy(update={"role": "assistant"}),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
        )


def test_schema_truncation_and_freshness() -> None:
    raw = "\n".join(f"- item {idx}" for idx in range(240))
    view = truncate_entrypoint_content(raw, max_lines=10, max_bytes=1_000)

    assert view.was_truncated is True
    assert "WARNING" in view.content
    assert parse_memory_type("note", default="project") == "project"
    assert parse_memory_scope("personal") == "private"
    assert "2 days old" in memory_freshness_text(time.time() - 2 * 86_400)


def test_relevance_formats_staleness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    path = add_memory_entry(project, "Redis Rule", "Redis cache decisions matter.", memory_type="project")
    old = time.time() - 3 * 86_400
    os.utime(path, (old, old))

    selected = select_relevant_memories("redis cache", project)
    rendered = format_relevant_memories(selected)

    assert selected
    assert "3 days old" in rendered
    assert "Redis cache decisions" in rendered


@pytest.mark.asyncio
async def test_memory_extraction_writes_typed_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    api = _FakeApiClient(
        '{"memories":[{"title":"Testing Policy","type":"feedback","scope":"project",'
        '"description":"real database tests","body":"Use real database tests for migrations.",'
        '"tags":["testing"]}]}'
    )
    messages = [
        ConversationMessage.from_user_text("do not mock database migrations"),
        ConversationMessage.from_user_text("noted").model_copy(update={"role": "assistant"}),
    ]

    result = await extract_memories_from_turn(cwd=project, api_client=api, model="claude-test", messages=messages)

    assert result.skipped is False
    assert len(result.written_paths) == 1
    text = result.written_paths[0].read_text(encoding="utf-8")
    assert 'type: "feedback"' in text
    assert 'scope: "project"' in text
    assert "Use real database tests" in text


def test_memory_extraction_parser_and_tool_guard(tmp_path: Path) -> None:
    records = parse_extraction_records(
        '{"memories":[{"title":"User Role","type":"user","scope":"private","body":"User knows Go."}]}'
    )
    assert records[0].memory_type == "user"
    assert records[0].scope == "private"

    ok, _ = validate_extraction_tool_request("bash", {"command": "rg memory src"}, tmp_path)
    denied, reason = validate_extraction_tool_request("write_file", {"path": "../x", "content": "x"}, tmp_path)

    assert ok is True
    assert denied is False
    assert "within" in reason


def test_memory_write_detection_resolves_relative_paths_from_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    memory_dir = get_project_memory_dir(project)

    normal_relative_write = ConversationMessage(
        role="assistant",
        content=[ToolUseBlock(name="write_file", input={"path": "REPORT.md", "content": "ok"})],
    )
    memory_absolute_write = ConversationMessage(
        role="assistant",
        content=[ToolUseBlock(name="write_file", input={"path": str(memory_dir / "report.md")})],
    )

    assert has_memory_writes_since([normal_relative_write], memory_dir, cwd=project) is False
    assert has_memory_writes_since([memory_absolute_write], memory_dir, cwd=project) is True


def test_session_memory_file_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    messages = [ConversationMessage.from_user_text("current task: finish memory runtime")]

    path = update_session_memory_file(project, messages, session_id="abc")

    assert path == get_session_memory_path(project, "abc")
    assert "finish memory runtime" in get_session_memory_content(path)


def test_team_memory_guards_and_agent_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    team_dir = ensure_team_memory_vault(project)
    valid_path, error = validate_team_memory_write_path(project, "notes/shared.md")
    escaped_path, escaped_error = validate_team_memory_write_path(project, "../outside.md")
    agent_dir = ensure_agent_memory_vault(project, "reviewer/bot", "project")

    assert team_dir.exists()
    assert valid_path is not None and error is None
    assert escaped_path is None and escaped_error
    assert check_team_memory_secrets("OPENAI_API_KEY=sk-12345678901234567890")
    assert agent_dir.exists()
    assert get_agent_memory_entrypoint(project, "reviewer/bot", "project").exists()


def test_agent_memory_snapshot_initializes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    snapshot = project / ".openharness" / "agent-memory-snapshots" / "reviewer"
    snapshot.mkdir(parents=True)
    (snapshot / "MEMORY.md").write_text("# Snapshot\n", encoding="utf-8")

    target = initialize_agent_memory_from_snapshot(project, "reviewer", "project")

    assert target is not None
    assert (target / "MEMORY.md").read_text(encoding="utf-8") == "# Snapshot\n"


@pytest.mark.asyncio
async def test_memory_commands_expose_session_team_and_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()
    engine = QueryEngine(
        api_client=_FakeApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(Settings().permission),
        cwd=project,
        model="claude-test",
        system_prompt="system",
    )
    context = CommandContext(engine=engine, cwd=str(project), session_id="s1")
    registry = create_default_command_registry()

    for raw in ("/memory session", "/memory team", "/memory agent status reviewer project"):
        command, args = registry.lookup(raw)
        assert command is not None
        result = await command.handler(args, context)
        assert result.message

    command, args = registry.lookup("/memory add --type feedback --scope private Style :: Keep answers concise.")
    assert command is not None
    result = await command.handler(args, context)
    assert "Added memory entry" in (result.message or "")
    assert 'type: "feedback"' in (get_project_memory_dir(project) / "style.md").read_text(encoding="utf-8")
