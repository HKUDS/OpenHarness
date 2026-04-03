"""Persistent team lifecycle management for OpenHarness swarms.

Teams are stored as JSON files on disk:
    ~/.openharness/teams/<name>/team.json

This module provides TeamMember, TeamFile, AllowedPath, TeamLifecycleManager
and a full set of CRUD helpers matching the TS teamHelpers.ts API.
The TeamLifecycleManager can work alongside the in-memory TeamRegistry
in coordinator_mode.py without modifying that module.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from openharness.swarm.mailbox import get_team_dir
from openharness.swarm.types import BackendType


# ---------------------------------------------------------------------------
# Name sanitisation (matching TS sanitizeName / sanitizeAgentName)
# ---------------------------------------------------------------------------


def sanitize_name(name: str) -> str:
    """Replace all non-alphanumeric characters with hyphens and lowercase.

    Mirrors TS ``sanitizeName``:
    ``name.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase()``
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", name).lower()


def sanitize_agent_name(name: str) -> str:
    """Replace ``@`` with ``-`` to avoid ambiguity in agentName@teamName format.

    Mirrors TS ``sanitizeAgentName``:
    ``name.replace(/@/g, '-')``
    """
    return name.replace("@", "-")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AllowedPath:
    """A path that all team members can edit without asking for permission."""

    path: str
    """Absolute directory path."""

    tool_name: str
    """The tool this applies to (e.g. 'Edit', 'Write')."""

    added_by: str
    """Agent name who added this rule."""

    added_at: float = field(default_factory=time.time)
    """Timestamp when the rule was added."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "tool_name": self.tool_name,
            "added_by": self.added_by,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AllowedPath":
        return cls(
            path=data["path"],
            tool_name=data.get("tool_name", data.get("toolName", "")),
            added_by=data.get("added_by", data.get("addedBy", "")),
            added_at=data.get("added_at", data.get("addedAt", time.time())),
        )


@dataclass
class TeamMember:
    """A member of a swarm team."""

    agent_id: str
    name: str
    backend_type: BackendType
    joined_at: float

    # Optional fields matching TS TeamFile member shape
    agent_type: str | None = None
    """Type/role of the agent (e.g. 'researcher', 'test-runner')."""

    model: str | None = None
    """Model identifier used by this agent."""

    prompt: str | None = None
    """Initial system prompt for this agent."""

    color: str | None = None
    """Assigned display colour (e.g. 'red', 'blue', 'green')."""

    plan_mode_required: bool = False
    """Whether this agent requires plan-mode approval before acting."""

    session_id: str | None = None
    """Actual session UUID of this agent (for discovery)."""

    subscriptions: list[str] = field(default_factory=list)
    """Event topics this agent subscribes to."""

    is_active: bool = True
    """False when idle; undefined/True when active."""

    mode: str | None = None
    """Current permission mode for this agent (e.g. 'auto', 'manual')."""

    tmux_pane_id: str = ""
    """Tmux/iTerm2 pane ID for pane-backed agents."""

    cwd: str = ""
    """Working directory for this agent."""

    worktree_path: str | None = None
    """Git worktree path, if the agent operates in an isolated worktree."""

    permissions: list[str] = field(default_factory=list)
    """Legacy permission strings list."""

    status: Literal["active", "idle", "stopped"] = "active"
    """Coarse status of this agent."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "backend_type": self.backend_type,
            "joined_at": self.joined_at,
            "agent_type": self.agent_type,
            "model": self.model,
            "prompt": self.prompt,
            "color": self.color,
            "plan_mode_required": self.plan_mode_required,
            "session_id": self.session_id,
            "subscriptions": self.subscriptions,
            "is_active": self.is_active,
            "mode": self.mode,
            "tmux_pane_id": self.tmux_pane_id,
            "cwd": self.cwd,
            "worktree_path": self.worktree_path,
            "permissions": self.permissions,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamMember":
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            backend_type=data["backend_type"],
            joined_at=data["joined_at"],
            agent_type=data.get("agent_type"),
            model=data.get("model"),
            prompt=data.get("prompt"),
            color=data.get("color"),
            plan_mode_required=data.get("plan_mode_required", False),
            session_id=data.get("session_id"),
            subscriptions=data.get("subscriptions", []),
            is_active=data.get("is_active", True),
            mode=data.get("mode"),
            tmux_pane_id=data.get("tmux_pane_id", ""),
            cwd=data.get("cwd", ""),
            worktree_path=data.get("worktree_path"),
            permissions=data.get("permissions", []),
            status=data.get("status", "active"),
        )


