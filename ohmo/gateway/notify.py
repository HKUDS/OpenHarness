"""Proactive notification helpers for ohmo gateway channels."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from ohmo.gateway.config import load_gateway_config

logger = logging.getLogger(__name__)


class OhmoNotificationError(RuntimeError):
    """Raised when a proactive notification cannot be delivered."""


def _chunk_text(text: str, *, max_chars: int = 1800) -> list[str]:
    """Split text into message-sized chunks without losing content."""
    stripped = text.strip()
    if not stripped:
        return []
    chunks: list[str] = []
    remaining = stripped
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _send_feishu_text_sync(*, user_open_id: str, content: str, workspace: str | Path | None = None) -> None:
    """Send a Feishu direct message using ohmo gateway Feishu credentials."""
    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise OhmoNotificationError("Feishu SDK is not installed. Run: pip install lark-oapi") from exc

    config = load_gateway_config(workspace)
    feishu_config: dict[str, Any] = config.channel_configs.get("feishu", {})
    app_id = str(feishu_config.get("app_id") or "").strip()
    app_secret = str(feishu_config.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise OhmoNotificationError("Feishu app_id/app_secret are not configured in ohmo gateway config.")

    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()
    for chunk in _chunk_text(content):
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(user_open_id)
                .msg_type("text")
                .content(json.dumps({"text": chunk}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = client.im.v1.message.create(request)
        if not response.success():
            log_id = response.get_log_id() if hasattr(response, "get_log_id") else ""
            raise OhmoNotificationError(
                f"send Feishu DM failed: code={response.code}, msg={response.msg}, log_id={log_id}"
            )


async def send_feishu_dm(*, user_open_id: str, content: str, workspace: str | Path | None = None) -> None:
    """Send a proactive Feishu direct message to a user open_id."""
    await asyncio.to_thread(_send_feishu_text_sync, user_open_id=user_open_id, content=content, workspace=workspace)
    logger.info("Sent proactive Feishu DM to open_id=%s", user_open_id)
