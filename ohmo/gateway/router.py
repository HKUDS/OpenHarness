"""Session routing for ohmo gateway."""

from __future__ import annotations

from openharness.channels.bus.events import InboundMessage


def session_key_for_message(message: InboundMessage) -> str:
    """Route sessions by chat, isolating shared chats by thread/sender.

    Private chats keep the original ``channel:chat_id`` key so existing long
    ohmo sessions remain resumable. Group/shared chats include sender identity
    to avoid multiple people sharing one agent memory.
    """
    if message.session_key_override:
        return message.session_key_override
    sender_id = str(message.sender_id).strip() or "anonymous"
    chat_type = str(message.metadata.get("chat_type") or "").strip().lower()
    is_shared_chat = chat_type in {"group", "chat", "supergroup", "channel", "room"}
    thread_id = (
        message.metadata.get("thread_id")
        or message.metadata.get("thread_ts")
        or message.metadata.get("message_thread_id")
    )
    if thread_id:
        if is_shared_chat:
            return f"{message.channel}:{message.chat_id}:{thread_id}:{sender_id}"
        return f"{message.channel}:{message.chat_id}:{thread_id}"
    if is_shared_chat:
        return f"{message.channel}:{message.chat_id}:{sender_id}"
    return f"{message.channel}:{message.chat_id}"
