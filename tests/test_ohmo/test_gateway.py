import asyncio
import logging
from types import SimpleNamespace
from datetime import datetime
import json
from pathlib import Path

import pytest

from openharness.api.usage import UsageSnapshot
from openharness.channels.bus.events import InboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock
from openharness.engine.stream_events import AssistantTextDelta, CompactProgressEvent, ToolExecutionStarted

from ohmo.gateway.bridge import OhmoGatewayBridge, _format_gateway_error
from ohmo.gateway.models import GatewayState
from ohmo.gateway.runtime import OhmoSessionRuntimePool, _build_inbound_user_message, _format_channel_progress
from ohmo.gateway.service import OhmoGatewayService, gateway_status, stop_gateway_process
from ohmo.gateway.router import session_key_for_message
from ohmo.session_storage import save_session_snapshot
from ohmo.workspace import get_gateway_restart_notice_path, initialize_workspace


def test_gateway_router_uses_thread_when_present():
    message = InboundMessage(
        channel="slack",
        sender_id="u1",
        chat_id="c1",
        content="hello",
        timestamp=datetime.utcnow(),
        metadata={"thread_ts": "t1"},
    )
    assert session_key_for_message(message) == "slack:c1:t1"


def test_gateway_router_falls_back_to_chat_scope():
    message = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="chat-1",
        content="hello",
        timestamp=datetime.utcnow(),
    )
    assert session_key_for_message(message) == "telegram:chat-1"


def test_gateway_error_formats_claude_refresh_failure():
    exc = ValueError("Claude OAuth refresh failed: HTTP Error 400: Bad Request")
    assert "claude-login" in _format_gateway_error(exc)
    assert "Claude subscription auth refresh failed" in _format_gateway_error(exc)


def test_gateway_error_formats_generic_auth_failure():
    exc = ValueError("API key missing for current profile")
    assert "Authentication failed" in _format_gateway_error(exc)


def test_compact_progress_formats_reactive_channel_hint_in_chinese():
    text = _format_channel_progress(
        channel="feishu",
        kind="compact_progress",
        text="",
        session_key="feishu:c1",
        content="帮我继续处理",
        compact_phase="compact_start",
        compact_trigger="reactive",
        attempt=None,
    )
    assert "重试" in text


def test_gateway_status_prefers_live_config_over_stale_state(tmp_path):
    workspace = tmp_path / ".ohmo-home"
    workspace.mkdir()
    (workspace / "gateway.json").write_text(
        json.dumps({"provider_profile": "codex", "enabled_channels": ["feishu"]}) + "\n",
        encoding="utf-8",
    )
    (workspace / "state.json").write_text(
        GatewayState(
            running=False,
            provider_profile="claude-subscription",
            enabled_channels=["feishu"],
        ).model_dump_json(indent=2)
        + "\n",
        encoding="utf-8",
    )
    state = gateway_status(tmp_path, workspace)
    assert state.running is False
    assert state.provider_profile == "codex"
    assert state.enabled_channels == ["feishu"]


