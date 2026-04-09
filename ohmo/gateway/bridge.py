"""Gateway bridge connecting channel bus traffic to ohmo runtimes."""

from __future__ import annotations

import asyncio
import logging

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus

from ohmo.gateway.router import session_key_for_message
from ohmo.gateway.runtime import OhmoSessionRuntimePool

logger = logging.getLogger(__name__)


def _content_snippet(text: str, *, limit: int = 160) -> str:
    """Return a single-line preview suitable for logs."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _format_gateway_error(exc: Exception) -> str:
    """Return a short, user-facing gateway error message."""
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if "claude oauth refresh failed" in lowered:
        return (
            "[ohmo gateway error] Claude subscription auth refresh failed. "
            "Run `oh auth claude-login` again or switch the gateway profile."
        )
    if "claude oauth refresh token is invalid or expired" in lowered:
        return (
            "[ohmo gateway error] Claude subscription token is expired. "
            "Run `claude auth login`, then `oh auth claude-login`, or switch the gateway profile."
        )
    if "auth source not found" in lowered or "access token" in lowered:
        return (
            "[ohmo gateway error] Authentication is not configured for the current "
            "gateway profile. Run `oh setup` or `ohmo config`."
        )
    if "api key" in lowered or "auth" in lowered or "credential" in lowered:
        return (
            "[ohmo gateway error] Authentication failed for the current gateway "
            "profile. Check `oh auth status` and `ohmo config`."
        )
    return f"[ohmo gateway error] {message}"


class OhmoGatewayBridge:
    """Consume inbound messages and publish assistant replies."""

    def __init__(self, *, bus: MessageBus, runtime_pool: OhmoSessionRuntimePool) -> None:
        self._bus = bus
        self._runtime_pool = runtime_pool
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                message = await asyncio.wait_for(self._bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            session_key = session_key_for_message(message)
            logger.info(
                "ohmo inbound received channel=%s chat_id=%s sender_id=%s session_key=%s content=%r",
                message.channel,
                message.chat_id,
                message.sender_id,
                session_key,
                _content_snippet(message.content),
            )
            try:
                reply = ""
                async for update in self._runtime_pool.stream_message(message, session_key):
                    if update.kind == "final":
                        reply = update.text
                        continue
                    if not update.text:
                        continue
                    logger.info(
                        "ohmo outbound update channel=%s chat_id=%s session_key=%s kind=%s content=%r",
                        message.channel,
                        message.chat_id,
                        session_key,
                        update.kind,
                        _content_snippet(update.text),
                    )
                    await self._bus.publish_outbound(
                        OutboundMessage(
                            channel=message.channel,
                            chat_id=message.chat_id,
                            content=update.text,
                            metadata=update.metadata,
                        )
                    )
            except Exception as exc:  # pragma: no cover - gateway failure path
                logger.exception(
                    "ohmo gateway failed to process inbound message channel=%s chat_id=%s sender_id=%s session_key=%s content=%r",
                    message.channel,
                    message.chat_id,
                    message.sender_id,
                    session_key,
                    _content_snippet(message.content),
                )
                reply = _format_gateway_error(exc)
            if not reply:
                logger.info(
                    "ohmo inbound finished without final reply channel=%s chat_id=%s session_key=%s",
                    message.channel,
                    message.chat_id,
                    session_key,
                )
                continue
            logger.info(
                "ohmo outbound final channel=%s chat_id=%s session_key=%s content=%r",
                message.channel,
                message.chat_id,
                session_key,
                _content_snippet(reply),
            )
            await self._bus.publish_outbound(
                OutboundMessage(
                    channel=message.channel,
                    chat_id=message.chat_id,
                    content=reply,
                    metadata={"_session_key": session_key},
                )
            )

    def stop(self) -> None:
        self._running = False
