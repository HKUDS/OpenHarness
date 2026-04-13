import asyncio
from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.bash_tool import BashTool, BashToolInput


class _FakeStdout:
    def __init__(self, chunks: list[bytes], *, sleep_forever: bool = False):
        self._chunks = list(chunks)
        self._sleep_forever = sleep_forever
        self._process = None

    def attach(self, process) -> None:
        self._process = process

    async def read(self, _size: int = -1):
        if self._chunks:
            if _size == -1:
                chunks = self._chunks[:]
                self._chunks.clear()
                return b"".join(chunks)
            return self._chunks.pop(0)
        if self._process is not None and self._process.returncode is not None:
            return b""
        if self._sleep_forever:
            await asyncio.sleep(0.05)
            if self._process is not None and self._process.returncode is not None:
                return b""
        return b""


class _FakeProcess:
    def __init__(self, *, stdout=None, returncode=None):
        self.stdout = stdout
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        if hasattr(self.stdout, "attach"):
            self.stdout.attach(self)

    async def wait(self):
        if self.returncode is None:
            await asyncio.sleep(60)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.mark.asyncio
async def test_bash_tool_timeout_returns_partial_output_and_interactive_hint(monkeypatch, tmp_path: Path):
    process = _FakeProcess(
        stdout=_FakeStdout(
            [
                b"Creating a new Next.js app in /tmp/coolblog.\n",
                b"Would you like to use Turbopack? \n",
            ],
            sleep_forever=True,
        )
    )

    async def fake_create_shell_subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr("openharness.tools.bash_tool.create_shell_subprocess", fake_create_shell_subprocess)

    result = await BashTool().execute(
        BashToolInput(
            command='npx create-next-app@latest coolblog --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"',
            timeout_seconds=1,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "Command timed out after 1 seconds." in result.output
    assert "Partial output:" in result.output
    assert "Creating a new Next.js app" in result.output
    assert "Would you like to use Turbopack?" in result.output
    assert "This command appears to require interactive input." in result.output
    assert result.metadata["timed_out"] is True
    assert process.killed is True


@pytest.mark.asyncio
async def test_bash_tool_collects_combined_output(monkeypatch, tmp_path: Path):
    process = _FakeProcess(
        stdout=_FakeStdout([b"line one\n", b"line two\n", b""]),
        returncode=0,
    )

    async def fake_create_shell_subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr("openharness.tools.bash_tool.create_shell_subprocess", fake_create_shell_subprocess)

    result = await BashTool().execute(
        BashToolInput(command="printf 'line one\\nline two\\n'"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert result.output == "line one\nline two"
    assert result.metadata["returncode"] == 0
