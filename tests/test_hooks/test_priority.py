"""Tests for hook priority ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.hooks import HookEvent, HookExecutionContext, HookExecutor
from openharness.hooks.loader import HookRegistry
from openharness.hooks.schemas import CommandHookDefinition, HttpHookDefinition


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


def test_priority_defaults_to_zero():
    assert CommandHookDefinition(command="true").priority == 0
    assert HttpHookDefinition(url="https://example.invalid").priority == 0


def test_registry_orders_by_priority_descending():
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="low", priority=1))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="high", priority=10))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="mid", priority=5))

    commands = [hook.command for hook in registry.get(HookEvent.PRE_TOOL_USE)]

    assert commands == ["high", "mid", "low"]


def test_registry_ties_keep_registration_order():
    """sorted() is stable, so equal priorities preserve insertion order."""
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="first", priority=5))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="second", priority=5))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="third", priority=5))

    commands = [hook.command for hook in registry.get(HookEvent.PRE_TOOL_USE)]

    assert commands == ["first", "second", "third"]


def test_negative_priority_runs_last():
    registry = HookRegistry()
    registry.register(HookEvent.SESSION_START, CommandHookDefinition(command="cleanup", priority=-10))
    registry.register(HookEvent.SESSION_START, CommandHookDefinition(command="default"))

    commands = [hook.command for hook in registry.get(HookEvent.SESSION_START)]

    assert commands == ["default", "cleanup"]


def test_summary_includes_non_default_priority():
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="guard", priority=10))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="logger"))

    summary = registry.summary()

    assert "priority=10" in summary
    # A default (zero) priority is not noisily printed.
    assert "priority=0" not in summary


@pytest.mark.asyncio
async def test_executor_runs_hooks_in_priority_order(tmp_path: Path):
    """End-to-end: execute() honours the priority-sorted registry order."""
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="printf 'low'", priority=1))
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="printf 'high'", priority=10))
    executor = HookExecutor(
        registry,
        HookExecutionContext(
            cwd=tmp_path,
            api_client=FakeApiClient('{"ok": true}'),
            default_model="claude-test",
        ),
    )

    result = await executor.execute(HookEvent.PRE_TOOL_USE, {"tool_name": "bash"})

    assert [hook.output for hook in result.results] == ["high", "low"]
