"""Swarm backend type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Backend type literals
# ---------------------------------------------------------------------------

BackendType = Literal["subprocess", "in_process", "tmux", "iterm2"]
"""All supported backend types."""

PaneBackendType = Literal["tmux", "iterm2"]
"""Subset of BackendType for pane-based (visual) backends only."""

PaneId = str
"""Opaque identifier for a terminal pane managed by a backend.

For tmux this is the pane ID (e.g. ``"%1"``).
For iTerm2 this is the session ID returned by ``it2``.
"""


# ---------------------------------------------------------------------------
# Pane backend types
# ---------------------------------------------------------------------------


@dataclass
class CreatePaneResult:
    """Result of creating a new teammate pane."""

    pane_id: PaneId
    """The pane ID for the newly created pane."""

    is_first_teammate: bool
    """Whether this is the first teammate pane (affects layout strategy)."""


@runtime_checkable
class PaneBackend(Protocol):
    """Protocol for pane management backends (tmux / iTerm2).

    Abstracts operations for creating and managing terminal panes for teammate
    visualization in swarm mode.
    """

    @property
    def type(self) -> BackendType:
        """The type identifier for this backend."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable display name for this backend."""
        ...

    @property
    def supports_hide_show(self) -> bool:
        """Whether this backend supports hiding and showing panes."""
        ...

    async def is_available(self) -> bool:
        """Return True if this backend is available on the system.

        For tmux: checks if the tmux binary exists.
        For iTerm2: checks if it2 CLI is installed and configured.
        """
        ...

    async def is_running_inside(self) -> bool:
        """Return True if we are currently inside this backend's environment.

        For tmux: checks if we are in a tmux session (``$TMUX`` set).
        For iTerm2: checks if we are running inside iTerm2.
        """
        ...

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: str | None = None,
    ) -> CreatePaneResult:
        """Create a new pane for a teammate in the swarm view.

        Args:
            name: The teammate's display name.
            color: Optional color name for the pane border / title.

        Returns:
            :class:`CreatePaneResult` with the pane ID and first-teammate flag.
        """
        ...

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        *,
        use_external_session: bool = False,
    ) -> None:
        """Send a shell command to execute in *pane_id*.

        Args:
            pane_id: Target pane.
            command: Command string to execute.
            use_external_session: If True, use external session socket (tmux only).
        """
        ...

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: str,
        *,
        use_external_session: bool = False,
    ) -> None:
        """Set the border color for *pane_id*."""
        ...

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: str | None = None,
        *,
        use_external_session: bool = False,
    ) -> None:
        """Set the title displayed in the border / header of *pane_id*."""
        ...

    async def enable_pane_border_status(
        self,
        window_target: str | None = None,
        *,
        use_external_session: bool = False,
    ) -> None:
        """Enable pane border status display (shows titles in borders)."""
        ...

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalance panes to achieve the desired layout.

        Args:
            window_target: The window containing the panes.
            has_leader: Whether there is a leader pane (affects strategy).
        """
        ...

    async def kill_pane(
        self,
        pane_id: PaneId,
        *,
        use_external_session: bool = False,
    ) -> bool:
        """Kill / close *pane_id*.

        Returns:
            True if the pane was killed successfully.
        """
        ...

    async def hide_pane(
        self,
        pane_id: PaneId,
        *,
        use_external_session: bool = False,
    ) -> bool:
        """Hide *pane_id* by breaking it out into a hidden window.

        The pane remains running but is not visible in the main layout.

        Returns:
            True if the pane was hidden successfully.
        """
        ...

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        *,
        use_external_session: bool = False,
    ) -> bool:
        """Show a previously hidden pane by joining it back into the main window.

        Returns:
            True if the pane was shown successfully.
        """
        ...

    def list_panes(self) -> list[PaneId]:
        """Return a list of all known pane IDs managed by this backend."""
        ...


# ---------------------------------------------------------------------------
# Backend detection result
# ---------------------------------------------------------------------------


@dataclass
class BackendDetectionResult:
    """Result from backend auto-detection.

    Attributes:
        backend: The backend that should be used.
        is_native: Whether we are running inside the backend's native env.
        needs_setup: True when iTerm2 is detected but ``it2`` is not installed.
    """

    backend: str
    """Backend type string (e.g. ``"tmux"``, ``"in_process"``)."""

    is_native: bool
    """True if running inside the backend's own environment."""

    needs_setup: bool = False
    """True when additional setup is needed (e.g. install ``it2``)."""


