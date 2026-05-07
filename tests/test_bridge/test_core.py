"""Tests for bridge helpers."""

from __future__ import annotations

from pathlib import Path
import asyncio

import pytest

from openharness.bridge import WorkSecret, build_sdk_url, decode_work_secret, encode_work_secret, spawn_session


def test_work_secret_roundtrip():
    secret = WorkSecret(version=1, session_ingress_token="tok", api_base_url="https://api.example.com")
    encoded = encode_work_secret(secret)
    decoded = decode_work_secret(encoded)
    assert decoded == secret


def test_build_sdk_url():
    assert build_sdk_url("https://api.example.com", "abc").startswith("wss://")
    assert build_sdk_url("http://localhost:3000", "abc").startswith("ws://")


@pytest.mark.asyncio
async def test_spawn_session_and_kill(tmp_path: Path):
    handle = await spawn_session(session_id="s1", command="sleep 30", cwd=tmp_path)
    assert handle.process.returncode is None
    await handle.kill()
    assert handle.process.returncode is not None


@pytest.mark.asyncio
async def test_spawn_session_merges_stderr_into_stdout(monkeypatch, tmp_path: Path):
    seen_kwargs = {}

    class FakeProcess:
        returncode = 0

        def terminate(self):
            pass

        def kill(self):
            pass

        async def wait(self):
            return 0

    async def fake_create_shell_subprocess(*args, **kwargs):
        seen_kwargs.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        "openharness.bridge.session_runner.create_shell_subprocess",
        fake_create_shell_subprocess,
    )

    await spawn_session(session_id="s1", command="printf err >&2", cwd=tmp_path)

    assert seen_kwargs["stdout"] is asyncio.subprocess.PIPE
    assert seen_kwargs["stderr"] is asyncio.subprocess.STDOUT