def test_stop_gateway_process_kills_matching_workspace_processes(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    workspace.mkdir()
    (workspace / "gateway.json").write_text('{"provider_profile":"codex"}\n', encoding="utf-8")
    (workspace / "gateway.pid").write_text("123\n", encoding="utf-8")

    killed: list[int] = []

    def fake_run(*args, **kwargs):
        class Result:
            stdout = (
                f"123 python -m ohmo gateway run --workspace {workspace}\n"
                f"456 python -m ohmo gateway run --workspace {workspace}\n"
            )

        return Result()

    monkeypatch.setattr("ohmo.gateway.service.subprocess.run", fake_run)
    monkeypatch.setattr("ohmo.gateway.service._pid_is_running", lambda pid: True)
    monkeypatch.setattr("ohmo.gateway.service.os.kill", lambda pid, sig: killed.append(pid))

    assert stop_gateway_process(tmp_path, workspace) is True
    assert killed == [123, 456]


@pytest.mark.asyncio
async def test_runtime_pool_restores_messages_for_session_key(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    save_session_snapshot(
        cwd=tmp_path,
        workspace=workspace,
        model="gpt-5.4",
        system_prompt="system",
        messages=[ConversationMessage.from_user_text("remember me")],
        usage=UsageSnapshot(),
        session_id="sess123",
        session_key="feishu:chat-1",
    )

    captured: dict[str, object] = {}

    async def fake_build_runtime(**kwargs):
        captured["restore_messages"] = kwargs.get("restore_messages")
        return SimpleNamespace(
            engine=SimpleNamespace(set_system_prompt=lambda prompt: None, messages=[]),
            session_id="newsession",
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    bundle = await pool.get_bundle("feishu:chat-1")

    assert captured["restore_messages"] is not None
    assert bundle.session_id == "sess123"


@pytest.mark.asyncio
async def test_runtime_pool_stream_message_emits_progress_and_tool_hint(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield ToolExecutionStarted(tool_name="web_fetch", tool_input={"url": "https://example.com"})
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="check")
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[0].kind == "progress"
    assert updates[0].text.startswith(("🤔", "🧠", "✨", "🔎", "🪄"))
    assert updates[1].kind == "tool_hint"
    assert updates[1].text.startswith("🛠️ ")
    assert "web_fetch" in updates[1].text
    assert updates[-1].kind == "final"
    assert updates[-1].text == "done"


@pytest.mark.asyncio
async def test_runtime_pool_stream_message_formats_auto_compact_status_for_feishu(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield CompactProgressEvent(phase="compact_start", trigger="auto")
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
            commands=SimpleNamespace(lookup=lambda raw: None),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="继续")
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[1].kind == "progress"
    assert updates[1].text == "🧠 聊天有点长啦，我先帮你悄悄压缩一下记忆，马上继续～"
    assert updates[-1].kind == "final"
    assert updates[-1].text == "done"


@pytest.mark.asyncio
async def test_runtime_pool_stream_message_formats_compact_retry_for_feishu(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield CompactProgressEvent(phase="compact_retry", trigger="auto", attempt=2, message="retrying")
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
            commands=SimpleNamespace(lookup=lambda raw: None),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="继续")
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[1].kind == "progress"
    assert "再试一次" in updates[1].text


@pytest.mark.asyncio
async def test_runtime_pool_stream_message_formats_compact_hooks_start_for_feishu(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield CompactProgressEvent(phase="hooks_start", trigger="auto")
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
            commands=SimpleNamespace(lookup=lambda raw: None),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="继续")
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[1].kind == "progress"
    assert "准备" in updates[1].text


@pytest.mark.asyncio
async def test_runtime_pool_stream_message_uses_english_progress_for_english_input(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield ToolExecutionStarted(tool_name="web_fetch", tool_input={"url": "https://example.com"})
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="can you check this")
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[0].kind == "progress"
    assert updates[0].text.startswith(("🤔", "🧠", "✨", "🔎", "🪄"))
    assert "Thinking" in updates[0].text or "Working" in updates[0].text or "Looking" in updates[0].text or "Following" in updates[0].text or "Pulling" in updates[0].text
    assert updates[1].kind == "tool_hint"
    assert updates[1].text.startswith("🛠️ Using web_fetch")


@pytest.mark.asyncio
async def test_runtime_pool_includes_media_paths_in_prompt(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    image_path = tmp_path / "example.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    report_path = tmp_path / "report.txt"
    report_path.write_text("Quarterly summary\nRevenue up 12%\n", encoding="utf-8")
    captured: dict[str, object] = {}

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                captured["content"] = content
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(
        channel="feishu",
        sender_id="u1",
        chat_id="c1",
        content="请看这个图片",
        media=[str(image_path), str(report_path)],
    )
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[-1].text == "done"
    submitted = captured["content"]
    assert isinstance(submitted, ConversationMessage)
    assert any(isinstance(block, ImageBlock) for block in submitted.content)
    text = "".join(block.text for block in submitted.content if isinstance(block, TextBlock))
    assert "[Channel attachments]" in text
    assert f"image: example.png (path: {image_path})" in text
    assert f"file: report.txt (path: {report_path})" in text
    assert "text preview: Quarterly summary Revenue up 12%" in text


def test_runtime_pool_includes_group_speaker_context():
    built = _build_inbound_user_message(
        InboundMessage(
            channel="feishu",
            sender_id="ou_123",
            chat_id="oc_group",
            content="请帮我看一下",
            metadata={"chat_type": "group", "sender_display_name": "Tang Jiabin"},
        )
    )
    text = "".join(block.text for block in built.content if isinstance(block, TextBlock))
    assert "[Channel speaker]" in text
    assert "Tang Jiabin" in text
    assert "Sender id: ou_123" in text
    assert "请帮我看一下" in text


@pytest.mark.asyncio
async def test_gateway_bridge_publishes_progress_updates():
    bus = MessageBus()

    class FakeRuntimePool:
        async def stream_message(self, message, session_key):
            yield SimpleNamespace(kind="progress", text="🤔 想一想…", metadata={"_progress": True, "_session_key": session_key})
            yield SimpleNamespace(kind="tool_hint", text="🛠️ 正在使用 web_fetch: https://example.com", metadata={"_progress": True, "_tool_hint": True, "_session_key": session_key})
            yield SimpleNamespace(kind="final", text="Done", metadata={"_session_key": session_key})

    bridge = OhmoGatewayBridge(bus=bus, runtime_pool=FakeRuntimePool())
    task = asyncio.create_task(bridge.run())
    try:
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="hi")
        )
        first = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        second = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        third = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
    finally:
        bridge.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert first.content.startswith(("🤔", "🧠", "✨", "🔎", "🪄"))
    assert first.metadata["_progress"] is True
    assert second.metadata["_tool_hint"] is True
    assert second.content.startswith("🛠️ ")
    assert "web_fetch" in second.content
    assert third.content == "Done"


@pytest.mark.asyncio
async def test_gateway_bridge_logs_inbound_and_final(caplog):
    bus = MessageBus()

    class FakeRuntimePool:
        async def stream_message(self, message, session_key):
            yield SimpleNamespace(kind="progress", text="🤔 想一想…", metadata={"_progress": True, "_session_key": session_key})
            yield SimpleNamespace(kind="final", text="Done", metadata={"_session_key": session_key})

    bridge = OhmoGatewayBridge(bus=bus, runtime_pool=FakeRuntimePool())
    task = asyncio.create_task(bridge.run())
    caplog.set_level(logging.INFO)
    try:
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="please translate this")
        )
        await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
    finally:
        bridge.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert "ohmo inbound received" in caplog.text
    assert "ohmo outbound final" in caplog.text
    assert "please translate this" in caplog.text


