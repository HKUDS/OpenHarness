"""Evidence collection system for capturing run-level data."""

from __future__ import annotations

import asyncio
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from openharness.engine.messages import ConversationMessage
from openharness.evidence.store import EvidenceStore
from openharness.evidence.types import (
    ConversationEvidence,
    ErrorEvidence,
    EvidenceRecord,
    HookEvidence,
    PerformanceEvidence,
    RunEvidence,
    StateEvidence,
    TaskEvidence,
)
from openharness.hooks.types import AggregatedHookResult, HookResult
from openharness.tasks.types import TaskRecord


class EvidenceCollector:
    """Collects and stores evidence from agent runs."""

    def __init__(self, run_id: str | None = None, store: EvidenceStore | None = None) -> None:
        self.run_id = run_id or str(uuid4())
        self.store = store or EvidenceStore()
        self.agent_id = ""
        self._start_time = time.time()

    def set_agent_id(self, agent_id: str) -> None:
        """Set the current agent ID for evidence records."""
        self.agent_id = agent_id

    def record_run_start(
        self,
        session_id: str = "",
        cwd: str = "",
        command_line: str = "",
        config: dict[str, Any] | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        """Record the start of a run."""
        evidence = RunEvidence(
            type="run_start",
            run_id=self.run_id,
            agent_id=self.agent_id,
            session_id=session_id,
            cwd=cwd,
            command_line=command_line,
            config=config or {},
            environment=environment or {},
            timestamp=self._start_time,
        )
        self.store.store_evidence(evidence)

    def record_run_end(self, final_status: str = "completed") -> None:
        """Record the end of a run."""
        evidence = RunEvidence(
            type="run_end",
            run_id=self.run_id,
            agent_id=self.agent_id,
            metadata={"final_status": final_status, "duration": time.time() - self._start_time},
        )
        self.store.store_evidence(evidence)

    def record_task_start(self, task: TaskRecord) -> None:
        """Record the start of a task."""
        evidence = TaskEvidence(
            type="task_start",
            run_id=self.run_id,
            agent_id=self.agent_id,
            task_id=task.id,
            task_type=task.type,
            description=task.description,
            status=task.status,
            command=task.command,
            cwd=task.cwd,
            output_file=str(task.output_file),
            metadata={"created_at": task.created_at, "started_at": task.started_at},
        )
        self.store.store_evidence(evidence)

    def record_task_progress(self, task_id: str, progress_data: dict[str, Any]) -> None:
        """Record progress on a task."""
        evidence = TaskEvidence(
            type="task_progress",
            run_id=self.run_id,
            agent_id=self.agent_id,
            task_id=task_id,
            metadata=progress_data,
        )
        self.store.store_evidence(evidence)

    def record_task_end(self, task: TaskRecord) -> None:
        """Record the end of a task."""
        duration = 0.0
        if task.started_at and task.ended_at:
            duration = task.ended_at - task.started_at

        evidence = TaskEvidence(
            type="task_end",
            run_id=self.run_id,
            agent_id=self.agent_id,
            task_id=task.id,
            status=task.status,
            return_code=task.return_code,
            duration=duration,
            metadata={
                "ended_at": task.ended_at,
                "return_code": task.return_code,
                "duration": duration,
            },
        )
        self.store.store_evidence(evidence)

    def record_conversation_message(
        self,
        message: ConversationMessage,
        token_count: int = 0,
        model: str = "",
    ) -> None:
        """Record a conversation message."""
        evidence = ConversationEvidence(
            type="conversation_message",
            run_id=self.run_id,
            agent_id=self.agent_id,
            message_type=message.message_type,
            content=message.content,
            role=getattr(message, "role", ""),
            tool_calls=getattr(message, "tool_calls", []),
            tool_results=getattr(message, "tool_results", []),
            token_count=token_count,
            model=model,
            metadata={"message_id": getattr(message, "id", "")},
        )
        self.store.store_evidence(evidence)

    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> None:
        """Record a tool call."""
        evidence = ConversationEvidence(
            type="tool_call",
            run_id=self.run_id,
            agent_id=self.agent_id,
            metadata={
                "tool_name": tool_name,
                "arguments": arguments,
                "tool_call_id": tool_call_id,
            },
        )
        self.store.store_evidence(evidence)

    def record_tool_result(
        self,
        tool_call_id: str,
        result: Any,
        success: bool = True,
        error_message: str = "",
    ) -> None:
        """Record a tool result."""
        evidence = ConversationEvidence(
            type="tool_result",
            run_id=self.run_id,
            agent_id=self.agent_id,
            metadata={
                "tool_call_id": tool_call_id,
                "result": str(result),
                "success": success,
                "error_message": error_message,
            },
        )
        self.store.store_evidence(evidence)

    def record_hook_execution(
        self,
        event: str,
        result: AggregatedHookResult,
        duration: float = 0.0,
    ) -> None:
        """Record hook execution results."""
        for hook_result in result.results:
            evidence = HookEvidence(
                type="hook_execution",
                run_id=self.run_id,
                agent_id=self.agent_id,
                event=event,
                hook_type=hook_result.hook_type,
                success=hook_result.success,
                output=hook_result.output,
                blocked=hook_result.blocked,
                reason=hook_result.reason,
                duration=duration,
                metadata=hook_result.metadata,
            )
            self.store.store_evidence(evidence)

    def record_state_change(
        self,
        state_type: str,
        previous_state: dict[str, Any],
        new_state: dict[str, Any],
        change_reason: str = "",
    ) -> None:
        """Record a state change."""
        evidence = StateEvidence(
            type="state_change",
            run_id=self.run_id,
            agent_id=self.agent_id,
            state_type=state_type,
            previous_state=previous_state,
            new_state=new_state,
            change_reason=change_reason,
        )
        self.store.store_evidence(evidence)

    def record_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        category: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a performance metric."""
        evidence = PerformanceEvidence(
            type="performance_metric",
            run_id=self.run_id,
            agent_id=self.agent_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            category=category,
            context=context or {},
        )
        self.store.store_evidence(evidence)

    def record_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None,
        exc: Exception | None = None,
        recoverable: bool = False,
    ) -> None:
        """Record an error or exception."""
        tb_str = ""
        if exc:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        evidence = ErrorEvidence(
            type="error",
            run_id=self.run_id,
            agent_id=self.agent_id,
            error_type=error_type,
            error_message=error_message,
            traceback=tb_str,
            context=context or {},
            recoverable=recoverable,
        )
        self.store.store_evidence(evidence)

    @asynccontextmanager
    async def collect_run_evidence(
        self,
        session_id: str = "",
        cwd: str = "",
        command_line: str = "",
        config: dict[str, Any] | None = None,
        environment: dict[str, str] | None = None,
    ) -> AsyncIterator[EvidenceCollector]:
        """Context manager for collecting evidence for an entire run."""
        try:
            self.record_run_start(
                session_id=session_id,
                cwd=cwd,
                command_line=command_line,
                config=config,
                environment=environment,
            )
            yield self
        except Exception as e:
            self.record_error(
                "run_execution_error",
                str(e),
                context={"phase": "run_execution"},
                exc=e,
            )
            raise
        finally:
            self.record_run_end()

    def get_run_summary(self) -> dict[str, Any]:
        """Get a summary of the current run's evidence."""
        return self.store.get_run_summary(self.run_id)