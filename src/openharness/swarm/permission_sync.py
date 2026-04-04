"""Permission sync protocol for leader-worker coordination in OpenHarness swarms.

Provides both file-based (pending/resolved directories) and mailbox-based
permission request/response coordination between swarm workers and the leader.

File-based flow (directory storage):
    1. Worker calls ``write_permission_request()`` → pending/{id}.json
    2. Leader calls ``read_pending_permissions()`` to list pending requests
    3. Leader calls ``resolve_permission()`` → moves to resolved/{id}.json
    4. Worker calls ``read_resolved_permission(id)`` or ``poll_for_response(id)``

Mailbox-based flow:
    1. Worker calls ``send_permission_request_via_mailbox()``
    2. Leader polls mailbox, sends response via ``send_permission_response_via_mailbox()``
    3. Worker calls ``poll_permission_response()`` on its own mailbox

Paths:
    ~/.openharness/teams/<teamName>/permissions/pending/<id>.json
    ~/.openharness/teams/<teamName>/permissions/resolved/<id>.json
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import random
import string
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Literal

from openharness.swarm.mailbox import (
    MailboxMessage,
    TeammateMailbox,
    create_permission_request_message,
    create_permission_response_message,
    create_sandbox_permission_request_message,
    create_sandbox_permission_response_message,
    get_team_dir,
    write_to_mailbox,
)

if TYPE_CHECKING:
    from openharness.permissions.checker import PermissionChecker


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _get_team_name() -> str | None:
    return os.environ.get("CLAUDE_CODE_TEAM_NAME")


def _get_agent_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_AGENT_ID")


def _get_agent_name() -> str | None:
    return os.environ.get("CLAUDE_CODE_AGENT_NAME")


def _get_teammate_color() -> str | None:
    return os.environ.get("CLAUDE_CODE_AGENT_COLOR")


# ---------------------------------------------------------------------------
# Read-only tool heuristic
# ---------------------------------------------------------------------------

_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        "WebFetch",
        "WebSearch",
        "TaskGet",
        "TaskList",
        "TaskOutput",
        "CronList",
    }
)


def _is_read_only(tool_name: str) -> bool:
    """Return True for tools that are considered safe/read-only."""
    return tool_name in _READ_ONLY_TOOLS


# ---------------------------------------------------------------------------
# File locking helper
# ---------------------------------------------------------------------------


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive POSIX file lock on *lock_path*."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SwarmPermissionRequest:
    """Permission request forwarded from a worker to the team leader.

    All fields are present to match the TS SwarmPermissionRequestSchema.
    """

    id: str
    """Unique identifier for this request."""

    worker_id: str
    """The requesting worker's agent ID (CLAUDE_CODE_AGENT_ID)."""

    worker_name: str
    """The requesting worker's agent name (CLAUDE_CODE_AGENT_NAME)."""

    team_name: str
    """Team name for routing."""

    tool_name: str
    """Name of the tool requiring permission (e.g. 'Bash', 'Edit')."""

    tool_use_id: str
    """Original tool-use ID from the worker's execution context."""

    description: str
    """Human-readable description of the requested operation."""

    input: dict[str, Any]
    """Serialized tool input parameters."""

    # Optional / defaulted fields
    permission_suggestions: list[Any] = field(default_factory=list)
    """Suggested rule updates produced by the worker's local permission system."""

    worker_color: str | None = None
    """The requesting worker's assigned color (CLAUDE_CODE_AGENT_COLOR)."""

    status: Literal["pending", "approved", "rejected"] = "pending"
    """Current status of the request."""

    resolved_by: Literal["worker", "leader"] | None = None
    """Who resolved the request."""

    resolved_at: float | None = None
    """Timestamp (seconds since epoch) when the request was resolved."""

    feedback: str | None = None
    """Optional rejection reason or leader comment."""

    updated_input: dict[str, Any] | None = None
    """Modified input if changed by the resolver."""

    permission_updates: list[Any] | None = None
    """'Always allow' rules applied during resolution."""

    created_at: float = field(default_factory=time.time)
    """Timestamp when request was created."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "worker_id": self.worker_id,
            "worker_name": self.worker_name,
            "team_name": self.team_name,
            "tool_name": self.tool_name,
            "tool_use_id": self.tool_use_id,
            "description": self.description,
            "input": self.input,
            "permission_suggestions": self.permission_suggestions,
            "worker_color": self.worker_color,
            "status": self.status,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "feedback": self.feedback,
            "updated_input": self.updated_input,
            "permission_updates": self.permission_updates,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwarmPermissionRequest":
        return cls(
            id=data["id"],
            worker_id=data.get("worker_id", data.get("workerId", "")),
            worker_name=data.get("worker_name", data.get("workerName", "")),
            team_name=data.get("team_name", data.get("teamName", "")),
            tool_name=data.get("tool_name", data.get("toolName", "")),
            tool_use_id=data.get("tool_use_id", data.get("toolUseId", "")),
            description=data.get("description", ""),
            input=data.get("input", {}),
            permission_suggestions=data.get(
                "permission_suggestions",
                data.get("permissionSuggestions", []),
            ),
            worker_color=data.get("worker_color", data.get("workerColor")),
            status=data.get("status", "pending"),
            resolved_by=data.get("resolved_by", data.get("resolvedBy")),
            resolved_at=data.get("resolved_at", data.get("resolvedAt")),
            feedback=data.get("feedback"),
            updated_input=data.get("updated_input", data.get("updatedInput")),
            permission_updates=data.get(
                "permission_updates", data.get("permissionUpdates")
            ),
            created_at=data.get("created_at", data.get("createdAt", time.time())),
        )


@dataclass
class PermissionResolution:
    """Resolution data returned when leader/worker resolves a request."""

    decision: Literal["approved", "rejected"]
    """Decision: approved or rejected."""

    resolved_by: Literal["worker", "leader"]
    """Who resolved the request."""

    feedback: str | None = None
    """Optional feedback message if rejected."""

    updated_input: dict[str, Any] | None = None
    """Optional updated input if the resolver modified it."""

    permission_updates: list[Any] | None = None
    """Permission updates to apply (e.g. 'always allow' rules)."""


@dataclass
class PermissionResponse:
    """Legacy response type for worker polling (backward compatibility)."""

    request_id: str
    """ID of the request this responds to."""

    decision: Literal["approved", "denied"]
    """Decision: approved or denied."""

    timestamp: str
    """ISO timestamp when response was created."""

    feedback: str | None = None
    """Optional feedback message if denied."""

    updated_input: dict[str, Any] | None = None
    """Optional updated input if the resolver modified it."""

    permission_updates: list[Any] | None = None
    """Permission updates to apply."""


@dataclass
class SwarmPermissionResponse:
    """Response sent from the leader back to the requesting worker."""

    request_id: str
    """ID of the ``SwarmPermissionRequest`` this responds to."""

    allowed: bool
    """True if the tool use is approved."""

    feedback: str | None = None
    """Optional rejection reason or leader comment."""

    updated_rules: list[dict[str, Any]] = field(default_factory=list)
    """Permission-rule updates the leader decided to apply."""


# ---------------------------------------------------------------------------
# Request ID generation
# ---------------------------------------------------------------------------


def generate_request_id() -> str:
    """Generate a unique permission request ID.

    Format: ``perm-{timestamp_ms}-{random7}``, matching the TS implementation:
    ``perm-${Date.now()}-${Math.random().toString(36).substring(2, 9)}``
    """
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    return f"perm-{ts}-{rand}"


def generate_sandbox_request_id() -> str:
    """Generate a unique sandbox permission request ID.

    Format: ``sandbox-{timestamp_ms}-{random7}``.
    """
    ts = int(time.time() * 1000)
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    return f"sandbox-{ts}-{rand}"


# ---------------------------------------------------------------------------
# Permission directory helpers
# ---------------------------------------------------------------------------


def get_permission_dir(team_name: str) -> Path:
    """Return ~/.openharness/teams/{teamName}/permissions/"""
    return get_team_dir(team_name) / "permissions"


def _get_pending_dir(team_name: str) -> Path:
    return get_permission_dir(team_name) / "pending"


def _get_resolved_dir(team_name: str) -> Path:
    return get_permission_dir(team_name) / "resolved"


def _ensure_permission_dirs(team_name: str) -> None:
    for d in (
        get_permission_dir(team_name),
        _get_pending_dir(team_name),
        _get_resolved_dir(team_name),
    ):
        d.mkdir(parents=True, exist_ok=True)


def _pending_request_path(team_name: str, request_id: str) -> Path:
    return _get_pending_dir(team_name) / f"{request_id}.json"


def _resolved_request_path(team_name: str, request_id: str) -> Path:
    return _get_resolved_dir(team_name) / f"{request_id}.json"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_permission_request(
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, Any],
    description: str = "",
    permission_suggestions: list[Any] | None = None,
    team_name: str | None = None,
    worker_id: str | None = None,
    worker_name: str | None = None,
    worker_color: str | None = None,
) -> SwarmPermissionRequest:
    """Build a new :class:`SwarmPermissionRequest` with a generated ID.

    Missing worker/team fields are read from environment variables
    (``CLAUDE_CODE_AGENT_ID``, ``CLAUDE_CODE_AGENT_NAME``,
    ``CLAUDE_CODE_TEAM_NAME``, ``CLAUDE_CODE_AGENT_COLOR``).

    Args:
        tool_name: Name of the tool requesting permission.
        tool_use_id: Original tool-use ID from the execution context.
        tool_input: The tool's input parameters.
        description: Optional human-readable description of the operation.
        permission_suggestions: Optional list of suggested permission-rule dicts.
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).
        worker_id: Worker agent ID (falls back to ``CLAUDE_CODE_AGENT_ID``).
        worker_name: Worker agent name (falls back to ``CLAUDE_CODE_AGENT_NAME``).
        worker_color: Worker color (falls back to ``CLAUDE_CODE_AGENT_COLOR``).

    Returns:
        A new :class:`SwarmPermissionRequest` in *pending* state.

    Raises:
        ValueError: if team_name, worker_id, or worker_name cannot be resolved.
    """
    resolved_team = team_name or _get_team_name() or ""
    resolved_id = worker_id or _get_agent_id() or ""
    resolved_name = worker_name or _get_agent_name() or ""
    resolved_color = worker_color or _get_teammate_color()

    return SwarmPermissionRequest(
        id=generate_request_id(),
        worker_id=resolved_id,
        worker_name=resolved_name,
        worker_color=resolved_color,
        team_name=resolved_team,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        description=description,
        input=tool_input,
        permission_suggestions=permission_suggestions or [],
        status="pending",
        created_at=time.time(),
    )


# ---------------------------------------------------------------------------
# File-based storage: write / read / resolve / cleanup
# ---------------------------------------------------------------------------


def _sync_write_permission_request(
    request: SwarmPermissionRequest,
) -> SwarmPermissionRequest:
    _ensure_permission_dirs(request.team_name)
    pending_path = _pending_request_path(request.team_name, request.id)
    lock_path = _get_pending_dir(request.team_name) / ".lock"

    with _file_lock(lock_path):
        pending_path.write_text(
            json.dumps(request.to_dict(), indent=2), encoding="utf-8"
        )
    return request


async def write_permission_request(
    request: SwarmPermissionRequest,
) -> SwarmPermissionRequest:
    """Write *request* to the pending directory with file locking.

    Called by worker agents when they need permission approval from the leader.

    Args:
        request: The permission request to persist.

    Returns:
        The written request (same object, for convenience).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_write_permission_request, request)


