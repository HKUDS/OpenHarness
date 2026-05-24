from __future__ import annotations

from pathlib import Path

import pytest

from openharness.ui.runtime import build_runtime, close_runtime, handle_line


class _StaticApiClient:
    async def stream_message(self, request):
        del request
        if False:
            yield None


@pytest.mark.asyncio
async def test_plan_command_refreshes_engine_system_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENHARNESS_LOGS_DIR", str(tmp_path / "logs"))

    bundle = await build_runtime(cwd=str(tmp_path), api_client=_StaticApiClient())
    try:
        assert "Plan mode is enabled" not in bundle.engine.system_prompt

        async def print_system(text: str) -> None:
            del text

        async def render_event(event) -> None:
            del event

        async def clear_output() -> None:
            pass

        should_continue = await handle_line(
            bundle,
            "/plan on",
            print_system=print_system,
            render_event=render_event,
            clear_output=clear_output,
        )

        assert should_continue is True
        assert bundle.app_state.get().permission_mode == "plan"
        assert "Plan mode is enabled" in bundle.engine.system_prompt
        assert "Do not call mutating tools" in bundle.engine.system_prompt
    finally:
        await close_runtime(bundle)
