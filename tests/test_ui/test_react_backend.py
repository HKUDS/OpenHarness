"""Tests for the React backend host protocol."""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from openharness.api.client import ApiMessageCompleteEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.stream_events import CompactProgressEvent
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.ui.backend_host import BackendHostConfig, ReactBackendHost, run_backend_host
from openharness.ui.protocol import BackendEvent
from openharness.ui.runtime import build_runtime, close_runtime, start_runtime


class StaticApiClient:
    """Fake streaming client for backend host tests."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=3),
            stop_reason=None,
        )


class FailingApiClient:
    """Fake client that triggers the query-loop ErrorEvent path."""

    def __init__(self, message: str) -> None:
        self._message = message

    async def stream_message(self, request):
        del request
        if False:
            yield None
        raise RuntimeError(self._message)


class FakeBinaryStdout:
    """Capture protocol writes through a binary stdout buffer."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_backend_host_accepts_permission_mode(monkeypatch):
    captured: dict[str, str | None] = {}

    async def _fake_run(self):
        captured["permission_mode"] = self._config.permission_mode
        return 0

    monkeypatch.setattr("openharness.ui.backend_host.ReactBackendHost.run", _fake_run)

    result = await run_backend_host(
        api_client=StaticApiClient("unused"),
        permission_mode="full_auto",
    )

    assert result == 0
    assert captured["permission_mode"] == "full_auto"


@pytest.mark.asyncio
async def test_read_requests_resolves_permission_response_without_queueing(monkeypatch):
    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    fut = asyncio.get_running_loop().create_future()
    host._permission_requests["req-1"] = fut

    payload = b'{"type":"permission_response","request_id":"req-1","allowed":true}\n'

    class _FakeBuffer:
        def __init__(self):
            self._reads = 0

        def readline(self):
            self._reads += 1
            if self._reads == 1:
                return payload
            return b""

    class _FakeStdin:
        buffer = _FakeBuffer()

    monkeypatch.setattr("openharness.ui.backend_host.sys.stdin", _FakeStdin())

    await host._read_requests()

    assert fut.done()
    assert fut.result() is True
    queued = await host._request_queue.get()
    assert queued.type == "shutdown"
    assert host._request_queue.empty()


@pytest.mark.asyncio
async def test_backend_host_processes_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("/version")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(event.type == "transcript_item" and event.item and event.item.role == "user" for event in events)
    assert any(
        event.type == "transcript_item"
        and event.item
        and event.item.role == "system"
        and "OpenHarness" in event.item.text
        for event in events
    )
    assert any(event.type == "state_snapshot" for event in events)