async def read_pending_permissions(
    team_name: str | None = None,
) -> list[SwarmPermissionRequest]:
    """Read all pending permission requests for a team.

    Called by the team leader to see what requests need attention.  Requests
    are returned sorted oldest-first.

    Args:
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        List of pending :class:`SwarmPermissionRequest` objects.
    """
    team = team_name or _get_team_name()
    if not team:
        return []

    pending_dir = _get_pending_dir(team)
    if not pending_dir.exists():
        return []

    requests: list[SwarmPermissionRequest] = []
    for path in sorted(pending_dir.glob("*.json")):
        if path.name == ".lock":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            requests.append(SwarmPermissionRequest.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue

    requests.sort(key=lambda r: r.created_at)
    return requests


async def read_resolved_permission(
    request_id: str,
    team_name: str | None = None,
) -> SwarmPermissionRequest | None:
    """Read a resolved permission request by ID.

    Called by workers to check if their request has been resolved.

    Args:
        request_id: The permission request ID to look up.
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        The resolved :class:`SwarmPermissionRequest`, or ``None`` if not yet
        resolved.
    """
    team = team_name or _get_team_name()
    if not team:
        return None

    resolved_path = _resolved_request_path(team, request_id)
    if not resolved_path.exists():
        return None

    try:
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
        return SwarmPermissionRequest.from_dict(data)
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def _sync_resolve_permission(
    request_id: str,
    resolution: PermissionResolution,
    team: str,
) -> bool:
    _ensure_permission_dirs(team)
    pending_path = _pending_request_path(team, request_id)
    resolved_path = _resolved_request_path(team, request_id)
    lock_path = _get_pending_dir(team) / ".lock"

    with _file_lock(lock_path):
        if not pending_path.exists():
            return False

        try:
            data = json.loads(pending_path.read_text(encoding="utf-8"))
            request = SwarmPermissionRequest.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return False

        resolved_request = SwarmPermissionRequest(
            id=request.id,
            worker_id=request.worker_id,
            worker_name=request.worker_name,
            worker_color=request.worker_color,
            team_name=request.team_name,
            tool_name=request.tool_name,
            tool_use_id=request.tool_use_id,
            description=request.description,
            input=request.input,
            permission_suggestions=request.permission_suggestions,
            status="approved" if resolution.decision == "approved" else "rejected",
            resolved_by=resolution.resolved_by,
            resolved_at=time.time(),
            feedback=resolution.feedback,
            updated_input=resolution.updated_input,
            permission_updates=resolution.permission_updates,
            created_at=request.created_at,
        )

        resolved_path.write_text(
            json.dumps(resolved_request.to_dict(), indent=2), encoding="utf-8"
        )
        try:
            pending_path.unlink()
        except OSError:
            pass

    return True


async def resolve_permission(
    request_id: str,
    resolution: PermissionResolution,
    team_name: str | None = None,
) -> bool:
    """Resolve a permission request, moving it from pending/ to resolved/.

    Called by the team leader (or worker in self-resolution cases).

    Args:
        request_id: The permission request ID to resolve.
        resolution: The resolution data (decision, resolvedBy, etc.).
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        ``True`` if the request was found and resolved, ``False`` otherwise.
    """
    team = team_name or _get_team_name()
    if not team:
        return False
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _sync_resolve_permission, request_id, resolution, team
    )