@pytest.mark.asyncio
async def test_gateway_bridge_stop_command_cancels_current_session():
    bus = MessageBus()
    cancelled = asyncio.Event()
    release = asyncio.Event()

    class FakeRuntimePool:
        async def stream_message(self, message, session_key):
            try:
                yield SimpleNamespace(kind="progress", text="🤔 想一想…", metadata={"_progress": True, "_session_key": session_key})
                await release.wait()
                yield SimpleNamespace(kind="final", text="Done", metadata={"_session_key": session_key})
            except asyncio.CancelledError:
                cancelled.set()
                raise

    bridge = OhmoGatewayBridge(bus=bus, runtime_pool=FakeRuntimePool())
    task = asyncio.create_task(bridge.run())
    try:
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="long task")
        )
        first = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        assert first.metadata["_progress"] is True
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="/stop")
        )
        stopped = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    finally:
        bridge.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert stopped.content == "⏹️ 已停止当前正在运行的任务。"


@pytest.mark.asyncio
async def test_gateway_bridge_restart_command_requests_gateway_restart():
    bus = MessageBus()
    restarted = asyncio.Event()
    restart_payloads: list[tuple[str, str, str]] = []

    class FakeRuntimePool:
        async def stream_message(self, message, session_key):
            if False:
                yield

    async def fake_restart(message, session_key: str) -> None:
        restart_payloads.append((message.channel, message.chat_id, session_key))
        restarted.set()

    bridge = OhmoGatewayBridge(bus=bus, runtime_pool=FakeRuntimePool(), restart_gateway=fake_restart)
    task = asyncio.create_task(bridge.run())
    try:
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="/restart")
        )
        restarting = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        await asyncio.wait_for(restarted.wait(), timeout=1.0)
    finally:
        bridge.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert restarting.content == (
        "🔄 正在重启 gateway，马上回来。\n"
        "Restarting the gateway now. I'll be back in a moment."
    )
    assert restart_payloads == [("feishu", "c1", "feishu:c1")]


