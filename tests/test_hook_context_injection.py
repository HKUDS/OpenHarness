from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, SupportsStreamingMessages
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import Settings, save_settings
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.query_engine import QueryEngine
from openharness.hooks import HookEvent, HookExecutionContext, HookExecutor, load_hook_registry
from openharness.hooks.schemas import CommandHookDefinition
from openharness.permissions.checker import PermissionChecker
from openharness.tools.base import ToolRegistry
from openharness.ui.runtime import build_runtime


class CapturingApiClient(SupportsStreamingMessages):
    def __init__(self) -> None:
        self.requests = []

    async def stream_message(self, request):
        self.requests.append(request)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
            usage=UsageSnapshot(),
        )


def _python_json_command(code: str) -> str:
    return f"{sys.executable} -c {json.dumps(code)}"


@pytest.mark.asyncio
async def test_command_hook_can_receive_payload_on_stdin(tmp_path: Path) -> None:
    seen = tmp_path / "seen.json"
    code = (
        "import json, pathlib, sys; "
        f"pathlib.Path({str(seen)!r}).write_text(sys.stdin.read(), encoding='utf-8'); "
        "print(json.dumps({'additional_context': 'stdin ok'}))"
    )
    registry = load_hook_registry(
        Settings(
            hooks={
                HookEvent.USER_PROMPT_SUBMIT.value: [
                    CommandHookDefinition(command=_python_json_command(code), stdin_payload=True)
                ]
            }
        )
    )
    client = CapturingApiClient()
    executor = HookExecutor(
        registry,
        HookExecutionContext(cwd=tmp_path, api_client=client, default_model="test-model"),
    )

    result = await executor.execute(HookEvent.USER_PROMPT_SUBMIT, {"prompt": "hello"})

    assert json.loads(seen.read_text(encoding="utf-8"))["prompt"] == "hello"
    assert result.additional_context == "stdin ok"


@pytest.mark.asyncio
async def test_user_prompt_hook_context_is_injected_for_one_turn(tmp_path: Path) -> None:
    code = "import json; print(json.dumps({'additional_context': 'CLAUDE_MEM_CONTEXT'}))"
    registry = load_hook_registry(
        Settings(
            hooks={
                HookEvent.USER_PROMPT_SUBMIT.value: [
                    CommandHookDefinition(command=_python_json_command(code))
                ]
            }
        )
    )
    client = CapturingApiClient()
    engine = QueryEngine(
        api_client=client,
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(Settings().permission),
        cwd=tmp_path,
        model="test-model",
        system_prompt="system",
        hook_executor=HookExecutor(
            registry,
            HookExecutionContext(cwd=tmp_path, api_client=client, default_model="test-model"),
        ),
        tool_metadata={"session_id": "s1"},
    )

    events = [event async for event in engine.submit_message("hello")]

    assert events
    assert any("CLAUDE_MEM_CONTEXT" in message.text for message in client.requests[0].messages)
    assert all("CLAUDE_MEM_CONTEXT" not in message.text for message in engine.messages)


@pytest.mark.asyncio
async def test_session_start_hook_context_is_added_to_runtime_system_prompt(tmp_path: Path) -> None:
    code = "import json; print(json.dumps({'additional_context': 'SESSION_MEMORY_CONTEXT'}))"
    settings = Settings(
        provider="anthropic",
        model="test-model",
        hooks={
            HookEvent.SESSION_START.value: [
                CommandHookDefinition(command=_python_json_command(code))
            ]
        },
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    save_settings(settings, config_dir / "settings.json")

    import os

    old_config_dir = os.environ.get("OPENHARNESS_CONFIG_DIR")
    os.environ["OPENHARNESS_CONFIG_DIR"] = str(config_dir)
    try:
        bundle = await build_runtime(
            cwd=str(tmp_path),
            api_client=CapturingApiClient(),
            include_project_memory=False,
        )
    finally:
        if old_config_dir is None:
            os.environ.pop("OPENHARNESS_CONFIG_DIR", None)
        else:
            os.environ["OPENHARNESS_CONFIG_DIR"] = old_config_dir

    assert "SESSION_MEMORY_CONTEXT" in bundle.engine.system_prompt
