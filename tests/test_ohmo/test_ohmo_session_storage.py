from pathlib import Path

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage

from ohmo.session_storage import OhmoSessionBackend, get_session_dir
from ohmo.workspace import initialize_workspace


def test_ohmo_session_backend_uses_workspace_sessions(tmp_path: Path):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    backend = OhmoSessionBackend(workspace)
    message = ConversationMessage.from_user_text("hello ohmo")
    backend.save_snapshot(
        cwd=tmp_path,
        model="gpt-5.4",
        system_prompt="system",
        messages=[message],
        usage=UsageSnapshot(),
        session_id="abc123",
    )

    session_dir = get_session_dir(workspace)
    assert session_dir == workspace / "sessions"
    assert (session_dir / "latest.json").exists()
    assert backend.load_by_id(tmp_path, "abc123") is not None


def test_ohmo_session_backend_loads_latest_for_session_key(tmp_path: Path):
    workspace = tmp_path / ".ohmo-home"
    initialize_workspace(workspace)
    backend = OhmoSessionBackend(workspace)
    message = ConversationMessage.from_user_text("hello thread")
    backend.save_snapshot(
        cwd=tmp_path,
        model="gpt-5.4",
        system_prompt="system",
        messages=[message],
        usage=UsageSnapshot(),
        session_id="abc123",
        session_key="feishu:chat-1",
        tool_metadata={
            "task_focus_state": {"goal": "Continue the same Feishu task"},
            "recent_verified_work": ["Verified the compact attachment order"],
        },
    )

    loaded = backend.load_latest_for_session_key("feishu:chat-1")
    assert loaded is not None
    assert loaded["session_id"] == "abc123"
    assert loaded["session_key"] == "feishu:chat-1"
    assert loaded["tool_metadata"]["task_focus_state"]["goal"] == "Continue the same Feishu task"
