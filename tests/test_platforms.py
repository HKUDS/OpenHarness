"""Tests for platform and capability detection."""

from __future__ import annotations

from openharness.platforms import detect_platform, get_platform_capabilities


def test_detect_platform_recognizes_wsl():
    detected = detect_platform(
        system_name="Linux",
        release="5.15.167.4-microsoft-standard-WSL2",
        env={},
    )
    assert detected == "wsl"


def test_detect_platform_recognizes_windows():
    assert detect_platform(system_name="Windows", release="10", env={}) == "windows"


def test_windows_capabilities_disable_swarm_mailbox_and_sandbox():
    capabilities = get_platform_capabilities("windows")
    assert capabilities.supports_native_windows_shell is True
    assert capabilities.supports_swarm_mailbox is False
    assert capabilities.supports_sandbox_runtime is False
