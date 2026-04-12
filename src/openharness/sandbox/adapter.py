"""Adapter around the ``srt`` sandbox-runtime CLI."""

from __future__ import annotations

import json
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openharness.config import Settings, load_settings
from openharness.platforms import get_platform, get_platform_capabilities


class SandboxUnavailableError(RuntimeError):
    """Raised when sandboxing is required but unavailable."""


@dataclass(frozen=True)
class SandboxAvailability:
    """Computed sandbox-runtime availability for the current environment."""

    enabled: bool
    available: bool
    reason: str | None = None
    command: str | None = None

    @property
    def active(self) -> bool:
        """Return whether sandboxing should be applied to child processes."""
        return self.enabled and self.available


def build_sandbox_runtime_config(settings: Settings) -> dict[str, Any]:
    """Convert OpenHarness settings into an ``srt`` settings payload."""
    return {
        "network": {
            "allowedDomains": list(settings.sandbox.network.allowed_domains),
            "deniedDomains": list(settings.sandbox.network.denied_domains),
        },
        "filesystem": {
            "allowRead": list(settings.sandbox.filesystem.allow_read),
            "denyRead": list(settings.sandbox.filesystem.deny_read),
            "allowWrite": list(settings.sandbox.filesystem.allow_write),
            "denyWrite": list(settings.sandbox.filesystem.deny_write),
        },
    }


def get_sandbox_availability(settings: Settings | None = None) -> SandboxAvailability:
    """Return whether ``srt`` can be used for the current runtime."""
    resolved_settings = settings or load_settings()
    if not resolved_settings.sandbox.enabled:
        return SandboxAvailability(enabled=False, available=False, reason="sandbox is disabled")

    platform_name = get_platform()
    capabilities = get_platform_capabilities(platform_name)
    if not capabilities.supports_sandbox_runtime:
        if platform_name == "windows":
            reason = "sandbox runtime is not supported on native Windows; use WSL for sandboxed execution"
        else:
            reason = f"sandbox runtime is not supported on platform {platform_name}"
        return SandboxAvailability(enabled=True, available=False, reason=reason)

    enabled_platforms = {name.lower() for name in resolved_settings.sandbox.enabled_platforms}
    if enabled_platforms and platform_name not in enabled_platforms:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason=f"sandbox is disabled for platform {platform_name} by configuration",
        )

    srt = shutil.which("srt")
    if not srt:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason=(
                "sandbox runtime CLI not found; install it with "
                "`npm install -g @anthropic-ai/sandbox-runtime`"
            ),
        )

    if platform_name in {"linux", "wsl"} and shutil.which("bwrap") is None:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason="bubblewrap (`bwrap`) is required for sandbox runtime on Linux/WSL",
            command=srt,
        )

    if platform_name == "macos" and shutil.which("sandbox-exec") is None:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason="`sandbox-exec` is required for sandbox runtime on macOS",
            command=srt,
        )

    return SandboxAvailability(enabled=True, available=True, command=srt)


def wrap_command_for_sandbox(
    command: list[str],
    *,
    settings: Settings | None = None,
) -> tuple[list[str], Path | None]:
    """Wrap an argv list with ``srt`` when sandboxing is active."""
    resolved_settings = settings or load_settings()
    if resolved_settings.sandbox.backend == "docker":
        return command, None
    availability = get_sandbox_availability(resolved_settings)
    if not availability.active:
        if resolved_settings.sandbox.enabled and resolved_settings.sandbox.fail_if_unavailable:
            raise SandboxUnavailableError(availability.reason or "sandbox runtime is unavailable")
        return command, None

    settings_path = _write_runtime_settings(build_sandbox_runtime_config(resolved_settings))
    # The ``srt`` argv form does not reliably preserve child exit codes for shell-style
    # commands such as ``bash -lc 'exit 1'``. Build a single escaped command string and
    # pass it through ``-c`` so hook/tool failures still propagate correctly.
    wrapped = [
        availability.command or "srt",
        "--settings",
        str(settings_path),
        "-c",
        shlex.join(command),
    ]
    return wrapped, settings_path


def _write_runtime_settings(payload: dict[str, Any]) -> Path:
    """Persist a temporary settings file for one sandboxed child process."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="openharness-sandbox-",
        suffix=".json",
        delete=False,
    )
    try:
        json.dump(payload, tmp)
        tmp.write("\n")
    finally:
        tmp.close()
    return Path(tmp.name)
