"""High-level conversation engine."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator, cast

from openharness.api.client import SupportsStreamingMessages
from openharness.config.settings import PermissionSettings, Settings
from openharness.coordinator.coordinator_mode import get_coordinator_user_context
from openharness.engine.cost_tracker import CostTracker
from openharness.engine.messages import ConversationMessage, TextBlock, ToolResultBlock, sanitize_conversation_messages
from openharness.engine.query import AskUserPrompt, PermissionPrompt, QueryContext, remember_user_goal, run_query
from openharness.engine.stream_events import AssistantTurnComplete, ErrorEvent, StreamEvent, ToolExecutionCompleted
from openharness.hooks import HookEvent, HookExecutor
from openharness.memory.auto_write import AUTO_MEMORY_REVIEW_SYSTEM_PROMPT, build_turn_memory_review_messages
from openharness.permissions.checker import PermissionChecker
from openharness.permissions.modes import PermissionMode
from openharness.services.autodream.service import schedule_auto_dream
from openharness.tools.base import ToolRegistry

log = logging.getLogger(__name__)

_MAX_TRACKED_REPEAT_PROMPTS = 24
_REPEAT_PROMPT_SUMMARY_LIMIT = 240


def _normalize_repeat_prompt(text: str) -> str:
    normalized = " ".join(text.split()).casefold()
    if not normalized:
        return ""
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized[:_REPEAT_PROMPT_SUMMARY_LIMIT]


def _summarize_repeat_prompt(text: str) -> str:
    summary = " ".join(text.split()).strip()
    return summary[:_REPEAT_PROMPT_SUMMARY_LIMIT]


def _repeat_prompt_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    count = item.get("count", 0)
    prompt = item.get("prompt", "")
    count_value = int(count) if isinstance(count, (int, float)) else 0
    return (-count_value, str(prompt))


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
        memory_auto_write_enabled: bool = True,
        memory_review_after_response: bool = True,
        memory_review_interval_turns: int = 3,
        memory_review_max_messages: int = 8,
        memory_repeat_prompt_threshold: int = 2,
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
        self._context_window_tokens = context_window_tokens
        self._auto_compact_threshold_tokens = auto_compact_threshold_tokens
        self._memory_auto_write_enabled = memory_auto_write_enabled
        self._memory_review_after_response = memory_review_after_response
        self._memory_review_interval_turns = max(1, int(memory_review_interval_turns))
        self._memory_review_max_messages = max(1, int(memory_review_max_messages))
        self._memory_repeat_prompt_threshold = max(0, int(memory_repeat_prompt_threshold))
        self._max_turns = max_turns
        self._permission_prompt = permission_prompt
        self._ask_user_prompt = ask_user_prompt
        self._hook_executor = hook_executor
        self._tool_metadata = tool_metadata or {}
        self._settings = settings
        self._messages: list[ConversationMessage] = []
        self._cost_tracker = CostTracker()

    def _memory_review_state(self) -> dict[str, int]:
        state = self._tool_metadata.setdefault(
            "memory_review_state",
            {
                "turns_since_review": 0,
                "turns_since_write": 0,
                "reviews": 0,
                "writes": 0,
            },
        )
        if not isinstance(state, dict):
            state = {
                "turns_since_review": 0,
                "turns_since_write": 0,
                "reviews": 0,
                "writes": 0,
            }
            self._tool_metadata["memory_review_state"] = state
        for key in ("turns_since_review", "turns_since_write", "reviews", "writes"):
            value = state.get(key, 0)
            state[key] = int(value) if isinstance(value, (int, float)) else 0
        return state

    def _build_memory_review_registry(self) -> ToolRegistry | None:
        tool = self._tool_registry.get("memory_write")
        if tool is None:
            return None
        registry = ToolRegistry()
        registry.register(tool)
        return registry

    def _repeat_prompt_state(self) -> dict[str, Any]:
        state = cast(
            dict[str, Any],
            self._tool_metadata.setdefault(
                "memory_repeat_prompt_state",
                {"prompts": {}},
            ),
        )
        if not isinstance(state, dict):
            state = {"prompts": {}}
            self._tool_metadata["memory_repeat_prompt_state"] = state
        prompts = state.get("prompts")
        if not isinstance(prompts, dict):
            prompts = {}
            state["prompts"] = prompts
        return state

    def _note_user_prompt(self, prompt: str) -> None:
        if self._memory_repeat_prompt_threshold <= 0:
            return
        normalized = _normalize_repeat_prompt(prompt)
        summary = _summarize_repeat_prompt(prompt)
        if not normalized or len(normalized) < 12 or not summary:
            return
        state = self._repeat_prompt_state()
        prompts = state.get("prompts")
        if not isinstance(prompts, dict):
            prompts = {}
            state["prompts"] = prompts
        record = prompts.get(normalized)
        if not isinstance(record, dict):
            record = {
                "count": 0,
                "latest_prompt": summary,
                "reviewed_stage": 0,
            }
        count = record.get("count", 0)
        record["count"] = int(count) + 1 if isinstance(count, (int, float)) else 1
        record["latest_prompt"] = summary
        reviewed_stage = record.get("reviewed_stage", 0)
        record["reviewed_stage"] = int(reviewed_stage) if isinstance(reviewed_stage, (int, float)) else 0
        prompts.pop(normalized, None)
        prompts[normalized] = record
        while len(prompts) > _MAX_TRACKED_REPEAT_PROMPTS:
            oldest_key = next(iter(prompts))
            if oldest_key == normalized and len(prompts) == 1:
                break
            prompts.pop(oldest_key, None)

    def _repeat_prompt_candidates(self) -> list[dict[str, object]]:
        if self._memory_repeat_prompt_threshold <= 0:
            return []
        state = self._repeat_prompt_state()
        prompts = state.get("prompts")
        if not isinstance(prompts, dict):
            return []
        candidates: list[dict[str, Any]] = []
        for normalized_prompt, record in prompts.items():
            if not isinstance(record, dict):
                continue
            count = record.get("count", 0)
            reviewed_stage = record.get("reviewed_stage", 0)
            prompt_text = str(record.get("latest_prompt") or "").strip()
            count_value = int(count) if isinstance(count, (int, float)) else 0
            reviewed_stage_value = int(reviewed_stage) if isinstance(reviewed_stage, (int, float)) else 0
            current_stage = count_value // self._memory_repeat_prompt_threshold
            if current_stage <= reviewed_stage_value or not prompt_text:
                continue
            candidates.append(
                {
                    "count": count_value,
                    "prompt": prompt_text,
                    "normalized_prompt": str(normalized_prompt),
                }
            )
        candidates.sort(key=_repeat_prompt_sort_key)
        return candidates[:5]

    def _mark_repeat_prompt_candidates_reviewed(self) -> None:
        if self._memory_repeat_prompt_threshold <= 0:
            return
        state = self._repeat_prompt_state()
        prompts = state.get("prompts")
        if not isinstance(prompts, dict):
            return
        for record in prompts.values():
            if not isinstance(record, dict):
                continue
            count = record.get("count", 0)
            count_value = int(count) if isinstance(count, (int, float)) else 0
            record["reviewed_stage"] = count_value // self._memory_repeat_prompt_threshold

    def _metadata_paths(self, key: str) -> tuple[str, ...]:
        value = self._tool_metadata.get(key)
        if not isinstance(value, (list, tuple, set)):
            return ()
        return tuple(str(item) for item in value if isinstance(item, (str, Path)))

    def _note_memory_write(self) -> None:
        state = self._memory_review_state()
        state["turns_since_review"] = 0
        state["turns_since_write"] = 0
        state["writes"] += 1

    def _should_run_memory_review(self, *, memory_tool_used: bool) -> bool:
        if not self._memory_auto_write_enabled:
            return False
        if memory_tool_used:
            self._note_memory_write()
            return False
        if not self._memory_review_after_response:
            return False
        if self._build_memory_review_registry() is None:
            return False
        state = self._memory_review_state()
        state["turns_since_review"] += 1
        state["turns_since_write"] += 1
        if self._repeat_prompt_candidates():
            return True
        return state["turns_since_review"] >= self._memory_review_interval_turns

    def _complete_memory_review(self, *, memory_written: bool) -> None:
        state = self._memory_review_state()
        state["turns_since_review"] = 0
        state["reviews"] += 1
        self._mark_repeat_prompt_candidates_reviewed()
        if memory_written:
            state["turns_since_write"] = 0
            state["writes"] += 1

    async def _run_turn_memory_review(self) -> bool:
        registry = self._build_memory_review_registry()
        if registry is None:
            return False
        review_messages = build_turn_memory_review_messages(
            self._messages,
            self._cwd,
            max_messages=self._memory_review_max_messages,
            extra_skill_dirs=self._metadata_paths("extra_skill_dirs"),
            extra_plugin_roots=self._metadata_paths("extra_plugin_roots"),
            repeat_prompt_candidates=self._repeat_prompt_candidates(),
        )
        if not review_messages:
            return False
        review_context = QueryContext(
            api_client=self._api_client,
            tool_registry=registry,
            permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
            cwd=self._cwd,
            model=self._model,
            system_prompt=AUTO_MEMORY_REVIEW_SYSTEM_PROMPT,
            max_tokens=min(self._max_tokens, 1024),
            max_turns=3,
            tool_metadata=self._tool_metadata,
        )
        memory_written = False
        try:
            async for event, usage in run_query(review_context, review_messages):
                if usage is not None:
                    self._cost_tracker.add(usage)
                if isinstance(event, ToolExecutionCompleted) and event.tool_name == "memory_write" and not event.is_error:
                    memory_written = True
                if isinstance(event, ErrorEvent):
                    return False
        except Exception:
            log.exception("Automatic memory review failed")
            return False
        return memory_written

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
        if user_message.text.strip():
            self._note_user_prompt(user_message.text)
            if not self._tool_metadata.pop("_suppress_next_user_goal", False):
                remember_user_goal(self._tool_metadata, user_message.text)
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
        completed_turn = False
        memory_tool_used = False
        try:
            async for event, usage in run_query(context, query_messages):
                if isinstance(event, AssistantTurnComplete):
                    self._messages = list(query_messages)
                    completed_turn = True
                elif isinstance(event, ToolExecutionCompleted) and event.tool_name == "memory_write" and not event.is_error:
                    memory_tool_used = True
                if usage is not None:
                    self._cost_tracker.add(usage)
                yield event
        finally:
            self._schedule_auto_dream()
        if completed_turn and not self.has_pending_continuation() and self._should_run_memory_review(memory_tool_used=memory_tool_used):
            self._complete_memory_review(memory_written=await self._run_turn_memory_review())

    async def continue_pending(self, *, max_turns: int | None = None) -> AsyncIterator[StreamEvent]:
        """Continue an interrupted tool loop without appending a new user message."""
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            context_window_tokens=self._context_window_tokens,
            auto_compact_threshold_tokens=self._auto_compact_threshold_tokens,
            max_turns=max_turns if max_turns is not None else self._max_turns,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
        )
        completed_turn = False
        memory_tool_used = False
        async for event, usage in run_query(context, self._messages):
            if isinstance(event, AssistantTurnComplete):
                completed_turn = True
            elif isinstance(event, ToolExecutionCompleted) and event.tool_name == "memory_write" and not event.is_error:
                memory_tool_used = True
            if usage is not None:
                self._cost_tracker.add(usage)
            yield event
        if completed_turn and not self.has_pending_continuation() and self._should_run_memory_review(memory_tool_used=memory_tool_used):
            self._complete_memory_review(memory_written=await self._run_turn_memory_review())
