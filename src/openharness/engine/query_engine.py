"""High-level conversation engine."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from openharness.api.client import SupportsStreamingMessages
from openharness.engine.cost_tracker import CostTracker
from openharness.coordinator.coordinator_mode import get_coordinator_user_context
from openharness.engine.messages import ConversationMessage, TextBlock, ToolResultBlock, sanitize_conversation_messages
from openharness.engine.query import AskUserPrompt, PermissionPrompt, QueryContext, remember_user_goal, run_query
from openharness.engine.stream_events import AssistantTurnComplete, StreamEvent
from openharness.config.settings import Settings
from openharness.hooks import HookEvent, HookExecutor
from openharness.permissions.checker import PermissionChecker
from openharness.services.autodream.service import schedule_auto_dream
from openharness.tools.base import ToolRegistry


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
        context_window_tokens: int | None = None,
        auto_compact_threshold_tokens: int | None = None,
        max_turns: int | None = 8,
        permission_prompt: PermissionPrompt | None = None,
        ask_user_prompt: AskUserPrompt | None = None,
        hook_executor: HookExecutor | None = None,
        tool_metadata: dict[str, object] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._api_client = api_client
        self._tool_registry = tool_registry
        self._permission_checker = permission_checker
        self._cwd = Path(cwd).resolve()
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._effort = settings.effort if settings is not None else None
        self._context_window_tokens = context_window_tokens
        self._auto_compact_threshold_tokens = auto_compact_threshold_tokens
        self._max_turns = max_turns
        self._permission_prompt = permission_prompt
        self._ask_user_prompt = ask_user_prompt
        self._hook_executor = hook_executor
        self._tool_metadata = tool_metadata or {}
        self._settings = settings
        self._messages: list[ConversationMessage] = []
        self._cost_tracker = CostTracker()

    @property
    def messages(self) -> list[ConversationMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    @property
    def max_turns(self) -> int | None:
        """Return the maximum number of agentic turns per user input, if capped."""
        return self._max_turns

    @property
    def api_client(self) -> SupportsStreamingMessages:
        """Return the active API client."""
        return self._api_client

    @property
    def model(self) -> str:
        """Return the active model identifier."""
        return self._model

    @property
    def system_prompt(self) -> str:
        """Return the active system prompt."""
        return self._system_prompt

    @property
    def tool_metadata(self) -> dict[str, object]:
        """Return the mutable tool metadata/carry-over state."""
        return self._tool_metadata

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

    def set_effort(self, effort: str | None) -> None:
        """Update the active reasoning effort for future turns."""
        self._effort = effort

    def set_api_client(self, api_client: SupportsStreamingMessages) -> None:
        """Update the active API client for future turns."""
        self._api_client = api_client

    def set_max_turns(self, max_turns: int | None) -> None:
        """Update the maximum number of agentic turns per user input."""
        self._max_turns = None if max_turns is None else max(1, int(max_turns))

    def set_permission_checker(self, checker: PermissionChecker) -> None:
        """Update the active permission checker for future turns."""
        self._permission_checker = checker

    def _build_coordinator_context_message(self) -> ConversationMessage | None:
        """Build a synthetic user message carrying coordinator runtime context."""
        context = get_coordinator_user_context()
        worker_tools_context = context.get("workerToolsContext")
        if not worker_tools_context:
            return None
        return ConversationMessage(
            role="user",
            content=[TextBlock(text=f"# Coordinator User Context\n\n{worker_tools_context}")],
        )

    def load_messages(self, messages: list[ConversationMessage]) -> None:
        """Replace the in-memory conversation history."""
        self._messages = list(messages)

    def _schedule_auto_dream(self) -> None:
        """Fire-and-forget background memory consolidation after a user turn."""
        if self._settings is None:
            return
        context = self._tool_metadata.get("autodream_context")
        kwargs = dict(context) if isinstance(context, dict) else {}
        schedule_auto_dream(
            cwd=self._cwd,
            settings=self._settings,
            model=self._model,
            current_session_id=str(self._tool_metadata.get("session_id") or ""),
            **kwargs,
        )

    def _prepare_session_memory(self) -> None:
        """Expose file-backed session memory to compaction when enabled."""

        if self._settings is None or not self._settings.memory.session_memory_enabled:
            return
        if not self._settings.memory.enabled:
            return
        from openharness.services.session_memory import prepare_session_memory_metadata

        prepare_session_memory_metadata(
            self._cwd,
            self._tool_metadata,
            session_id=str(self._tool_metadata.get("session_id") or "default"),
        )

    async def _update_session_memory(self) -> None:
        """Persist a session checkpoint after a user turn."""

        if self._settings is None or not self._settings.memory.session_memory_enabled:
            return
        if not self._settings.memory.enabled:
            return
        from openharness.services.session_memory import update_session_memory_file

        update_session_memory_file(
            self._cwd,
            list(self._messages),
            tool_metadata=self._tool_metadata,
            session_id=str(self._tool_metadata.get("session_id") or "default"),
        )

    async def _extract_durable_memories(self) -> None:
        """Run the optional durable memory extraction pass."""

        if self._settings is None or not self._settings.memory.auto_extract_enabled:
            return
        if not self._settings.memory.enabled:
            return
        from openharness.services.memory_extract import extract_memories_from_turn

        try:
            result = await extract_memories_from_turn(
                cwd=self._cwd,
                api_client=self._api_client,
                model=self._model,
                messages=list(self._messages),
                max_records=self._settings.memory.auto_extract_max_records,
            )
        except Exception as exc:
            self._tool_metadata["memory_extract_last_error"] = str(exc)
            return
        self._tool_metadata["memory_extract_last"] = {
            "skipped": result.skipped,
            "reason": result.reason,
            "written_paths": [str(path) for path in result.written_paths],
        }

    def has_pending_continuation(self) -> bool:
        """Return True when the conversation ends with tool results awaiting a follow-up model turn."""
        if not self._messages:
            return False
        last = self._messages[-1]
        if last.role != "user":
            return False
        if not any(isinstance(block, ToolResultBlock) for block in last.content):
            return False
        for msg in reversed(self._messages[:-1]):
            if msg.role != "assistant":
                continue
            return bool(msg.tool_uses)
        return False

    async def submit_message(self, prompt: str | ConversationMessage) -> AsyncIterator[StreamEvent]:
        """Append a user message and execute the query loop."""
        user_message = (
            prompt
            if isinstance(prompt, ConversationMessage)
            else ConversationMessage.from_user_text(prompt)
        )
        if user_message.text.strip() and not self._tool_metadata.pop("_suppress_next_user_goal", False):
            remember_user_goal(self._tool_metadata, user_message.text)
        self._prepare_session_memory()
        self._messages = sanitize_conversation_messages(self._messages)
        self._messages.append(user_message)
        if self._hook_executor is not None:
            await self._hook_executor.execute(
                HookEvent.USER_PROMPT_SUBMIT,
                {
                    "event": HookEvent.USER_PROMPT_SUBMIT.value,
                    "prompt": user_message.text,
                },
            )
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            effort=self._effort,
            context_window_tokens=self._context_window_tokens,
            auto_compact_threshold_tokens=self._auto_compact_threshold_tokens,
            max_turns=self._max_turns,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
        )
        query_messages = list(self._messages)
        coordinator_context = self._build_coordinator_context_message()
        if coordinator_context is not None:
            query_messages.append(coordinator_context)
        try:
            async for event, usage in run_query(context, query_messages):
                if isinstance(event, AssistantTurnComplete):
                    self._messages = list(query_messages)
                if usage is not None:
                    self._cost_tracker.add(usage)
                yield event
        finally:
            await self._update_session_memory()
            await self._extract_durable_memories()
            self._schedule_auto_dream()

    async def continue_pending(self, *, max_turns: int | None = None) -> AsyncIterator[StreamEvent]:
        """Continue an interrupted tool loop without appending a new user message."""
        self._prepare_session_memory()
        self._messages = sanitize_conversation_messages(self._messages)
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            effort=self._effort,
            context_window_tokens=self._context_window_tokens,
            auto_compact_threshold_tokens=self._auto_compact_threshold_tokens,
            max_turns=max_turns if max_turns is not None else self._max_turns,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
        )
        async for event, usage in run_query(context, self._messages):
            if usage is not None:
                self._cost_tracker.add(usage)
            yield event
        await self._update_session_memory()
        await self._extract_durable_memories()