@pytest.mark.asyncio
async def test_backend_host_processes_model_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("hello from react backend")))
    host._bundle = await build_runtime(api_client=StaticApiClient("hello from react backend"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("hi")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(
        event.type == "assistant_complete" and event.message == "hello from react backend"
        for event in events
    )
    assert any(
        event.type == "assistant_complete"
        and event.item
        and event.item.role == "assistant"
        and "hello from react backend" in event.item.text
        for event in events
    )


@pytest.mark.asyncio
async def test_backend_host_emits_compact_progress_event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    async def _fake_handle_line(bundle, line, print_system, render_event, clear_output):
        del bundle, line, print_system, clear_output
        await render_event(
            CompactProgressEvent(
                phase="compact_start",
                trigger="auto",
                message="Compacting conversation memory.",
                checkpoint="compact_start",
                metadata={"token_count": 12345},
            )
        )
        return True

    monkeypatch.setattr("openharness.ui.backend_host.handle_line", _fake_handle_line)
    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("hi")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(
        event.type == "compact_progress"
        and event.compact_phase == "compact_start"
        and event.compact_checkpoint == "compact_start"
        and event.compact_metadata == {"token_count": 12345}
        for event in events
    )


@pytest.mark.asyncio
async def test_backend_host_surfaces_query_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=FailingApiClient("rate limit")))
    host._bundle = await build_runtime(api_client=FailingApiClient("rate limit"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._process_line("hi")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    assert any(event.type == "error" and "rate limit" in event.message for event in events)
    assert any(
        event.type == "transcript_item"
        and event.item
        and event.item.role == "system"
        and "rate limit" in event.item.text
        for event in events
    )


@pytest.mark.asyncio
async def test_backend_host_command_does_not_reset_cli_overrides(tmp_path, monkeypatch):
    """Regression: slash commands should not snap model/provider back to persisted defaults.

    When the session is launched with CLI overrides (e.g. --provider openai -m 5.4),
    issuing a command like /fast triggers a UI state refresh. That refresh must
    preserve the effective session settings, not reload ~/.openharness/settings.json
    verbatim.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(
        api_client=StaticApiClient("unused"),
        model="5.4",
        api_format="openai",
    )
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        # Sanity: the initial session state reflects CLI overrides.
        assert host._bundle.app_state.get().model == "5.4"
        assert host._bundle.app_state.get().provider == "openai-compatible"

        # Run a command that triggers sync_app_state.
        await host._process_line("/fast show")

        # CLI overrides should remain in effect.
        assert host._bundle.app_state.get().model == "5.4"
        assert host._bundle.app_state.get().provider == "openai-compatible"
    finally:
        await close_runtime(host._bundle)


@pytest.mark.asyncio
async def test_build_runtime_leaves_interactive_sessions_unbounded_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    bundle = await build_runtime(
        api_client=StaticApiClient("unused"),
        enforce_max_turns=False,
    )
    try:
        assert bundle.engine.max_turns is None
        assert bundle.enforce_max_turns is False
    finally:
        await close_runtime(bundle)


@pytest.mark.asyncio
async def test_backend_host_emits_utf8_protocol_bytes(monkeypatch):
    host = ReactBackendHost(BackendHostConfig())
    fake_stdout = FakeBinaryStdout()
    monkeypatch.setattr("openharness.ui.backend_host.sys.stdout", fake_stdout)

    await host._emit(BackendEvent(type="assistant_delta", message="你好😊"))

    raw = fake_stdout.buffer.getvalue()
    assert raw.startswith(b"OHJSON:")
    decoded = raw.decode("utf-8").strip()
    payload = json.loads(decoded.removeprefix("OHJSON:"))
    assert payload["type"] == "assistant_delta"
    assert payload["message"] == "你好😊"


@pytest.mark.asyncio
async def test_backend_host_emits_model_select_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"), model="opus", api_format="anthropic")
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        await host._handle_select_command("model")
    finally:
        await close_runtime(host._bundle)

    event = next(item for item in events if item.type == "select_request")
    assert event.modal["command"] == "model"
    assert any(option["value"] == "opus" and option.get("active") for option in event.select_options)
    assert any(option["value"] == "default" for option in event.select_options)


@pytest.mark.asyncio
async def test_backend_host_emits_theme_select_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        await host._handle_select_command("theme")
    finally:
        await close_runtime(host._bundle)

    event = next(item for item in events if item.type == "select_request")
    assert event.modal["command"] == "theme"
    assert any(option["value"] == "default" for option in event.select_options)


@pytest.mark.asyncio
async def test_backend_host_emits_turns_select_request_with_unlimited_option(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"), enforce_max_turns=False)
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        await host._handle_select_command("turns")
    finally:
        await close_runtime(host._bundle)

    event = next(item for item in events if item.type == "select_request")
    assert event.modal["command"] == "turns"
    assert any(option["value"] == "unlimited" and option.get("active") for option in event.select_options)


@pytest.mark.asyncio
async def test_backend_host_emits_provider_select_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        await host._handle_select_command("provider")
    finally:
        await close_runtime(host._bundle)

    event = next(item for item in events if item.type == "select_request")
    assert event.modal["command"] == "provider"
    assert any(option["value"] == "claude-api" and option.get("active") for option in event.select_options)


@pytest.mark.asyncio
async def test_backend_host_apply_select_command_shows_single_segment_transcript(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._apply_select_command("theme", "default")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    user_event = next(item for item in events if item.type == "transcript_item" and item.item and item.item.role == "user")
    assert user_event.item.text == "/theme"


@pytest.mark.asyncio
async def test_backend_host_apply_provider_select_command_shows_single_segment_transcript(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))

    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))
    host._bundle = await build_runtime(api_client=StaticApiClient("unused"))
    events = []

    async def _emit(event):
        events.append(event)

    host._emit = _emit  # type: ignore[method-assign]
    await start_runtime(host._bundle)
    try:
        should_continue = await host._apply_select_command("provider", "claude-api")
    finally:
        await close_runtime(host._bundle)

    assert should_continue is True
    user_event = next(item for item in events if item.type == "transcript_item" and item.item and item.item.role == "user")
    assert user_event.item.text == "/provider"


@pytest.mark.asyncio
async def test_concurrent_ask_permission_are_serialised():
    """Concurrent _ask_permission calls must be serialised so the frontend
    never receives two overlapping modal_request events.

    Without _permission_lock the second call emits a modal_request before the
    first future is resolved, overwriting the frontend's modal state. The first
    tool then silently waits 300 s and gets Permission denied.
    """
    host = ReactBackendHost(BackendHostConfig(api_client=StaticApiClient("unused")))

    emitted_order: list[str] = []

    async def _fake_emit(event: BackendEvent) -> None:
        if event.type == "modal_request" and event.modal:
            emitted_order.append(str(event.modal.get("request_id", "")))

    host._emit = _fake_emit  # type: ignore[method-assign]

    async def _ask_and_approve(tool: str) -> bool:
        # Start the ask; a background task resolves the future once it appears.
        async def _resolver():
            # Busy-wait until this tool's future is registered.
            while True:
                await asyncio.sleep(0)
                for rid, fut in list(host._permission_requests.items()):
                    if not fut.done():
                        fut.set_result(True)
                        return

        asyncio.create_task(_resolver())
        return await host._ask_permission(tool, "reason")

    # Fire two permission requests concurrently.
    result_a, result_b = await asyncio.gather(
        _ask_and_approve("write_file"),
        _ask_and_approve("bash"),
    )

    assert result_a is True
    assert result_b is True
    # With the lock in place the two modal_request events must be emitted
    # sequentially (one completes before the other starts), so exactly two
    # distinct request IDs must have been emitted.
    assert len(emitted_order) == 2
    assert emitted_order[0] != emitted_order[1]