# ---------------------------------------------------------------------------
# Teammate identity & spawn configuration
# ---------------------------------------------------------------------------


@dataclass
class TeammateIdentity:
    """Identity fields for a teammate agent."""

    agent_id: str
    """Unique agent identifier (format: agentName@teamName)."""

    name: str
    """Agent name (e.g. 'researcher', 'tester')."""

    team: str
    """Team name this teammate belongs to."""

    color: str | None = None
    """Assigned color for UI differentiation."""

    parent_session_id: str | None = None
    """Parent session ID for context linking."""


@dataclass
class TeammateSpawnConfig:
    """Configuration for spawning a teammate (any execution mode)."""

    name: str
    """Human-readable teammate name (e.g. ``"researcher"``)."""

    team: str
    """Team name this teammate belongs to."""

    prompt: str
    """Initial prompt / task for the teammate."""

    cwd: str
    """Working directory for the teammate."""

    parent_session_id: str
    """Parent session ID (for transcript correlation)."""

    model: str | None = None
    """Model override for this teammate."""

    system_prompt: str | None = None
    """System prompt resolved from workflow config."""

    system_prompt_mode: Literal["default", "replace", "append"] | None = None
    """How to apply the system prompt: replace or append to default."""

    color: str | None = None
    """Optional UI color for the teammate."""

    color_override: str | None = None
    """Explicit color override (takes precedence over ``color``)."""

    permissions: list[str] = field(default_factory=list)
    """Tool permissions to grant this teammate."""

    plan_mode_required: bool = False
    """Whether this teammate must enter plan mode before implementing."""

    allow_permission_prompts: bool = False
    """When False (default), unlisted tools are auto-denied."""

    worktree_path: str | None = None
    """Optional git worktree path for isolated filesystem access."""

    session_id: str | None = None
    """Explicit session ID (generated if not provided)."""

    subscriptions: list[str] = field(default_factory=list)
    """Event topics this teammate subscribes to."""


# ---------------------------------------------------------------------------
# Spawn result & messaging
# ---------------------------------------------------------------------------


@dataclass
class SpawnResult:
    """Result from spawning a teammate."""

    task_id: str
    """Task ID in the task manager."""

    agent_id: str
    """Unique agent identifier (format: agentName@teamName)."""

    backend_type: BackendType
    """The backend used to spawn this agent."""

    success: bool = True
    error: str | None = None

    pane_id: PaneId | None = None
    """Pane ID for pane-based backends (tmux / iTerm2)."""


@dataclass
class TeammateMessage:
    """Message to send to a teammate."""

    text: str
    from_agent: str
    color: str | None = None
    timestamp: str | None = None
    summary: str | None = None


# ---------------------------------------------------------------------------
# TeammateExecutor protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TeammateExecutor(Protocol):
    """Protocol for teammate execution backends.

    Abstracts spawn/messaging/shutdown across subprocess, in-process, and tmux backends.
    """

    type: BackendType

    def is_available(self) -> bool:
        """Check if this backend is available on the system."""
        ...

    async def spawn(self, config: TeammateSpawnConfig) -> SpawnResult:
        """Spawn a new teammate with the given configuration."""
        ...

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """Send a message to a running teammate via stdin."""
        ...

    async def shutdown(self, agent_id: str, *, force: bool = False) -> bool:
        """Terminate a teammate.

        Args:
            agent_id: The agent to terminate.
            force: If True, kill immediately. If False, attempt graceful shutdown.

        Returns:
            True if the agent was terminated successfully.
        """
        ...


# ---------------------------------------------------------------------------
# Type guard helpers
# ---------------------------------------------------------------------------


def is_pane_backend(backend_type: BackendType) -> bool:
    """Return True if *backend_type* is a terminal-pane backend (tmux or iterm2)."""
    return backend_type in ("tmux", "iterm2")
