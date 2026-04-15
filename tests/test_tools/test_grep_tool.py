import asyncio
from pathlib import Path

import pytest

from openharness.tools.grep_tool import GrepTool, GrepToolInput


class _FakeStdout:
    async def readline(self):
        await asyncio.sleep(60)
        return b""


class _FakeProcess:
    def __init__(self):
        self.stdout = _FakeStdout()
        self.stderr = None
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
async def test_grep_tool_returns_timeout_error(monkeypatch, tmp_path: Path):
    tool = GrepTool()
    monkeypatch.setattr("openharness.tools.grep_tool.shutil.which", lambda _: "/usr/bin/rg")
    fake_process = _FakeProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(
        "openharness.tools.grep_tool.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await tool.execute(
        GrepToolInput(pattern="foo", timeout_seconds=1),
        type("Ctx", (), {"cwd": tmp_path})(),
    )

    assert result.is_error is True
    assert "grep timed out after 1 seconds" in result.output
    assert fake_process.terminated or fake_process.killed