def _sync_cleanup_old_resolutions(team: str, max_age_seconds: float) -> int:
    resolved_dir = _get_resolved_dir(team)
    if not resolved_dir.exists():
        return 0

    now = time.time()
    cleaned = 0

    for path in resolved_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            resolved_at = data.get("resolved_at") or data.get("created_at", 0)
            if now - resolved_at >= max_age_seconds:
                path.unlink()
                cleaned += 1
        except (json.JSONDecodeError, KeyError, OSError):
            try:
                path.unlink()
                cleaned += 1
            except OSError:
                pass

    return cleaned


async def cleanup_old_resolutions(
    team_name: str | None = None,
    max_age_seconds: float = 3600.0,
) -> int:
    """Clean up old resolved permission files.

    Called periodically to prevent file accumulation.

    Args:
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).
        max_age_seconds: Maximum age in seconds (default: 1 hour).

    Returns:
        Number of files removed.
    """
    team = team_name or _get_team_name()
    if not team:
        return 0
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _sync_cleanup_old_resolutions, team, max_age_seconds
    )


async def delete_resolved_permission(
    request_id: str,
    team_name: str | None = None,
) -> bool:
    """Delete a resolved permission file after a worker has processed it.

    Args:
        request_id: The permission request ID.
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        ``True`` if the file was found and deleted, ``False`` otherwise.
    """
    team = team_name or _get_team_name()
    if not team:
        return False

    resolved_path = _resolved_request_path(team, request_id)
    try:
        resolved_path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Legacy / backward-compat helpers
