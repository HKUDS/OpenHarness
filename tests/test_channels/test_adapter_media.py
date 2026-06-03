from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openharness.channels.adapter import ChannelBridge
from openharness.channels.bus.events import InboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.engine.stream_events import AssistantTextDelta, ToolExecutionCompleted


class _FakeEngine:
    def __init__(self, events):
        self._events = events

    async def submit_message(self, content):
        del content
        for event in self._events:
            yield event


class ChannelBridgeMediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_generation_paths_are_forwarded_as_outbound_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "infographic.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            bus = MessageBus()
            bridge = ChannelBridge(
                engine=_FakeEngine(
                    [
                        ToolExecutionCompleted(
                            tool_name="image_generation",
                            output=f"Wrote {image_path}",
                            metadata={"paths": [str(image_path)]},
                        ),
                        AssistantTextDelta("done"),
                    ]
                ),
                bus=bus,
            )

            await bridge._handle(
                InboundMessage(
                    channel="feishu",
                    sender_id="ou_x",
                    chat_id="oc_x",
                    content="/knowledge-kit:ig test",
                    timestamp=datetime.now(),
                )
            )

            outbound = await bus.consume_outbound()
            self.assertEqual(outbound.content, "done")
            self.assertEqual(outbound.media, [str(image_path.resolve())])

    async def test_non_image_generation_paths_are_not_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "notes.txt"
            file_path.write_text("not media", encoding="utf-8")
            bus = MessageBus()
            bridge = ChannelBridge(
                engine=_FakeEngine(
                    [
                        ToolExecutionCompleted(
                            tool_name="grep",
                            output="match",
                            metadata={"paths": [str(file_path)]},
                        ),
                        AssistantTextDelta("done"),
                    ]
                ),
                bus=bus,
            )

            await bridge._handle(
                InboundMessage(
                    channel="feishu",
                    sender_id="ou_x",
                    chat_id="oc_x",
                    content="search",
                    timestamp=datetime.now(),
                )
            )

            outbound = await bus.consume_outbound()
            self.assertEqual(outbound.media, [])


if __name__ == "__main__":
    unittest.main()