@pytest.mark.asyncio
async def test_gateway_service_request_restart_waits_before_stop(monkeypatch):
    service = object.__new__(OhmoGatewayService)
    service._restart_requested = False
    service._stop_event = asyncio.Event()
    service._workspace = "/tmp/ohmo"

    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("ohmo.gateway.service.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "ohmo.gateway.service.get_gateway_restart_notice_path",
        lambda workspace: Path("/tmp/restart-notice.json"),
    )
    writes: list[str] = []
    monkeypatch.setattr(
        "pathlib.Path.write_text",
        lambda self, content, encoding=None: writes.append(content) or len(content),
    )

    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="/restart")

    await OhmoGatewayService.request_restart(service, message, "feishu:c1")

    assert service._restart_requested is True
    assert service._stop_event.is_set() is True
    assert slept == [0.75]
    assert writes


@pytest.mark.asyncio
async def test_gateway_service_publishes_pending_restart_notice(tmp_path, monkeypatch):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    notice_path = get_gateway_restart_notice_path(workspace)
    notice_path.write_text(
        json.dumps(
            {
                "channel": "feishu",
                "chat_id": "chat-1",
                "session_key": "feishu:chat-1",
                "content": "✅ gateway 已经重新连上，可以继续了。\nGateway is back online. We can continue.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = object.__new__(OhmoGatewayService)
    service._workspace = workspace
    service._bus = MessageBus()

    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("ohmo.gateway.service.asyncio.sleep", fake_sleep)

    await OhmoGatewayService._publish_pending_restart_notice(service)

    outbound = await asyncio.wait_for(service._bus.consume_outbound(), timeout=1.0)
    assert outbound.content == "✅ gateway 已经重新连上，可以继续了。\nGateway is back online. We can continue."
    assert outbound.chat_id == "chat-1"
    assert not notice_path.exists()


@pytest.mark.asyncio
async def test_gateway_bridge_new_message_interrupts_same_session():
    bus = MessageBus()
    first_cancelled = asyncio.Event()
    second_started = asyncio.Event()

    class FakeRuntimePool:
        async def stream_message(self, message, session_key):
            if message.content == "first":
                try:
                    yield SimpleNamespace(kind="progress", text="🤔 想一想…", metadata={"_progress": True, "_session_key": session_key})
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    first_cancelled.set()
                    raise
            else:
                second_started.set()
                yield SimpleNamespace(kind="final", text="second-done", metadata={"_session_key": session_key})

    bridge = OhmoGatewayBridge(bus=bus, runtime_pool=FakeRuntimePool())
    task = asyncio.create_task(bridge.run())
    try:
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="first")
        )
        await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        await bus.publish_inbound(
            InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="second")
        )
        interrupted = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        final = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        await asyncio.wait_for(first_cancelled.wait(), timeout=1.0)
        await asyncio.wait_for(second_started.wait(), timeout=1.0)
    finally:
        bridge.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert interrupted.content == "⏹️ 已停止上一条正在处理的任务，继续看你的最新消息。"
    assert final.content == "second-done"


@pytest.mark.asyncio
async def test_runtime_pool_logs_session_lifecycle(tmp_path, monkeypatch, caplog):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)

    async def fake_build_runtime(**kwargs):
        class FakeEngine:
            messages = []
            total_usage = UsageSnapshot()

            def set_system_prompt(self, prompt):
                return None

            async def submit_message(self, content):
                yield ToolExecutionStarted(tool_name="web_fetch", tool_input={"url": "https://example.com"})
                yield AssistantTextDelta(text="done")

        return SimpleNamespace(
            engine=FakeEngine(),
            session_id="sess123",
            current_settings=lambda: SimpleNamespace(model="gpt-5.4"),
        )

    async def fake_start_runtime(bundle):
        return None

    monkeypatch.setattr("ohmo.gateway.runtime.build_runtime", fake_build_runtime)
    monkeypatch.setattr("ohmo.gateway.runtime.start_runtime", fake_start_runtime)

    pool = OhmoSessionRuntimePool(cwd=tmp_path, workspace=workspace, provider_profile="codex")
    message = InboundMessage(channel="feishu", sender_id="u1", chat_id="c1", content="check")
    caplog.set_level(logging.INFO)
    updates = [u async for u in pool.stream_message(message, "feishu:c1")]

    assert updates[-1].text == "done"
    assert "ohmo runtime processing start" in caplog.text
    assert "ohmo runtime tool start" in caplog.text
    assert "ohmo runtime saved snapshot" in caplog.text
    assert "ohmo runtime processing complete" in caplog.text
