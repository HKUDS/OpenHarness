"""File tools honor the active sandbox path policy (L1 enforcement, sandbox T2)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openharness.config.settings import SandboxFilesystemSettings
from openharness.permissions.active_policy import (
    clear_active_path_policy,
    set_active_path_policy,
)
from openharness.permissions.modes import PermissionMode
from openharness.permissions.path_policy import PathPolicy
from openharness.tools.base import ToolExecutionContext
from openharness.tools.file_edit_tool import FileEditTool, FileEditToolInput
from openharness.tools.file_write_tool import FileWriteTool, FileWriteToolInput


@pytest.fixture(autouse=True)
def _clear_policy():
    clear_active_path_policy()
    yield
    clear_active_path_policy()


def _run(coro):
    return asyncio.run(coro)


def _install(mode: PermissionMode, cwd: Path, **fs) -> None:
    set_active_path_policy(PathPolicy(mode, SandboxFilesystemSettings(**fs), cwd))


def test_write_allowed_within_workspace(tmp_path: Path):
    _install(PermissionMode.DEFAULT, tmp_path)
    ctx = ToolExecutionContext(cwd=tmp_path)
    result = _run(FileWriteTool().execute(FileWriteToolInput(path="out.txt", content="hi"), ctx))
    assert result.is_error is False
    assert (tmp_path / "out.txt").read_text() == "hi"


def test_write_blocked_outside_workspace(tmp_path: Path):
    _install(PermissionMode.DEFAULT, tmp_path)
    ctx = ToolExecutionContext(cwd=tmp_path)
    outside = tmp_path.parent / "escape.txt"
    result = _run(FileWriteTool().execute(FileWriteToolInput(path=str(outside), content="x"), ctx))
    assert result.is_error is True
    assert "blocked by sandbox policy" in result.output
    assert not outside.exists()


def test_write_blocks_sensitive_under_full_auto(tmp_path: Path):
    # Decision D4: even full-access cannot write credential paths.
    _install(PermissionMode.FULL_AUTO, tmp_path)
    ctx = ToolExecutionContext(cwd=tmp_path)
    result = _run(FileWriteTool().execute(FileWriteToolInput(path=".ssh/id_rsa", content="K"), ctx))
    assert result.is_error is True
    assert not (tmp_path / ".ssh" / "id_rsa").exists()


def test_no_policy_means_no_enforcement(tmp_path: Path):
    # Without an installed policy (direct callers / unit tests) writes are
    # unaffected — guards against regressing existing behavior.
    outside = tmp_path.parent / "free.txt"
    ctx = ToolExecutionContext(cwd=tmp_path)
    result = _run(FileWriteTool().execute(FileWriteToolInput(path=str(outside), content="y"), ctx))
    assert result.is_error is False
    assert outside.read_text() == "y"
    outside.unlink()


def test_edit_blocked_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / "ext.txt"
    outside.write_text("hello world")
    try:
        _install(PermissionMode.DEFAULT, tmp_path)
        ctx = ToolExecutionContext(cwd=tmp_path)
        result = _run(
            FileEditTool().execute(
                FileEditToolInput(path=str(outside), old_str="hello", new_str="bye"), ctx
            )
        )
        assert result.is_error is True
        assert "blocked by sandbox policy" in result.output
        assert outside.read_text() == "hello world"  # unchanged
    finally:
        outside.unlink()
