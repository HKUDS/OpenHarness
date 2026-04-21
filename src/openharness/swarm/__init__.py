"""Swarm backend abstraction for teammate execution."""

from __future__ import annotations

from importlib import import_module

from openharness.swarm.registry import BackendRegistry, get_backend_registry
from openharness.swarm.subprocess_backend import SubprocessBackend
from openharness.swarm.types import (
    BackendType,
    SpawnResult,
    TeammateExecutor,
    TeammateIdentity,
    TeammateMessage,
    TeammateSpawnConfig,
)

_LAZY_EXPORTS = {
    "MailboxMessage": ("openharness.swarm.mailbox", "MailboxMessage"),
    "TeammateMailbox": ("openharness.swarm.mailbox", "TeammateMailbox"),
    "create_idle_notification": ("openharness.swarm.mailbox", "create_idle_notification"),
    "create_shutdown_request": ("openharness.swarm.mailbox", "create_shutdown_request"),
    "create_user_message": ("openharness.swarm.mailbox", "create_user_message"),
    "get_agent_mailbox_dir": ("openharness.swarm.mailbox", "get_agent_mailbox_dir"),
    "get_team_dir": ("openharness.swarm.mailbox", "get_team_dir"),
    "SwarmPermissionRequest": ("openharness.swarm.permission_sync", "SwarmPermissionRequest"),
    "SwarmPermissionResponse": ("openharness.swarm.permission_sync", "SwarmPermissionResponse"),
    "create_permission_request": ("openharness.swarm.permission_sync", "create_permission_request"),
    "handle_permission_request": ("openharness.swarm.permission_sync", "handle_permission_request"),
    "poll_permission_response": ("openharness.swarm.permission_sync", "poll_permission_response"),
    "send_permission_request": ("openharness.swarm.permission_sync", "send_permission_request"),
    "send_permission_response": ("openharness.swarm.permission_sync", "send_permission_response"),
}

__all__ = [
    "BackendRegistry",
    "BackendType",
    "MailboxMessage",
    "SpawnResult",
    "SubprocessBackend",
    "SwarmPermissionRequest",
    "SwarmPermissionResponse",
    "TeammateExecutor",
    "TeammateIdentity",
    "TeammateMailbox",
    "TeammateMessage",
    "TeammateSpawnConfig",
    "create_idle_notification",
    "create_permission_request",
    "create_shutdown_request",
    "create_user_message",
    "get_agent_mailbox_dir",
    "get_backend_registry",
    "get_team_dir",
    "handle_permission_request",
    "poll_permission_response",
    "send_permission_request",
    "send_permission_response",
]


def __getattr__(name: str):
    """Lazily load POSIX-only swarm helpers when they are actually used."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
