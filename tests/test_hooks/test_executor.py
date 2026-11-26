"""Tests for hooks execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiRetryEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.hooks import HookEvent, HookExecutionContext, HookExecutor
from openharness.hooks.executor import _inject_arguments
from openharness.hooks.loader import HookRegistry
from openharness.hooks.schemas import AgentHookDefinition, CommandHookDefinition, PromptHookDefinition


class FakeApiClient:
    """Minimal fake streaming client."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


@pytest.mark.asyncio
async def test_command_hook_executes(tmp_path: Path):
    registry = HookRegistry()
    registry.register(
        HookEvent.SESSION_START,
        CommandHookDefinition(command="printf 'booted'"),
    )
    executor = HookExecutor(
        registry,
        HookExecutionContext(cwd=tmp_path, api_client=FakeApiClient('{"ok": true}'), default_model="claude-test"),
    )

    result = await executor.execute(HookEvent.SESSION_START, {"event": "session_start"})

    assert result.blocked is False
    assert result.results[0].output == "booted"


@pytest.mark.asyncio
async def test_prompt_hook_can_block(tmp_path: Path):
    registry = HookRegistry()
    registry.register(
        HookEvent.PRE_TOOL_USE,
        PromptHookDefinition(prompt="Check tool call", matcher="bash"),
    )
    executor = HookExecutor(
        registry,
        HookExecutionContext(
            cwd=tmp_path,
            api_client=FakeApiClient('{"ok": false, "reason": "blocked by policy"}'),
            default_model="claude-test",
        ),
    )

    result = await executor.execute(
        HookEvent.PRE_TOOL_USE,
        {"tool_name": "bash", "tool_input": {"command": "rm -rf ."}},
    )

    assert result.blocked is True
    assert result.reason == "blocked by policy"


# ---------------------------------------------------------------------------
# _inject_arguments shell escaping
# ---------------------------------------------------------------------------


def test_inject_arguments_no_escape_by_default():
    payload = {"command": "$(whoami)"}
    result = _inject_arguments("echo $ARGUMENTS", payload)
    # Without shell_escape, the raw JSON is substituted
    assert result == 'echo {"command": "$(whoami)"}'


def test_inject_arguments_shell_escape_wraps_in_single_quotes():
    payload = {"command": "$(whoami)"}
    result = _inject_arguments("echo $ARGUMENTS", payload, shell_escape=True)
    # With shell_escape, shlex.quote wraps the JSON in single quotes
    # so bash treats it as a literal string
    assert result.startswith("echo '")
    assert "$(whoami)" in result


@pytest.mark.asyncio
async def test_command_hook_escapes_shell_metacharacters(tmp_path: Path):
    """$ARGUMENTS in command hooks must be shell-escaped to prevent injection."""
    registry = HookRegistry()
    registry.register(
        HookEvent.PRE_TOOL_USE,
        CommandHookDefinition(command="echo $ARGUMENTS"),
    )
    executor = HookExecutor(
        registry,
        HookExecutionContext(
            cwd=tmp_path,
            api_client=FakeApiClient('{"ok": true}'),
            default_model="claude-test",
        ),
    )

    # $(echo INJECTED) would execute as a subshell if not properly escaped
    payload = {"tool_name": "test", "input": "$(echo INJECTED)"}
    result = await executor.execute(HookEvent.PRE_TOOL_USE, payload)

    output = result.results[0].output
    # With proper escaping, the literal $(echo INJECTED) must survive.
    # Without escaping, bash expands the subshell and the $() wrapper is gone.
    assert "$(echo INJECTED)" in output


class HangingApiClient:
    """Fake client whose model call never returns."""

    async def stream_message(self, request):
        del request
        await asyncio.Future()
        yield  # pragma: no cover


class FailingApiClient:
    """Fake client whose model call raises."""

    async def stream_message(self, request):
        del request
        raise RuntimeError("upstream unavailable")
        yield  # pragma: no cover


class RetryThenAnswerApiClient:
    """Fake client that reports one retry before it answers."""

    async def stream_message(self, request):
        del request
        yield ApiRetryEvent(message="rate limited", attempt=1, max_attempts=3, delay_seconds=0.0)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text='{"ok": true}')]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


def _prompt_hook_executor(tmp_path: Path, api_client, hook) -> HookExecutor:
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, hook)
    return HookExecutor(
        registry,
        HookExecutionContext(cwd=tmp_path, api_client=api_client, default_model="claude-test"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("hook_cls", [PromptHookDefinition, AgentHookDefinition])
async def test_prompt_like_hook_enforces_timeout(tmp_path: Path, hook_cls):
    executor = _prompt_hook_executor(
        tmp_path,
        HangingApiClient(),
        hook_cls(prompt="Check tool call", timeout_seconds=1),
    )

    result = await asyncio.wait_for(
        executor.execute(HookEvent.PRE_TOOL_USE, {"tool_name": "bash"}),
        timeout=10,
    )

    assert result.blocked is True
    assert result.results[0].success is False
    assert "timed out after 1s" in result.reason


@pytest.mark.asyncio
async def test_prompt_hook_request_error_respects_block_on_failure(tmp_path: Path):
    executor = _prompt_hook_executor(
        tmp_path,
        FailingApiClient(),
        PromptHookDefinition(prompt="Check tool call", block_on_failure=False),
    )

    result = await executor.execute(HookEvent.PRE_TOOL_USE, {"tool_name": "bash"})

    assert result.blocked is False
    assert result.results[0].success is False
    assert "upstream unavailable" in result.results[0].reason


@pytest.mark.asyncio
async def test_prompt_hook_ignores_retry_events(tmp_path: Path):
    executor = _prompt_hook_executor(
        tmp_path,
        RetryThenAnswerApiClient(),
        PromptHookDefinition(prompt="Check tool call"),
    )

    result = await executor.execute(HookEvent.PRE_TOOL_USE, {"tool_name": "bash"})

    assert result.blocked is False
    assert result.results[0].success is True
