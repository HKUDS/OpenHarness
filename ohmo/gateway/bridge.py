"""Gateway bridge connecting channel bus traffic to ohmo runtimes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from openharness.channels.bus.events import InboundMessage
from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus

from ohmo.group_registry import load_managed_group_record
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

    def __init__(
        self,
        *,
        bus: MessageBus,
        runtime_pool: OhmoSessionRuntimePool,
        restart_gateway: Callable[[object, str], Awaitable[None] | None] | None = None,
        workspace: str | Path | None = None,
        feishu_group_policy: str = "open",
    ) -> None:
        self._bus = bus
        self._runtime_pool = runtime_pool
        self._restart_gateway = restart_gateway
        self._workspace = workspace
        self._feishu_group_policy = _normalize_feishu_group_policy(feishu_group_policy)
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

            if not self._should_process_message(message):
                logger.info(
                    "ohmo inbound ignored channel=%s chat_id=%s sender_id=%s reason=feishu_group_policy policy=%s content=%r",
                    message.channel,
                    message.chat_id,
                    message.sender_id,
                    self._feishu_group_policy,
                    _content_snippet(message.content),
                )
                continue

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
            if message.content.strip() == "/stop":
                await self._handle_stop(message, session_key)
                continue
            if message.content.strip() == "/restart":
                await self._handle_restart(message, session_key)
                continue
            group_args = _parse_group_command(message.content)
            if group_args is not None:
                prepared = await self._prepare_group_prompt_message(message, session_key, group_args)
                if prepared is None:
                    continue
                message = prepared
                session_key = session_key_for_message(message)
            await self._interrupt_session(
                session_key,
                reason="replaced by a newer user message",
                notify=OutboundMessage(
                    channel=message.channel,
                    chat_id=message.chat_id,
                    content="⏹️ 已停止上一条正在处理的任务，继续看你的最新消息。",
                    metadata={"_progress": True, "_session_key": session_key},
                ),
            )
            task = asyncio.create_task(
                self._process_message(message, session_key),
                name=f"ohmo-session:{session_key}",
            )
            self._session_tasks[session_key] = task
            task.add_done_callback(lambda finished, key=session_key: self._cleanup_task(key, finished))

    def stop(self) -> None:
        self._running = False
        for session_key, task in list(self._session_tasks.items()):
            self._session_cancel_reasons[session_key] = "gateway stopping"
            task.cancel()

    async def _handle_stop(self, message, session_key: str) -> None:
        stopped = await self._interrupt_session(
            session_key,
            reason="stopped by user command",
        )
        content = "⏹️ 已停止当前正在运行的任务。" if stopped else "当前没有正在运行的任务。"
        await self._bus.publish_outbound(
            OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content=content,
                metadata={"_session_key": session_key},
            )
        )

    async def _handle_restart(self, message, session_key: str) -> None:
        await self._interrupt_session(
            session_key,
            reason="restarting gateway by user command",
        )
        await self._bus.publish_outbound(
            OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content="🔄 正在重启 gateway，马上回来。\nRestarting the gateway now. I'll be back in a moment.",
                metadata={"_session_key": session_key},
            )
        )
        if self._restart_gateway is not None:
            result = self._restart_gateway(message, session_key)
            if asyncio.iscoroutine(result):
                await result

    async def _prepare_group_prompt_message(
        self,
        message,
        session_key: str,
        args: str,
    ) -> InboundMessage | None:
        """Convert a private /group command into an agent task."""
        if message.channel != "feishu":
            await self._publish_command_reply(
                message,
                session_key,
                "/group 当前只支持飞书。\n/group is currently only available for Feishu.",
            )
            return None

        chat_type = str(message.metadata.get("chat_type") or "").strip().lower()
        is_private = chat_type in {"p2p", "private", "im", "direct"} or (
            not chat_type and str(message.chat_id) == str(message.sender_id)
        )
        if not is_private:
            await self._publish_command_reply(
                message,
                session_key,
                "请在和 ohmo 的私聊里使用 /group 创建新群。\nUse /group in a private chat with ohmo to create a new group.",
            )
            return None

        metadata = dict(message.metadata)
        metadata["_ohmo_group_command"] = True
        metadata["_ohmo_group_raw_request"] = args
        prompt = _build_group_agent_prompt(args)
        return InboundMessage(
            channel=message.channel,
            sender_id=message.sender_id,
            chat_id=message.chat_id,
            content=prompt,
            timestamp=message.timestamp,
            media=list(message.media),
            metadata=metadata,
            session_key_override=message.session_key_override,
        )

    async def _publish_command_reply(self, message, session_key: str, content: str) -> None:
        await self._bus.publish_outbound(
            OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content=content,
                metadata={"_session_key": session_key},
            )
        )

    async def _interrupt_session(
        self,
        session_key: str,
        *,
        reason: str,
        notify: OutboundMessage | None = None,
    ) -> bool:
        task = self._session_tasks.get(session_key)
        if task is None or task.done():
            return False
        self._session_cancel_reasons[session_key] = reason
        task.cancel()
        if notify is not None:
            await self._bus.publish_outbound(notify)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        return True

    async def _process_message(self, message, session_key: str) -> None:
        # Preserve thread metadata only for shared chats. Feishu p2p replies
        # should stay as normal private messages, not topic replies.
        inbound_meta = {
            k: message.metadata[k] for k in ("thread_id",) if k in message.metadata
        }
        chat_type = str(message.metadata.get("chat_type") or "").lower()
        if chat_type == "group" or inbound_meta.get("thread_id"):
            if "message_id" in message.metadata:
                inbound_meta["message_id"] = message.metadata["message_id"]
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
                await self._bus.publish_outbound(
                    OutboundMessage(
                        channel=message.channel,
                        chat_id=message.chat_id,
                        content=update.text,
                        metadata={**inbound_meta, **(update.metadata or {})},
                    )
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
            return
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
                metadata={**inbound_meta, "_session_key": session_key},
            )

    def stop(self) -> None:
        self._running = False
    def _cleanup_task(self, session_key: str, task: asyncio.Task[None]) -> None:
        current = self._session_tasks.get(session_key)
        if current is task:
            self._session_tasks.pop(session_key, None)
        self._session_cancel_reasons.pop(session_key, None)

    def _should_process_message(self, message: InboundMessage) -> bool:
        if message.channel != "feishu":
            return True
        chat_type = str(message.metadata.get("chat_type") or "").strip().lower()
        if chat_type != "group":
            return True
        policy = self._feishu_group_policy
        if policy == "open":
            return True
        mentioned = _message_mentions_bot(message)
        if policy == "mention":
            return mentioned
        if policy == "managed":
            return self._is_managed_feishu_group(message.chat_id)
        if policy == "managed_or_mention":
            return mentioned or self._is_managed_feishu_group(message.chat_id)
        return mentioned

    def _is_managed_feishu_group(self, chat_id: str) -> bool:
        try:
            return load_managed_group_record(
                workspace=self._workspace,
                channel="feishu",
                chat_id=chat_id,
            ) is not None
        except Exception:
            logger.exception("failed to load ohmo managed group metadata chat_id=%s", chat_id)
            return False


def _parse_group_command(content: str) -> str | None:
    stripped = content.strip()
    parts = stripped.split(maxsplit=1)
    if not parts or parts[0] != "/group":
        return None
    if len(parts) == 1:
        return ""
    return parts[1].strip()


def _build_group_agent_prompt(raw_request: str) -> str:
    request = raw_request.strip() or "(user did not provide details)"
    return (
        "The user invoked `/group` from a Feishu private chat.\n"
        "Your task is to create a dedicated Feishu group for this request.\n\n"
        "Use the `ohmo_create_feishu_group` tool exactly once if you can infer a safe group name. "
        "You, the model, must decide the final `name`, optional `repo`, and optional `cwd` from the user's "
        "natural-language request and available local context. If the cwd is not obvious, inspect the filesystem "
        "before calling the tool. If there is not enough information to choose safely, ask one concise clarification "
        "instead of calling the tool. Do not create the group via bash or direct API calls.\n\n"
        f"User /group request:\n{request}"
    )


def _normalize_feishu_group_policy(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "all": "open",
        "always": "open",
        "always_reply": "open",
        "managed_mention": "managed_or_mention",
        "managed_or_at": "managed_or_mention",
        "at": "mention",
        "mentions": "mention",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"open", "mention", "managed", "managed_or_mention"}:
        return normalized
    return "managed_or_mention"


def _message_mentions_bot(message: InboundMessage) -> bool:
    value = message.metadata.get("mentions_bot")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