# ---------------------------------------------------------------------------


async def poll_for_response(
    request_id: str,
    _agent_name: str | None = None,
    team_name: str | None = None,
) -> PermissionResponse | None:
    """Poll for a permission response (worker-side convenience function).

    Converts the resolved request into the simpler legacy response format.

    Args:
        request_id: The permission request ID to check.
        _agent_name: Unused; kept for API compatibility.
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        A :class:`PermissionResponse`, or ``None`` if not yet resolved.
    """
    from datetime import datetime, timezone

    resolved = await read_resolved_permission(request_id, team_name)
    if not resolved:
        return None

    ts = resolved.resolved_at or resolved.created_at
    return PermissionResponse(
        request_id=resolved.id,
        decision="approved" if resolved.status == "approved" else "denied",
        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3]
        + "Z",
        feedback=resolved.feedback,
        updated_input=resolved.updated_input,
        permission_updates=resolved.permission_updates,
    )


async def remove_worker_response(
    request_id: str,
    _agent_name: str | None = None,
    team_name: str | None = None,
) -> None:
    """Remove a worker's response after processing (alias for delete_resolved_permission)."""
    await delete_resolved_permission(request_id, team_name)


# Alias: submitPermissionRequest → writePermissionRequest
submit_permission_request = write_permission_request


