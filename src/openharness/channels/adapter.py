"""ChannelBridge: connects the MessageBus to a QueryEngine instance.

Usage::

    bridge = ChannelBridge(engine=query_engine, bus=message_bus)
    asyncio.create_task(bridge.run())

The bridge continuously consumes inbound messages from the bus, feeds them
to QueryEngine.submit_message(), and publishes the assembled reply as an
OutboundMessage back to the bus for delivery by ChannelManager.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from openharness.channels.bus.events import InboundMessage, OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.engine.stream_events import AssistantTextDelta, AssistantTurnComplete, ToolExecutionCompleted

if TYPE_CHECKING:
    from openharness.engine.query_engine import QueryEngine

logger = logging.getLogger(__name__)


def _media_paths_from_tool_event(event: ToolExecutionCompleted) -> list[str]:
    """Return local media files produced by tools that create sendable assets."""
    if event.is_error or event.tool_name != "image_generation":
        return []
    metadata = event.metadata or {}
    raw_paths = metadata.get("paths")
    if isinstance(raw_paths, str):
        candidates = [raw_paths]
    elif isinstance(raw_paths, list):
        candidates = [str(path) for path in raw_paths if isinstance(path, str)]
    else:
        return []

    media_paths: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_file():
            logger.debug("Ignoring image_generation media path that is not a file: %s", candidate)
            continue
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            media_paths.append(resolved)
    return media_paths


class ChannelBridge:
    """Bridges inbound channel messages to the QueryEngine and routes replies back.

    One bridge instance should be created per QueryEngine.  It owns the asyncio
    loop integration and handles back-pressure through the MessageBus queues.
    """

    def __init__(self, *, engine: "QueryEngine", bus: MessageBus) -> None:
        self._engine = engine
        self._bus = bus
        self._running = False
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the bridge loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="channel-bridge")
        logger.info("ChannelBridge started")

    async def stop(self) -> None:
        """Stop the bridge loop gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ChannelBridge stopped")

    async def run(self) -> None:
        """Run the bridge inline (blocks until stopped or cancelled)."""
        self._running = True
        try:
            await self._loop()
        finally:
            self._running = False

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Main processing loop: consume → process → publish."""
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self._bus.consume_inbound(),
                    timeout=1.0,
                )
                await self._handle(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ChannelBridge: unhandled error processing message")

    async def _handle(self, msg: InboundMessage) -> None:
        """Process one inbound message and publish the reply."""
        logger.debug("ChannelBridge received from %s/%s", msg.channel, msg.chat_id)

        reply_parts: list[str] = []
        media_paths: list[str] = []
        try:
            async for event in self._engine.submit_message(msg.content):
                if isinstance(event, AssistantTextDelta):
                    reply_parts.append(event.text)
                elif isinstance(event, AssistantTurnComplete):
                    # Turn is done; we'll send the accumulated text below
                    pass
                elif isinstance(event, ToolExecutionCompleted):
                    media_paths.extend(_media_paths_from_tool_event(event))
        except Exception:
            logger.exception(
                "ChannelBridge: engine error for message from %s/%s",
                msg.channel,
                msg.chat_id,
            )
            reply_parts = ["[Error: failed to process your message]"]

        reply_text = "".join(reply_parts).strip()
        if not reply_text and not media_paths:
            logger.debug("ChannelBridge: empty reply and no media, skipping publish")
            return

        outbound = OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=reply_text,
            media=media_paths,
            metadata={"_session_key": msg.session_key},
        )
        await self._bus.publish_outbound(outbound)
        logger.debug(
            "ChannelBridge published reply to %s/%s (%d chars)",
            msg.channel,
            msg.chat_id,
            len(reply_text),
        )
