"""Tests for Docker image management."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from openharness.sandbox.docker_image import (
    _image_exists,
    ensure_image_available,
    get_dockerfile_content,
)


def test_get_dockerfile_content_returns_valid_dockerfile():
    content = get_dockerfile_content()
    assert "FROM python:3.11-slim" in content
    assert "ripgrep" in content
    assert "bash" in content
    assert "ohuser" in content


async def test_image_exists_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_image.shutil.which",
        lambda name: "/usr/bin/docker",
    )

    async def fake_exec(*args, **kwargs):
        mock = MagicMock()
        mock.communicate = AsyncMock(return_value=(b"", b""))
        mock.returncode = 0
        return mock

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await _image_exists("openharness-sandbox:latest")
    assert result is True


async def test_image_exists_returns_false_on_failure(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_image.shutil.which",
        lambda name: "/usr/bin/docker",
    )

    async def fake_exec(*args, **kwargs):
        mock = MagicMock()
        mock.communicate = AsyncMock(return_value=(b"", b"Error"))
        mock.returncode = 1
        return mock

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await _image_exists("nonexistent:latest")
    assert result is False


async def test_ensure_image_skips_build_when_exists(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_image.shutil.which",
        lambda name: "/usr/bin/docker",
    )

    async def fake_exec(*args, **kwargs):
        mock = MagicMock()
        mock.communicate = AsyncMock(return_value=(b"", b""))
        mock.returncode = 0
        return mock

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await ensure_image_available("openharness-sandbox:latest", auto_build=True)
    assert result is True


async def test_ensure_image_returns_false_without_auto_build(monkeypatch):
    monkeypatch.setattr(
        "openharness.sandbox.docker_image.shutil.which",
        lambda name: "/usr/bin/docker",
    )

    async def fake_exec(*args, **kwargs):
        mock = MagicMock()
        mock.communicate = AsyncMock(return_value=(b"", b""))
        mock.returncode = 1  # image not found
        return mock

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await ensure_image_available("nonexistent:latest", auto_build=False)
    assert result is False
