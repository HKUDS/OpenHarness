"""Process-level registry for the active in-process path policy (sandbox L1).

Mirrors ``sandbox.session``'s Docker registry: a single policy is installed at
session start (``ui.runtime.build_runtime``) and read by the in-process file
tools before they write. When NO policy is installed — e.g. unit tests that call
a tool directly, or non-session callers — enforcement is skipped (fail-open), so
the policy never affects code paths that don't run a real session.

Single-policy-per-process (same constraint as the Docker session registry): fine
because in-process OH runs one session per process; the swarm runs its workers as
separate subprocesses, each with its own registry.
"""

from __future__ import annotations

from openharness.permissions.path_policy import PathPolicy

_active_policy: PathPolicy | None = None


def set_active_path_policy(policy: PathPolicy | None) -> None:
    """Install (or clear, with ``None``) the process-wide active path policy."""
    global _active_policy  # noqa: PLW0603
    _active_policy = policy


def get_active_path_policy() -> PathPolicy | None:
    """Return the active path policy, or ``None`` when none is installed."""
    return _active_policy


def clear_active_path_policy() -> None:
    """Remove the active path policy (session teardown)."""
    global _active_policy  # noqa: PLW0603
    _active_policy = None
