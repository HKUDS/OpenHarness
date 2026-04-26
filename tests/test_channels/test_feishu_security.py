"""Security regressions for Feishu/Lark channel media handling."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.feishu import FeishuChannel
from openharness.config.schema import FeishuConfig


@pytest.mark.asyncio
async def test_feishu_inbound_file_attachment_cannot_escape_media_dir(tmp_path: Path, monkeypatch):
    """Remote Feishu filenames are metadata and must not be trusted as paths."""
    workspace = tmp_path / "ohmo"
    workspace.mkdir()
    protected_file = workspace / "soul.md"
    protected_file.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setenv("OHMO_WORKSPACE", str(workspace))

    channel = FeishuChannel(
        FeishuConfig(allow_from=["user-open-id"], react_emoji="eyes"), MessageBus()
    )

    def fake_download(message_id: str, file_key: str, resource_type: str = "file"):
        assert message_id == "message-id"
        assert file_key == "file-key"
        return b"ATTACKER_OVERWRITE", "../../soul.md"

    async def fake_add_reaction(*args, **kwargs):
        return None

    monkeypatch.setattr(channel, "_download_file_sync", fake_download)
    monkeypatch.setattr(channel, "_add_reaction", fake_add_reaction)
    monkeypatch.setattr(
        channel, "_resolve_sender_display_name_sync", lambda sender_id: "Allowed User"
    )

    forwarded = {}

    async def fake_handle_message(**kwargs):
        forwarded.update(kwargs)

    monkeypatch.setattr(channel, "_handle_message", fake_handle_message)

    event = SimpleNamespace(
        sender=SimpleNamespace(
            sender_type="user",
            sender_id=SimpleNamespace(open_id="user-open-id"),
        ),
        message=SimpleNamespace(
            message_id="message-id",
            chat_id="chat-id",
            chat_type="p2p",
            message_type="file",
            content=json.dumps({"file_key": "file-key"}),
        ),
    )

    await channel._on_message(SimpleNamespace(event=event))

    media_dir = workspace / "attachments" / "feishu"
    saved_paths = [Path(path).resolve() for path in forwarded["media"]]
    assert protected_file.read_text(encoding="utf-8") == "ORIGINAL"
    assert saved_paths == [(media_dir / "soul.md").resolve()]
    assert saved_paths[0].read_bytes() == b"ATTACKER_OVERWRITE"
    assert saved_paths[0].is_relative_to(media_dir.resolve())
    assert "../../" not in forwarded["content"]
