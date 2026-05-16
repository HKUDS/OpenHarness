"""Tests for project-scoped runtime memory backend selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.config.settings import set_project_memory_provider
from openharness.ui.runtime import build_runtime, close_runtime


class StaticApiClient:
    async def stream_message(self, request):
        del request
        if False:  # pragma: no cover
            yield None


@pytest.mark.asyncio
async def test_build_runtime_configures_project_memory_provider(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    set_project_memory_provider(repo, "demo")

    calls: list[tuple[Path, str, str]] = []

    def fake_configure_memory_provider(cwd, provider_name, *, settings=None):
        resolved = Path(cwd).resolve()
        configured = settings.memory.provider if settings is not None else ""
        calls.append((resolved, provider_name, configured))
        return object()

    monkeypatch.setattr("openharness.ui.runtime.configure_memory_provider", fake_configure_memory_provider)

    bundle = await build_runtime(cwd=repo, api_client=StaticApiClient())
    try:
        assert calls == [(repo.resolve(), "demo", "demo")]
        assert bundle.current_settings().memory.provider == "demo"
    finally:
        await close_runtime(bundle)