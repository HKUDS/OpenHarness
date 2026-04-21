"""Platform and capability detection helpers."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Mapping

PlatformName = Literal["macos", "linux", "windows", "wsl", "unknown"]


@dataclass(frozen=True)
class PlatformCapabilities:
    """Capabilities that drive shell, swarm, and sandbox decisions."""

    name: PlatformName
    supports_posix_shell: bool
    supports_native_windows_shell: bool
    supports_tmux: bool
    supports_swarm_mailbox: bool
    supports_sandbox_runtime: bool
    supports_docker_sandbox: bool


def detect_platform(
    *,
    system_name: str | None = None,
    release: str | None = None,
    env: Mapping[str, str] | None = None,
) -> PlatformName:
    """Return the normalized platform name for the current process."""
    env_map = env or os.environ
    system = (system_name or platform.system()).lower()
    kernel_release = (release or platform.release()).lower()

    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        if "microsoft" in kernel_release or env_map.get("WSL_DISTRO_NAME") or env_map.get("WSL_INTEROP"):
            return "wsl"
        return "linux"
    return "unknown"


@lru_cache(maxsize=1)
def get_platform() -> PlatformName:
    """Return the detected platform for this process."""
    return detect_platform()


def get_platform_capabilities(platform_name: PlatformName | None = None) -> PlatformCapabilities:
    """Return the capability matrix for a normalized platform name."""
    name = platform_name or get_platform()
    if name in {"macos", "linux", "wsl"}:
        return PlatformCapabilities(
            name=name,
            supports_posix_shell=True,
            supports_native_windows_shell=False,
            supports_tmux=True,
            supports_swarm_mailbox=True,
            supports_sandbox_runtime=True,
            supports_docker_sandbox=True,
        )
    if name == "windows":
        return PlatformCapabilities(
            name=name,
            supports_posix_shell=False,
            supports_native_windows_shell=True,
            supports_tmux=False,
            supports_swarm_mailbox=False,
            supports_sandbox_runtime=False,
            supports_docker_sandbox=False,
        )
    return PlatformCapabilities(
        name=name,
        supports_posix_shell=False,
        supports_native_windows_shell=False,
        supports_tmux=False,
        supports_swarm_mailbox=False,
        supports_sandbox_runtime=False,
        supports_docker_sandbox=False,
    )

