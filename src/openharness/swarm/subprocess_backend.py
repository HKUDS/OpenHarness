"""Subprocess-based TeammateExecutor implementation."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from openharness.swarm.spawn_utils import (
    build_inherited_cli_flags,
    build_inherited_env_vars,
    get_teammate_command,
    resolve_max_concurrent_teammates,
    warn_if_shared_key_parallel_teammates,
)
from openharness.swarm.types import (
    BackendType,
    SpawnResult,
    TeammateMessage,
    TeammateSpawnConfig,
)
from openharness.tasks.manager import BackgroundTaskManager, get_task_manager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "killed"})


class SubprocessBackend:
    """TeammateExecutor that runs each teammate as a separate subprocess.

    Uses the existing :class:`~openharness.tasks.manager.BackgroundTaskManager`
    to create and manage the child processes, communicating via stdin/stdout.
    """

    type: BackendType = "subprocess"

    # Maps agent_id -> task_id for tracking live agents
    _agent_tasks: dict[str, str]

    def __init__(self, max_concurrent_teammates: int | None = None) -> None:
        self._agent_tasks = {}
        self._inflight_agents: set[str] = set()
        self._max_concurrent_teammates = max_concurrent_teammates
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._semaphore_limit: int | None = None
        self._semaphore_manager_id: int | None = None
        self._slot_releasers: dict[str, Callable[[], None]] = {}

    def _reconcile_and_get_semaphore(
        self,
        manager: BackgroundTaskManager,
    ) -> tuple[asyncio.Semaphore | None, int]:
        """Return (semaphore, effective_limit) bound to the current loop and manager."""
        loop = asyncio.get_running_loop()
        manager_id = id(manager)
        if self._semaphore_loop is not loop or self._semaphore_manager_id != manager_id:
            self._slot_releasers.clear()
            self._agent_tasks.clear()
            self._inflight_agents.clear()
            self._semaphore = None
            self._semaphore_limit = None
            self._semaphore_loop = loop
            self._semaphore_manager_id = manager_id
        else:
            for aid, releaser in list(self._slot_releasers.items()):
                task_id = self._agent_tasks.get(aid)
                record = manager.get_task(task_id) if task_id and hasattr(manager, "get_task") else None
                if record is not None and record.status in _TERMINAL_TASK_STATUSES:
                    releaser()

        limit = resolve_max_concurrent_teammates(self._max_concurrent_teammates)
        if limit <= 0:
            return None, 0

        if self._semaphore is None or (
            self._semaphore_limit != limit and not self._slot_releasers
        ):
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit
        assert self._semaphore_limit is not None
        return self._semaphore, self._semaphore_limit

    def _active_teammate_count(self, manager: BackgroundTaskManager) -> int:
        """Count active + in-flight teammate tasks that have not finished."""
        active_agents: set[str] = set(self._inflight_agents)
        has_get_task = hasattr(manager, "get_task")
        for agent_id, task_id in self._agent_tasks.items():
            record = manager.get_task(task_id) if has_get_task else None
            if record is None or record.status not in _TERMINAL_TASK_STATUSES:
                active_agents.add(agent_id)
        return len(active_agents)

    def _track_task_slot(
        self,
        manager: BackgroundTaskManager,
        agent_id: str,
        task_id: str,
        semaphore: asyncio.Semaphore,
        initial_record: Any,
    ) -> None:
        """Release a concurrency semaphore slot once *task_id* finishes."""
        released = False
        unregister: Callable[[], None] | None = None

        def _release_slot() -> None:
            nonlocal released, unregister
            if released:
                return
            released = True
            if unregister is not None:
                unregister()
                unregister = None
            if self._slot_releasers.get(agent_id) is _release_slot:
                self._slot_releasers.pop(agent_id, None)
            semaphore.release()

        async def _on_task_complete(task_record: Any) -> None:
            if task_record.id == task_id and task_record.status in _TERMINAL_TASK_STATUSES:
                _release_slot()

        self._slot_releasers[agent_id] = _release_slot
        register_listener = getattr(manager, "register_completion_listener", None)
        if callable(register_listener):
            unregister = register_listener(_on_task_complete)

        current = manager.get_task(task_id) if hasattr(manager, "get_task") else None
        if getattr(initial_record, "status", None) in _TERMINAL_TASK_STATUSES or (
            current is not None and current.status in _TERMINAL_TASK_STATUSES
        ):
            _release_slot()

    def is_available(self) -> bool:
        """Subprocess backend is always available."""
        return True

    async def spawn(self, config: TeammateSpawnConfig) -> SpawnResult:
        """Spawn a new teammate as a subprocess via the task manager.

        Builds the appropriate CLI command and creates a ``local_agent`` task
        that accepts the initial prompt via stdin.
        """
        agent_id = f"{config.name}@{config.team}"
        manager = get_task_manager()
        semaphore, effective_limit = self._reconcile_and_get_semaphore(manager)

        prior_active = self._active_teammate_count(manager)
        warn_if_shared_key_parallel_teammates(
            prior_active,
            logger_obj=logger,
            backend_name="SubprocessBackend",
            max_concurrent=effective_limit,
        )
        self._inflight_agents.add(agent_id)

        flags = build_inherited_cli_flags(
            model=config.model,
            system_prompt=config.system_prompt,
            system_prompt_mode=config.system_prompt_mode,
            plan_mode_required=config.plan_mode_required,
        )
        # Only inject the inherited teammate env vars when we are also
        # building the command ourselves. If the caller supplied a custom
        # ``config.command`` we honour their choice and don't second-guess
        # which env vars they want, matching pre-fix behaviour.
        extra_env: dict[str, str] | None = None
        argv: list[str] | None = None
        command: str | None = config.command
        if command is None:
            # Direct-exec argv list — no shell, no quoting required. This
            # avoids Git Bash on Windows being unable to exec a Windows-
            # pathed python interpreter when bash is itself launched via
            # ``asyncio.create_subprocess_exec`` (see issue #230).
            extra_env = build_inherited_env_vars()
            teammate_cmd = get_teammate_command()
            if (
                teammate_cmd.endswith("python")
                or teammate_cmd.endswith("python3")
                or teammate_cmd.endswith("python.exe")
                or teammate_cmd.endswith("python3.exe")
                or "/python" in teammate_cmd
                or "\\python" in teammate_cmd.lower()
            ):
                argv = [teammate_cmd, "-m", "openharness", "--task-worker"] + flags
            else:
                argv = [teammate_cmd, "--task-worker"] + flags

        acquired_semaphore: asyncio.Semaphore | None = None
        try:
            if semaphore is not None:
                if semaphore.locked():
                    logger.info(
                        "[SubprocessBackend] %s waiting for teammate concurrency slot (limit=%d)",
                        agent_id,
                        effective_limit,
                    )
                await semaphore.acquire()
                acquired_semaphore = semaphore
                prior_releaser = self._slot_releasers.pop(agent_id, None)
                if prior_releaser is not None:
                    prior_releaser()

            try:
                record = await manager.create_agent_task(
                    prompt=config.prompt,
                    description=f"Teammate: {agent_id}",
                    cwd=config.cwd,
                    task_type=config.task_type,
                    model=config.model,
                    command=command,
                    argv=argv,
                    env=extra_env,
                )
            except Exception as exc:
                if acquired_semaphore is not None:
                    acquired_semaphore.release()
                logger.error("Failed to spawn teammate %s: %s", agent_id, exc)
                return SpawnResult(
                    task_id="",
                    agent_id=agent_id,
                    backend_type=self.type,
                    success=False,
                    error=str(exc),
                )

            self._agent_tasks[agent_id] = record.id
            if acquired_semaphore is not None:
                self._track_task_slot(manager, agent_id, record.id, acquired_semaphore, record)
        finally:
            self._inflight_agents.discard(agent_id)
        logger.debug("Spawned teammate %s as task %s", agent_id, record.id)
        return SpawnResult(
            task_id=record.id,
            agent_id=agent_id,
            backend_type=self.type,
        )

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """Send a message to a running teammate via its stdin pipe.

        The message is serialised as a single JSON line so the teammate can
        distinguish structured messages from plain prompts.
        """
        task_id = self._agent_tasks.get(agent_id)
        if task_id is None:
            raise ValueError(f"No active subprocess for agent {agent_id!r}")

        payload = {
            "text": message.text,
            "from": message.from_agent,
            "timestamp": message.timestamp,
        }
        if message.color:
            payload["color"] = message.color
        if message.summary:
            payload["summary"] = message.summary

        manager = get_task_manager()
        await manager.write_to_task(task_id, json.dumps(payload))
        logger.debug("Sent message to %s (task %s)", agent_id, task_id)

    async def shutdown(self, agent_id: str, *, force: bool = False) -> bool:
        """Terminate a subprocess teammate.

        Args:
            agent_id: The agent to terminate.
            force: Ignored for subprocess backend; always sends SIGTERM then
                   SIGKILL after a brief wait (handled by the task manager).

        Returns:
            True if the task was found and terminated.
        """
        task_id = self._agent_tasks.get(agent_id)
        if task_id is None:
            logger.warning("shutdown() called for unknown agent %s", agent_id)
            return False

        manager = get_task_manager()
        try:
            await manager.stop_task(task_id)
        except ValueError as exc:
            logger.debug("stop_task for %s: %s", task_id, exc)
            # Task may have already finished — still clean up mapping
        finally:
            self._agent_tasks.pop(agent_id, None)
            releaser = self._slot_releasers.pop(agent_id, None)
            if releaser is not None:
                releaser()

        logger.debug("Shut down teammate %s (task %s)", agent_id, task_id)
        return True

    def get_task_id(self, agent_id: str) -> str | None:
        """Return the task manager task ID for a given agent, if known."""
        return self._agent_tasks.get(agent_id)