# ---------------------------------------------------------------------------
# Team leader / worker role detection
# ---------------------------------------------------------------------------


def is_team_leader(team_name: str | None = None) -> bool:
    """Return True if the current agent is a team leader.

    Team leaders don't have an agent ID set, or their ID is 'team-lead'.
    """
    team = team_name or _get_team_name()
    if not team:
        return False
    agent_id = _get_agent_id()
    return not agent_id or agent_id == "team-lead"


def is_swarm_worker() -> bool:
    """Return True if the current agent is a worker in a swarm."""
    team_name = _get_team_name()
    agent_id = _get_agent_id()
    return bool(team_name) and bool(agent_id) and not is_team_leader()


# ---------------------------------------------------------------------------
# Leader name lookup
# ---------------------------------------------------------------------------


async def get_leader_name(team_name: str | None = None) -> str | None:
    """Get the leader's agent name from the team file.

    This is needed to address permission requests to the leader's mailbox.

    Args:
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        The leader's name string, or ``None`` if the team file is missing.
        Falls back to ``'team-lead'`` if the lead member is not found.
    """
    from openharness.swarm.team_lifecycle import read_team_file_async

    team = team_name or _get_team_name()
    if not team:
        return None

    team_file = await read_team_file_async(team)
    if not team_file:
        return None

    lead_id = team_file.lead_agent_id
    if lead_id and lead_id in team_file.members:
        return team_file.members[lead_id].name

    return "team-lead"


# ---------------------------------------------------------------------------
# Mailbox-based permission send/receive
# ---------------------------------------------------------------------------


async def send_permission_request_via_mailbox(
    request: SwarmPermissionRequest,
) -> bool:
    """Send a permission request to the leader via the mailbox system.

    This is the mailbox-based approach for forwarding permission requests.
    Writes a ``permission_request`` message to the leader's mailbox.

    Args:
        request: The permission request to send.

    Returns:
        ``True`` if the message was sent successfully.
    """
    leader_name = await get_leader_name(request.team_name)
    if not leader_name:
        return False

    try:
        msg = create_permission_request_message(
            sender=request.worker_name,
            recipient=leader_name,
            request_data={
                "request_id": request.id,
                "agent_id": request.worker_name,
                "tool_name": request.tool_name,
                "tool_use_id": request.tool_use_id,
                "description": request.description,
                "input": request.input,
                "permission_suggestions": request.permission_suggestions,
            },
        )

        await write_to_mailbox(
            leader_name,
            {
                "from": request.worker_name,
                "text": json.dumps(msg.payload),
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                ),
                "color": request.worker_color,
            },
            request.team_name,
        )
        return True
    except OSError:
        return False


