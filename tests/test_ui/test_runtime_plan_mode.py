from __future__ import annotations

from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.ui.runtime import build_runtime, close_runtime, handle_line


class _StaticApiClient:
    async def stream_message(self, request):
        del request
        if False:
            yield None


class _ReplyingApiClient:
    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(
                role="assistant",
                content=[TextBlock(text="continued")],
            ),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


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


@pytest.mark.asyncio
async def test_resume_preserves_session_id_for_next_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENHARNESS_LOGS_DIR", str(tmp_path / "logs"))

    bundle = await build_runtime(cwd=str(tmp_path), api_client=_ReplyingApiClient())
    original_session_id = bundle.session_id
    resumed_session_id = "resume-me"
    bundle.session_backend.save_snapshot(
        cwd=bundle.cwd,
        model=bundle.engine.model,
        system_prompt=bundle.engine.system_prompt,
        messages=[ConversationMessage(role="user", content=[TextBlock(text="before")])],
        usage=UsageSnapshot(),
        session_id=resumed_session_id,
        tool_metadata={},
    )

    async def print_system(text: str) -> None:
        del text

    async def render_event(event) -> None:
        del event

    async def clear_output() -> None:
        pass

    try:
        await handle_line(
            bundle,
            f"/resume {resumed_session_id}",
            print_system=print_system,
            render_event=render_event,
            clear_output=clear_output,
        )

        assert bundle.session_id == resumed_session_id
        assert bundle.engine.tool_metadata["session_id"] == resumed_session_id

        await handle_line(
            bundle,
            "continue this session",
            print_system=print_system,
            render_event=render_event,
            clear_output=clear_output,
        )

        resumed = bundle.session_backend.load_by_id(bundle.cwd, resumed_session_id)
        assert resumed is not None
        assert resumed["session_id"] == resumed_session_id
        message_texts = {
            (message["role"], block["text"])
            for message in resumed["messages"]
            for block in message["content"]
            if block.get("type") == "text"
        }
        assert ("user", "continue this session") in message_texts
        assert ("assistant", "continued") in message_texts
        assert bundle.session_backend.load_by_id(bundle.cwd, original_session_id) is None
    finally:
        await close_runtime(bundle)
