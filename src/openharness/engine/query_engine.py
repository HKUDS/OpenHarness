"""High-level conversation engine."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import logging

from openharness.api.client import SupportsStreamingMessages
from openharness.engine.cost_tracker import CostTracker
from openharness.engine.messages import ConversationMessage
from openharness.engine.query import AskUserPrompt, PermissionPrompt, QueryContext, run_query
from openharness.engine.stream_events import StreamEvent
from openharness.hooks import HookExecutor
from openharness.permissions.checker import PermissionChecker
from openharness.services.compact import compact_messages, estimate_conversation_tokens
from openharness.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# Auto-compact when estimated tokens exceed this threshold.
# Conservative default — most models support at least 128k tokens.
AUTO_COMPACT_TOKEN_THRESHOLD = 80_000


class QueryEngine:
    """Owns conversation history and the tool-aware model loop."""

    def __init__(
        self,
        *,
        api_client: SupportsStreamingMessages,
        tool_registry: ToolRegistry,
        permission_checker: PermissionChecker,
        cwd: str | Path,
        model: str,
        system_prompt: str,
        max_tokens: int = 4096,
        permission_prompt: PermissionPrompt | None = None,
        ask_user_prompt: AskUserPrompt | None = None,
        hook_executor: HookExecutor | None = None,
        tool_metadata: dict[str, object] | None = None,
    ) -> None:
        self._api_client = api_client
        self._tool_registry = tool_registry
        self._permission_checker = permission_checker
        self._cwd = Path(cwd).resolve()
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._permission_prompt = permission_prompt
        self._ask_user_prompt = ask_user_prompt
        self._hook_executor = hook_executor
        self._tool_metadata = tool_metadata or {}
        self._messages: list[ConversationMessage] = []
        self._cost_tracker = CostTracker()

    @property
    def messages(self) -> list[ConversationMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    @property
    def total_usage(self):
        """Return the total usage across all turns."""
        return self._cost_tracker.total

    def clear(self) -> None:
        """Clear the in-memory conversation history."""
        self._messages.clear()
        self._cost_tracker = CostTracker()

    def set_system_prompt(self, prompt: str) -> None:
        """Update the active system prompt for future turns."""
        self._system_prompt = prompt

    def set_model(self, model: str) -> None:
        """Update the active model for future turns."""
        self._model = model

    def set_permission_checker(self, checker: PermissionChecker) -> None:
        """Update the active permission checker for future turns."""
        self._permission_checker = checker

    def load_messages(self, messages: list[ConversationMessage]) -> None:
        """Replace the in-memory conversation history."""
        self._messages = list(messages)

    def _auto_compact_if_needed(self) -> None:
        """Compact conversation history if estimated tokens exceed the threshold."""
        estimated = estimate_conversation_tokens(self._messages)
        if estimated > AUTO_COMPACT_TOKEN_THRESHOLD:
            before = len(self._messages)
            self._messages = compact_messages(self._messages, preserve_recent=6)
            after = len(self._messages)
            logger.info(
                "Auto-compacted conversation: %d -> %d messages (~%d tokens)",
                before, after, estimated,
            )

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        """Append a user message and execute the query loop."""
        self._messages.append(ConversationMessage.from_user_text(prompt))
        self._auto_compact_if_needed()
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
        )
        async for event, usage in run_query(context, self._messages):
            if usage is not None:
                self._cost_tracker.add(usage)
            yield event