async def send_permission_response_via_mailbox(
    worker_name: str,
    resolution: PermissionResolution,
    request_id: str,
    team_name: str | None = None,
) -> bool:
    """Send a permission response to a worker via the mailbox system.

    Called by the leader when approving/denying a permission request.

    Args:
        worker_name: The worker's name to send the response to.
        resolution: The permission resolution.
        request_id: The original request ID.
        team_name: Team name (falls back to ``CLAUDE_CODE_TEAM_NAME``).

    Returns:
        ``True`` if the message was sent successfully.
    """
    team = team_name or _get_team_name()
    if not team:
        return False

    sender_name = _get_agent_name() or "team-lead"
    subtype = "success" if resolution.decision == "approved" else "error"

    try:
        msg = create_permission_response_message(
            sender=sender_name,
            recipient=worker_name,
            response_data={
                "request_id": request_id,
                "subtype": subtype,
                "error": resolution.feedback if subtype == "error" else None,
                "updated_input": resolution.updated_input,
                "permission_updates": resolution.permission_updates,
            },
        )

        await write_to_mailbox(
            worker_name,
            {
                "from": sender_name,
                "text": json.dumps(msg.payload),
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                ),
            },
            team,
        )
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Sandbox permission mailbox helpers
# ---------------------------------------------------------------------------


async def send_sandbox_permission_request_via_mailbox(
    host: str,
    request_id: str,
    team_name: str | None = None,
) -> bool:
    """Send a sandbox permission request to the leader via the mailbox system.

    Called by workers when sandbox runtime needs network access approval.

    Args:
        host: The host requesting network access.
        request_id: Unique ID for this request.
        team_name: Optional team name.

    Returns:
        ``True`` if the message was sent successfully.
    """
    team = team_name or _get_team_name()
    if not team:
        return False

    leader_name = await get_leader_name(team)
    if not leader_name:
        return False

    worker_id = _get_agent_id()
    worker_name = _get_agent_name()
    worker_color = _get_teammate_color()

    if not worker_id or not worker_name:
        return False

    try:
        msg = create_sandbox_permission_request_message(
            sender=worker_name,
            recipient=leader_name,
            request_data={
                "requestId": request_id,
                "workerId": worker_id,
                "workerName": worker_name,
                "workerColor": worker_color,
                "host": host,
            },
        )

        await write_to_mailbox(
            leader_name,
            {
                "from": worker_name,
                "text": json.dumps(msg.payload),
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                ),
                "color": worker_color,
            },
            team,
        )
        return True
    except OSError:
        return False


async def send_sandbox_permission_response_via_mailbox(
    worker_name: str,
    request_id: str,
    host: str,
    allow: bool,
    team_name: str | None = None,
) -> bool:
    """Send a sandbox permission response to a worker via the mailbox system.

    Called by the leader when approving/denying a sandbox network access request.

    Args:
        worker_name: The worker's name to send the response to.
        request_id: The original request ID.
        host: The host that was approved/denied.
        allow: Whether the connection is allowed.
        team_name: Optional team name.

    Returns:
        ``True`` if the message was sent successfully.
    """
    team = team_name or _get_team_name()
    if not team:
        return False

    sender_name = _get_agent_name() or "team-lead"

    try:
        msg = create_sandbox_permission_response_message(
            sender=sender_name,
            recipient=worker_name,
            response_data={
                "requestId": request_id,
                "host": host,
                "allow": allow,
            },
        )

        await write_to_mailbox(
            worker_name,
            {
                "from": sender_name,
                "text": json.dumps(msg.payload),
                "timestamp": time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                ),
            },
            team,
        )
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Worker helpers: send request / poll response (original mailbox-only approach)
# ---------------------------------------------------------------------------


async def send_permission_request(
    request: SwarmPermissionRequest,
    team_name: str,
    worker_id: str,
    leader_id: str = "leader",
) -> None:
    """Serialize *request* and write it to the leader's mailbox.

    This is the original structured-payload approach.  For new code prefer
    :func:`send_permission_request_via_mailbox`.

    Args:
        request: The permission request to forward.
        team_name: The swarm team name used for mailbox routing.
        worker_id: The sending worker's agent ID.
        leader_id: The leader's agent ID (default ``"leader"``).
    """
    payload: dict[str, Any] = {
        "request_id": request.id,
        "tool_name": request.tool_name,
        "tool_use_id": request.tool_use_id,
        "input": request.input,
        "description": request.description,
        "permission_suggestions": request.permission_suggestions,
        "worker_id": worker_id,
    }
    msg = MailboxMessage(
        id=str(uuid.uuid4()),
        type="permission_request",
        sender=worker_id,
        recipient=leader_id,
        payload=payload,
        timestamp=time.time(),
    )
    leader_mailbox = TeammateMailbox(team_name, leader_id)
    await leader_mailbox.write(msg)