@dataclass
class TeamFile:
    """Persistent team metadata stored as team.json inside the team directory."""

    name: str
    created_at: float

    description: str = ""

    lead_agent_id: str = ""
    """Agent ID of the team leader."""

    lead_session_id: str | None = None
    """Actual session UUID of the leader (for discovery)."""

    hidden_pane_ids: list[str] = field(default_factory=list)
    """Pane IDs that are currently hidden from the UI."""

    members: dict[str, TeamMember] = field(default_factory=dict)
    """Dict mapping agent_id → TeamMember."""

    team_allowed_paths: list[AllowedPath] = field(default_factory=list)
    """Paths all teammates can edit without asking."""

    allowed_paths: list[str] = field(default_factory=list)
    """Legacy list of allowed path strings."""

    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "lead_agent_id": self.lead_agent_id,
            "lead_session_id": self.lead_session_id,
            "hidden_pane_ids": self.hidden_pane_ids,
            "members": {k: v.to_dict() for k, v in self.members.items()},
            "team_allowed_paths": [p.to_dict() for p in self.team_allowed_paths],
            "allowed_paths": self.allowed_paths,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamFile":
        members = {
            k: TeamMember.from_dict(v)
            for k, v in data.get("members", {}).items()
        }
        team_allowed_paths = [
            AllowedPath.from_dict(p)
            for p in data.get("team_allowed_paths", [])
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            created_at=data["created_at"],
            lead_agent_id=data.get("lead_agent_id", ""),
            lead_session_id=data.get("lead_session_id"),
            hidden_pane_ids=data.get("hidden_pane_ids", []),
            members=members,
            team_allowed_paths=team_allowed_paths,
            allowed_paths=data.get("allowed_paths", []),
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Atomically write this team file to *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.rename(path)

    @classmethod
    def load(cls, path: Path) -> "TeamFile":
        """Load a TeamFile from *path*.

        Raises:
            FileNotFoundError: if *path* does not exist.
            json.JSONDecodeError: if the file is not valid JSON.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_TEAM_FILE_NAME = "team.json"


def _team_file_path(name: str) -> Path:
    """Return the path to the team.json for *name*."""
    return get_team_dir(name) / _TEAM_FILE_NAME


def get_team_file_path(team_name: str) -> Path:
    """Public accessor for the team.json path."""
    return _team_file_path(team_name)


# ---------------------------------------------------------------------------
# Synchronous read/write helpers (for sync contexts)
# ---------------------------------------------------------------------------


def read_team_file(team_name: str) -> TeamFile | None:
    """Read and return the TeamFile for *team_name*, or ``None`` if missing.

    Uses synchronous I/O — safe for use in sync contexts such as React-like
    render paths or signal handlers.
    """
    path = _team_file_path(team_name)
    if not path.exists():
        return None
    try:
        return TeamFile.load(path)
    except (json.JSONDecodeError, KeyError):
        return None


def write_team_file(team_name: str, team_file: TeamFile) -> None:
    """Persist *team_file* to disk (synchronous)."""
    team_file.save(_team_file_path(team_name))


# ---------------------------------------------------------------------------
# Async read/write helpers
# ---------------------------------------------------------------------------


async def read_team_file_async(team_name: str) -> TeamFile | None:
    """Async wrapper around :func:`read_team_file`."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_team_file, team_name)


async def write_team_file_async(team_name: str, team_file: TeamFile) -> None:
    """Async wrapper around :func:`write_team_file`."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, write_team_file, team_name, team_file)


# ---------------------------------------------------------------------------
# Member management helpers (standalone functions)
# ---------------------------------------------------------------------------


def remove_teammate_from_team_file(
    team_name: str,
    identifier: dict[str, str | None],
) -> bool:
    """Remove a teammate from the team file by agent_id or name.

    Args:
        team_name: The name of the team.
        identifier: Dict with optional ``agent_id`` and/or ``name`` keys.

    Returns:
        ``True`` if a member was removed, ``False`` otherwise.
    """
    agent_id = identifier.get("agent_id")
    name = identifier.get("name")
    if not agent_id and not name:
        return False

    team_file = read_team_file(team_name)
    if not team_file:
        return False

    original_len = len(team_file.members)
    to_remove = [
        k
        for k, m in team_file.members.items()
        if (agent_id and m.agent_id == agent_id) or (name and m.name == name)
    ]
    for k in to_remove:
        del team_file.members[k]

    if len(team_file.members) == original_len:
        return False

    write_team_file(team_name, team_file)
    return True


def add_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Add *pane_id* to the hidden panes list in the team file.

    Returns:
        ``True`` if successful, ``False`` if the team does not exist.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    if pane_id not in team_file.hidden_pane_ids:
        team_file.hidden_pane_ids.append(pane_id)
        write_team_file(team_name, team_file)
    return True


def remove_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Remove *pane_id* from the hidden panes list in the team file.

    Returns:
        ``True`` if successful, ``False`` if the team does not exist.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    try:
        team_file.hidden_pane_ids.remove(pane_id)
        write_team_file(team_name, team_file)
    except ValueError:
        pass
    return True


def remove_member_from_team(team_name: str, tmux_pane_id: str) -> bool:
    """Remove a team member by tmux pane ID (also removes from hidden panes).

    Returns:
        ``True`` if the member was found and removed, ``False`` otherwise.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    to_remove = [
        k
        for k, m in team_file.members.items()
        if m.tmux_pane_id == tmux_pane_id
    ]
    if not to_remove:
        return False

    for k in to_remove:
        del team_file.members[k]

    # Also clean up hidden_pane_ids
    try:
        team_file.hidden_pane_ids.remove(tmux_pane_id)
    except ValueError:
        pass

    write_team_file(team_name, team_file)
    return True


def remove_member_by_agent_id(team_name: str, agent_id: str) -> bool:
    """Remove a team member by agent ID.

    Use this for in-process teammates which may share the same tmux_pane_id.

    Returns:
        ``True`` if the member was found and removed, ``False`` otherwise.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    if agent_id not in team_file.members:
        return False

    del team_file.members[agent_id]
    write_team_file(team_name, team_file)
    return True


# ---------------------------------------------------------------------------
# Mode and active-status helpers
# ---------------------------------------------------------------------------


def set_member_mode(
    team_name: str,
    member_name: str,
    mode: str,
) -> bool:
    """Set a team member's permission mode.

    Called when the team leader changes a teammate's mode.

    Args:
        team_name: The name of the team.
        member_name: The *name* (not agent_id) of the member to update.
        mode: The new permission mode string (e.g. ``'auto'``, ``'manual'``).

    Returns:
        ``True`` if successful, ``False`` if the team or member is not found.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    member = next(
        (m for m in team_file.members.values() if m.name == member_name), None
    )
    if not member:
        return False

    if member.mode == mode:
        return True

    # Immutably update
    for k, m in team_file.members.items():
        if m.name == member_name:
            team_file.members[k] = TeamMember(
                **{**m.to_dict(), "mode": mode}  # type: ignore[arg-type]
            )
            break

    write_team_file(team_name, team_file)
    return True


def sync_teammate_mode(
    mode: str,
    team_name_override: str | None = None,
) -> None:
    """Sync the current agent's permission mode to the team config file.

    No-op if ``CLAUDE_CODE_AGENT_NAME`` or the resolved team name are not set.

    Args:
        mode: The permission mode to sync.
        team_name_override: Optional override for the team name.
    """
    team_name = team_name_override or os.environ.get("CLAUDE_CODE_TEAM_NAME")
    agent_name = os.environ.get("CLAUDE_CODE_AGENT_NAME")
    if team_name and agent_name:
        set_member_mode(team_name, agent_name, mode)


def set_multiple_member_modes(
    team_name: str,
    mode_updates: list[dict[str, str]],
) -> bool:
    """Set multiple team members' permission modes in a single atomic write.

    Args:
        team_name: The name of the team.
        mode_updates: List of dicts with ``member_name`` and ``mode`` keys.

    Returns:
        ``True`` if the team file was found (even if nothing changed).
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    update_map = {u["member_name"]: u["mode"] for u in mode_updates}
    any_changed = False

    for k, m in list(team_file.members.items()):
        new_mode = update_map.get(m.name)
        if new_mode is not None and m.mode != new_mode:
            team_file.members[k] = TeamMember(
                **{**m.to_dict(), "mode": new_mode}  # type: ignore[arg-type]
            )
            any_changed = True

    if any_changed:
        write_team_file(team_name, team_file)
    return True


async def set_member_active(
    team_name: str,
    member_name: str,
    is_active: bool,
) -> None:
    """Set a team member's active status (async).

    Called when a teammate becomes idle (is_active=False) or starts a new
    turn (is_active=True).

    Args:
        team_name: The name of the team.
        member_name: The *name* of the member to update.
        is_active: Whether the member is active.
    """
    team_file = await read_team_file_async(team_name)
    if not team_file:
        return

    member = next(
        (m for m in team_file.members.values() if m.name == member_name), None
    )
    if not member:
        return

    if member.is_active == is_active:
        return

    for k, m in list(team_file.members.items()):
        if m.name == member_name:
            team_file.members[k] = TeamMember(
                **{**m.to_dict(), "is_active": is_active}  # type: ignore[arg-type]
            )
            break

    await write_team_file_async(team_name, team_file)


# ---------------------------------------------------------------------------
# Session cleanup tracking
# ---------------------------------------------------------------------------

_session_created_teams: set[str] = set()


def register_team_for_session_cleanup(team_name: str) -> None:
    """Mark a team as created this session so it gets cleaned up on exit.

    Call this right after the initial write_team_file.
    :func:`unregister_team_for_session_cleanup` should be called after an
    explicit team deletion to prevent double-cleanup.
    """
    _session_created_teams.add(team_name)


def unregister_team_for_session_cleanup(team_name: str) -> None:
    """Remove a team from session cleanup tracking (e.g. after explicit delete)."""
    _session_created_teams.discard(team_name)


async def _kill_orphaned_teammate_panes(team_name: str) -> None:
    """Best-effort kill of all pane-backed teammate panes for a team.

    Called from :func:`cleanup_session_teams` on ungraceful leader exit
    (SIGINT/SIGTERM).  Deleting directories alone would orphan teammate
    processes in open tmux/iTerm2 panes; this function kills them first.

    Mirrors TS ``killOrphanedTeammatePanes`` in teamHelpers.ts.
    """
    from openharness.swarm.registry import get_backend_registry
    from openharness.swarm.spawn_utils import is_inside_tmux
    from openharness.swarm.types import is_pane_backend

    team_file = read_team_file(team_name)
    if not team_file:
        return

    pane_members = [
        m
        for m in team_file.members.values()
        if m.name != "team-lead"
        and m.tmux_pane_id
        and m.backend_type
        and is_pane_backend(m.backend_type)
    ]
    if not pane_members:
        return

    registry = get_backend_registry()
    use_external_session = not is_inside_tmux()

    async def _kill_one(member: TeamMember) -> None:
        try:
            executor = registry.get_executor(member.backend_type)
            await executor.kill_pane(
                member.tmux_pane_id,
                use_external_session=use_external_session,
            )
        except Exception:
            pass

    await asyncio.gather(*(_kill_one(m) for m in pane_members), return_exceptions=True)


async def cleanup_session_teams() -> None:
    """Clean up all teams created this session that weren't explicitly deleted.

    Kills orphaned teammate panes first, then removes team and task directories
    for every team registered via :func:`register_team_for_session_cleanup`.
    Safe to call multiple times.
    """
    if not _session_created_teams:
        return

    teams = list(_session_created_teams)
    # Kill panes first — on SIGINT the teammate processes are still running;
    # deleting directories alone would orphan them in open tmux/iTerm2 panes.
    await asyncio.gather(
        *(_kill_orphaned_teammate_panes(t) for t in teams),
        return_exceptions=True,
    )
    await asyncio.gather(
        *(cleanup_team_directories(t) for t in teams),
        return_exceptions=True,
    )
    _session_created_teams.clear()


# ---------------------------------------------------------------------------
# Worktree cleanup
# ---------------------------------------------------------------------------


async def _destroy_worktree(worktree_path: str) -> None:
    """Best-effort removal of a git worktree.

    Tries ``git worktree remove --force`` first; falls back to ``shutil.rmtree``.
    """
    wt = Path(worktree_path)
    git_file = wt / ".git"
    main_repo_path: str | None = None

    try:
        content = git_file.read_text(encoding="utf-8").strip()
        match = re.match(r"^gitdir:\s*(.+)$", content)
        if match:
            worktree_git_dir = match.group(1)
            main_git_dir = Path(worktree_git_dir) / ".." / ".."
            main_repo_path = str(main_git_dir / "..")
    except OSError:
        pass

    if main_repo_path:
        try:
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=main_repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return
            if "not a working tree" in (result.stderr or ""):
                return
        except (subprocess.SubprocessError, OSError):
            pass

    try:
        shutil.rmtree(worktree_path, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Team directory cleanup
# ---------------------------------------------------------------------------


async def cleanup_team_directories(team_name: str) -> None:
    """Clean up team and task directories for *team_name*.

    Also removes git worktrees created for team members.  Called when a
    swarm session is terminated.

    Args:
        team_name: The team name to clean up.
    """
    # Read team file to get worktree paths BEFORE deleting the team directory
    team_file = read_team_file(team_name)
    worktree_paths: list[str] = []
    if team_file:
        for member in team_file.members.values():
            if member.worktree_path:
                worktree_paths.append(member.worktree_path)

    # Clean up worktrees first
    for wt_path in worktree_paths:
        await _destroy_worktree(wt_path)

    # Remove the team directory
    team_dir = get_team_dir(team_name)
    try:
        shutil.rmtree(team_dir, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# TeamLifecycleManager
# ---------------------------------------------------------------------------


class TeamLifecycleManager:
    """Manage the on-disk lifecycle of swarm teams.

    Persists team metadata to ``~/.openharness/teams/<name>/team.json``.
    Integrates with the mailbox system's directory layout — the team
    directory created here is the same one that :class:`TeammateMailbox`
    uses, so agents can be added and messaged without separate setup.

    This class is stateless: every method reads from and writes to disk
    directly, making it safe to instantiate multiple times.
    """

    # ------------------------------------------------------------------
    # Team CRUD
    # ------------------------------------------------------------------

    def create_team(self, name: str, description: str = "") -> TeamFile:
        """Create a new team and persist it to disk.

        Raises:
            ValueError: if a team with *name* already exists.
        """
        path = _team_file_path(name)
        if path.exists():
            raise ValueError(f"Team '{name}' already exists at {path}")

        team = TeamFile(
            name=name,
            description=description,
            created_at=time.time(),
        )
        team.save(path)
        return team

    def delete_team(self, name: str) -> None:
        """Remove a team directory and all its contents (mailboxes included).

        Raises:
            ValueError: if the team does not exist.
        """
        team_dir = get_team_dir(name)
        team_file = team_dir / _TEAM_FILE_NAME
        if not team_file.exists():
            raise ValueError(f"Team '{name}' does not exist")
        shutil.rmtree(team_dir)

    def get_team(self, name: str) -> TeamFile | None:
        """Return the TeamFile for *name*, or ``None`` if it does not exist."""
        path = _team_file_path(name)
        if not path.exists():
            return None
        try:
            return TeamFile.load(path)
        except (json.JSONDecodeError, KeyError):
            return None

    def list_teams(self) -> list[TeamFile]:
        """Return all teams found in ``~/.openharness/teams/``, sorted by name."""
        base = Path.home() / ".openharness" / "teams"
        if not base.exists():
            return []

        teams: list[TeamFile] = []
        for team_dir in sorted(base.iterdir()):
            team_file = team_dir / _TEAM_FILE_NAME
            if not team_file.exists():
                continue
            try:
                teams.append(TeamFile.load(team_file))
            except (json.JSONDecodeError, KeyError):
                continue
        return teams

    # ------------------------------------------------------------------
    # Member management
    # ------------------------------------------------------------------

    def add_member(self, team_name: str, member: TeamMember) -> TeamFile:
        """Add *member* to *team_name* and persist.

        If a member with the same ``agent_id`` already exists it is replaced.

        Raises:
            ValueError: if the team does not exist.
        """
        path = _team_file_path(team_name)
        team = self._require_team(team_name, path)
        team.members[member.agent_id] = member
        team.save(path)
        return team

    def remove_member(self, team_name: str, agent_id: str) -> TeamFile:
        """Remove the member with *agent_id* from *team_name* and persist.

        Raises:
            ValueError: if the team or member does not exist.
        """
        path = _team_file_path(team_name)
        team = self._require_team(team_name, path)
        if agent_id not in team.members:
            raise ValueError(
                f"Agent '{agent_id}' is not a member of team '{team_name}'"
            )
        del team.members[agent_id]
        team.save(path)
        return team

    # ------------------------------------------------------------------
    # Mode helpers (proxy to standalone functions)
    # ------------------------------------------------------------------

    def set_member_mode(
        self, team_name: str, member_name: str, mode: str
    ) -> bool:
        """Set a team member's permission mode."""
        return set_member_mode(team_name, member_name, mode)

    async def set_member_active(
        self, team_name: str, member_name: str, is_active: bool
    ) -> None:
        """Set a team member's active status."""
        await set_member_active(team_name, member_name, is_active)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_team(self, name: str, path: Path) -> TeamFile:
        if not path.exists():
            raise ValueError(f"Team '{name}' does not exist")
        return TeamFile.load(path)