async def poll_permission_response(
    team_name: str,
    worker_id: str,
    request_id: str,
    timeout: float = 60.0,
) -> SwarmPermissionResponse | None:
    """Poll the worker's own mailbox until a matching ``permission_response`` arrives.

    Checks every 0.5 s up to *timeout* seconds.  When a response matching
    *request_id* is found, the message is marked read and the decoded
    :class:`SwarmPermissionResponse` is returned.

    Args:
        team_name: The swarm team name.
        worker_id: The worker's agent ID (owns this mailbox).
        request_id: The ``SwarmPermissionRequest.id`` to match against.
        timeout: Maximum seconds to wait before returning ``None``.

    Returns:
        A :class:`SwarmPermissionResponse`, or ``None`` on timeout.
    """
    worker_mailbox = TeammateMailbox(team_name, worker_id)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        messages = await worker_mailbox.read_all(unread_only=True)
        for msg in messages:
            if msg.type == "permission_response":
                payload = msg.payload
                if payload.get("request_id") == request_id:
                    await worker_mailbox.mark_read(msg.id)
                    return SwarmPermissionResponse(
                        request_id=payload["request_id"],
                        allowed=bool(payload.get("allowed", False)),
                        feedback=payload.get("feedback"),
                        updated_rules=payload.get("updated_rules", []),
                    )
        await asyncio.sleep(0.5)

    return None


# ---------------------------------------------------------------------------
# Leader helper: evaluate and send response
# ---------------------------------------------------------------------------


async def handle_permission_request(
    request: SwarmPermissionRequest,
    checker: "PermissionChecker",
) -> SwarmPermissionResponse:
    """Evaluate *request* using the existing :class:`PermissionChecker`.

    Read-only tools are auto-approved without consulting the checker.  For
    all other tools the checker's ``evaluate`` method is called; if the tool
    is allowed or only requires confirmation (and nothing blocks it), it is
    approved; otherwise it is denied.

    Args:
        request: The incoming permission request from a worker.
        checker: An already-configured :class:`~openharness.permissions.checker.PermissionChecker`.

    Returns:
        A :class:`SwarmPermissionResponse` with the decision.
    """
    if _is_read_only(request.tool_name):
        return SwarmPermissionResponse(
            request_id=request.id,
            allowed=True,
            feedback=None,
        )

    file_path: str | None = (
        request.input.get("file_path")  # type: ignore[assignment]
        or request.input.get("path")
        or None
    )
    command: str | None = request.input.get("command")  # type: ignore[assignment]

    decision = checker.evaluate(
        request.tool_name,
        is_read_only=False,
        file_path=file_path,
        command=command,
    )

    allowed = decision.allowed
    feedback: str | None = None if allowed else decision.reason

    return SwarmPermissionResponse(
        request_id=request.id,
        allowed=allowed,
        feedback=feedback,
    )


# ---------------------------------------------------------------------------
# Leader helper: write response back to a worker's mailbox
# ---------------------------------------------------------------------------


async def send_permission_response(
    response: SwarmPermissionResponse,
    team_name: str,
    worker_id: str,
    leader_id: str = "leader",
) -> None:
    """Write *response* to the worker's mailbox.

    This is the original structured-payload approach.  For new code prefer
    :func:`send_permission_response_via_mailbox`.

    Args:
        response: The resolution to send.
        team_name: The swarm team name.
        worker_id: The target worker's agent ID.
        leader_id: The sending leader's agent ID (default ``"leader"``).
    """
    payload: dict[str, Any] = {
        "request_id": response.request_id,
        "allowed": response.allowed,
        "feedback": response.feedback,
        "updated_rules": response.updated_rules,
    }
    msg = MailboxMessage(
        id=str(uuid.uuid4()),
        type="permission_response",
        sender=leader_id,
        recipient=worker_id,
        payload=payload,
        timestamp=time.time(),
    )
    worker_mailbox = TeammateMailbox(team_name, worker_id)
    await worker_mailbox.write(msg)
