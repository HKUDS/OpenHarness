"""Session-aware runtime pool for ohmo gateway."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import mimetypes
from pathlib import Path
import json
import os
import string

from openharness.channels.bus.events import InboundMessage
from openharness.commands import CommandContext
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock
from openharness.engine.query import MaxTurnsExceeded
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.prompts import build_runtime_system_prompt
from openharness.ui.runtime import RuntimeBundle, _last_user_text, build_runtime, close_runtime, start_runtime

from ohmo.prompts import build_ohmo_system_prompt
from ohmo.session_storage import OhmoSessionBackend
from ohmo.workspace import get_plugins_dir, get_skills_dir, initialize_workspace

logger = logging.getLogger(__name__)

_CHANNEL_THINKING_PHRASES = (
    "🤔 想一想…",
    "🧠 琢磨中…",
    "✨ 整理一下思路…",
    "🔎 看看这个…",
    "🪄 捋一捋线索…",
)

_CHANNEL_THINKING_PHRASES_EN = (
    "🤔 Thinking…",
    "🧠 Working through it…",
    "✨ Pulling the pieces together…",
    "🔎 Looking into it…",
    "🪄 Following the thread…",
)

_TEXT_PREVIEW_BYTES = 4096
_TEXT_PREVIEW_CHARS = 900
_BINARY_HEAD_BYTES = 32


@dataclass(frozen=True)
class GatewayStreamUpdate:
    """One outbound update produced while processing a channel message."""

    kind: str
    text: str
    metadata: dict[str, object]


class OhmoSessionRuntimePool:
    """Maintain one runtime bundle per chat/thread session."""

    def __init__(
        self,
        *,
        cwd: str | Path,
        workspace: str | Path | None = None,
        provider_profile: str,
        model: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self._cwd = str(Path(cwd).resolve())
        self._workspace = workspace
        self._provider_profile = provider_profile
        self._model = model
        self._max_turns = max_turns
        self._workspace = initialize_workspace(workspace)
        self._session_backend = OhmoSessionBackend(self._workspace)
        self._bundles: dict[str, RuntimeBundle] = {}

    @property
    def active_sessions(self) -> int:
        return len(self._bundles)

    async def get_bundle(self, session_key: str, latest_user_prompt: str | None = None) -> RuntimeBundle:
        """Return an existing bundle or create a new one."""
        bundle = self._bundles.get(session_key)
        if bundle is not None:
            logger.info(
                "ohmo runtime reusing session session_key=%s session_id=%s prompt=%r",
                session_key,
                bundle.session_id,
                _content_snippet(latest_user_prompt or ""),
            )
            bundle.engine.set_system_prompt(self._runtime_system_prompt(bundle, latest_user_prompt))
            return bundle

        snapshot = self._session_backend.load_latest_for_session_key(session_key)
        logger.info(
            "ohmo runtime creating session session_key=%s restored=%s prompt=%r",
            session_key,
            bool(snapshot),
            _content_snippet(latest_user_prompt or ""),
        )
        bundle = await build_runtime(
            model=self._model,
            max_turns=self._max_turns,
            system_prompt=build_ohmo_system_prompt(self._cwd, workspace=self._workspace, extra_prompt=None),
            active_profile=self._provider_profile,
            session_backend=self._session_backend,
            enforce_max_turns=self._max_turns is not None,
            restore_messages=snapshot.get("messages") if snapshot else None,
            extra_skill_dirs=(str(get_skills_dir(self._workspace)),),
            extra_plugin_roots=(str(get_plugins_dir(self._workspace)),),
        )
        if snapshot and snapshot.get("session_id"):
            bundle.session_id = str(snapshot["session_id"])
        await start_runtime(bundle)
        logger.info(
            "ohmo runtime started session_key=%s session_id=%s restored_messages=%s",
            session_key,
            bundle.session_id,
            len(snapshot.get("messages") or []) if snapshot else 0,
        )
        self._bundles[session_key] = bundle
        return bundle

    async def stream_message(self, message: InboundMessage, session_key: str):
        """Submit an inbound channel message and yield progress + final reply updates."""
        user_message = _build_inbound_user_message(message)
        user_prompt = user_message.text
        bundle = await self.get_bundle(session_key, latest_user_prompt=user_prompt)
        logger.info(
            "ohmo runtime processing start channel=%s chat_id=%s session_key=%s session_id=%s content=%r",
            message.channel,
            message.chat_id,
            session_key,
            bundle.session_id,
            _content_snippet(user_prompt),
        )

        parsed = bundle.commands.lookup(user_prompt)
        if parsed is not None and not message.media:
            command, args = parsed
            result = await command.handler(
                args,
                CommandContext(
                    engine=bundle.engine,
                    hooks_summary=bundle.hook_summary(),
                    mcp_summary=bundle.mcp_summary(),
                    plugin_summary=bundle.plugin_summary(),
                    cwd=bundle.cwd,
                    tool_registry=bundle.tool_registry,
                    app_state=bundle.app_state,
                    session_backend=bundle.session_backend,
                    session_id=bundle.session_id,
                    extra_skill_dirs=bundle.extra_skill_dirs,
                    extra_plugin_roots=bundle.extra_plugin_roots,
                ),
            )
            async for update in self._stream_command_result(
                bundle=bundle,
                message=message,
                session_key=session_key,
                user_prompt=user_prompt,
                result=result,
            ):
                yield update
            return

        async for update in self._stream_engine_message(
            bundle=bundle,
            message=message,
            session_key=session_key,
            user_prompt=user_prompt,
            user_message=user_message,
        ):
            yield update

    async def _stream_command_result(
        self,
        *,
        bundle: RuntimeBundle,
        message: InboundMessage,
        session_key: str,
        user_prompt: str,
        result,
    ):
        if result.refresh_runtime:
            bundle = await self._refresh_bundle(session_key, bundle, user_prompt)

        if result.message:
            yield GatewayStreamUpdate(
                kind="final",
                text=result.message,
                metadata={"_session_key": session_key, "_command": True},
            )

        if result.submit_prompt is not None:
            original_model = bundle.engine.model
            if result.submit_model:
                bundle.engine.set_model(result.submit_model)
            try:
                async for update in self._stream_engine_message(
                    bundle=bundle,
                    message=message,
                    session_key=session_key,
                    user_prompt=result.submit_prompt,
                    user_message=result.submit_prompt,
                ):
                    yield update
            finally:
                if result.submit_model:
                    bundle.engine.set_model(original_model)
            return

        if result.continue_pending:
            settings = bundle.current_settings()
            if bundle.enforce_max_turns:
                bundle.engine.set_max_turns(settings.max_turns)
            bundle.engine.set_system_prompt(
                self._runtime_system_prompt(bundle, _last_user_text(bundle.engine.messages))
            )
            turns = result.continue_turns if result.continue_turns is not None else bundle.engine.max_turns
            reply_parts: list[str] = []
            try:
                async for event in bundle.engine.continue_pending(max_turns=turns):
                    async for update in self._convert_stream_event(
                        event=event,
                        bundle=bundle,
                        message=message,
                        session_key=session_key,
                        content=user_prompt,
                        reply_parts=reply_parts,
                    ):
                        yield update
            except MaxTurnsExceeded as exc:
                yield GatewayStreamUpdate(
                    kind="error",
                    text=f"Stopped after {exc.max_turns} turns (max_turns).",
                    metadata={"_session_key": session_key},
                )
            await self._save_snapshot(bundle, session_key, user_prompt)
            reply = "".join(reply_parts).strip()
            if reply:
                yield GatewayStreamUpdate(
                    kind="final",
                    text=reply,
                    metadata={"_session_key": session_key},
                )
            return

        await self._save_snapshot(bundle, session_key, user_prompt)

    async def _stream_engine_message(
        self,
        *,
        bundle: RuntimeBundle,
        message: InboundMessage,
        session_key: str,
        user_prompt: str,
        user_message: ConversationMessage | str,
    ):
        bundle.engine.set_system_prompt(self._runtime_system_prompt(bundle, user_prompt))
        reply_parts: list[str] = []
        yield GatewayStreamUpdate(
            kind="progress",
            text=_format_channel_progress(
                channel=message.channel,
                kind="thinking",
                text="Thinking...",
                session_key=session_key,
                content=user_prompt,
            ),
            metadata={"_progress": True, "_session_key": session_key},
        )
        try:
            async for event in bundle.engine.submit_message(user_message):
                async for update in self._convert_stream_event(
                    event=event,
                    bundle=bundle,
                    message=message,
                    session_key=session_key,
                    content=user_prompt,
                    reply_parts=reply_parts,
                ):
                    yield update
        except MaxTurnsExceeded as exc:
            yield GatewayStreamUpdate(
                kind="error",
                text=f"Stopped after {exc.max_turns} turns (max_turns).",
                metadata={"_session_key": session_key},
            )
            await self._save_snapshot(bundle, session_key, user_prompt)
            return
        await self._save_snapshot(bundle, session_key, user_prompt)
        reply = "".join(reply_parts).strip()
        if reply:
            logger.info(
                "ohmo runtime processing complete session_key=%s session_id=%s reply=%r",
                session_key,
                bundle.session_id,
                _content_snippet(reply),
            )
            yield GatewayStreamUpdate(
                kind="final",
                text=reply,
                metadata={"_session_key": session_key},
            )

    async def _convert_stream_event(
        self,
        *,
        event,
        bundle: RuntimeBundle,
        message: InboundMessage,
        session_key: str,
        content: str,
        reply_parts: list[str],
    ):
        if isinstance(event, AssistantTextDelta):
            reply_parts.append(event.text)
            return
        if isinstance(event, StatusEvent):
            logger.info(
                "ohmo runtime status session_key=%s session_id=%s message=%r",
                session_key,
                bundle.session_id,
                _content_snippet(event.message),
            )
            yield GatewayStreamUpdate(
                kind="progress",
                text=_format_channel_progress(
                    channel=message.channel,
                    kind="status",
                    text=event.message,
                    session_key=session_key,
                    content=content,
                ),
                metadata={"_progress": True, "_session_key": session_key},
            )
            return
        if isinstance(event, ToolExecutionStarted):
            summary = _summarize_tool_input(event.tool_name, event.tool_input)
            logger.info(
                "ohmo runtime tool start session_key=%s session_id=%s tool=%s summary=%r",
                session_key,
                bundle.session_id,
                event.tool_name,
                summary,
            )
            hint = f"Using {event.tool_name}"
            if summary:
                hint = f"{hint}: {summary}"
            yield GatewayStreamUpdate(
                kind="tool_hint",
                text=_format_channel_progress(
                    channel=message.channel,
                    kind="tool_hint",
                    text=hint,
                    session_key=session_key,
                    content=content,
                ),
                metadata={
                    "_progress": True,
                    "_tool_hint": True,
                    "_session_key": session_key,
                },
            )
            return
        if isinstance(event, ToolExecutionCompleted):
            logger.info(
                "ohmo runtime tool complete session_key=%s session_id=%s tool=%s",
                session_key,
                bundle.session_id,
                event.tool_name,
            )
            return
        if isinstance(event, ErrorEvent):
            logger.error(
                "ohmo runtime error session_key=%s session_id=%s message=%r",
                session_key,
                bundle.session_id,
                _content_snippet(event.message),
            )
            yield GatewayStreamUpdate(
                kind="error",
                text=event.message,
                metadata={"_session_key": session_key},
            )
            return
        if isinstance(event, AssistantTurnComplete) and not reply_parts:
            reply_parts.append(event.message.text.strip())

    async def _save_snapshot(self, bundle: RuntimeBundle, session_key: str, user_prompt: str) -> None:
        self._session_backend.save_snapshot(
            cwd=self._cwd,
            model=bundle.current_settings().model,
            system_prompt=self._runtime_system_prompt(bundle, user_prompt),
            messages=bundle.engine.messages,
            usage=bundle.engine.total_usage,
            session_id=bundle.session_id,
            session_key=session_key,
        )
        logger.info(
            "ohmo runtime saved snapshot session_key=%s session_id=%s message_count=%s",
            session_key,
            bundle.session_id,
            len(bundle.engine.messages),
        )

    async def _refresh_bundle(
        self,
        session_key: str,
        bundle: RuntimeBundle,
        latest_user_prompt: str | None,
    ) -> RuntimeBundle:
        snapshot = list(bundle.engine.messages)
        prior_session_id = bundle.session_id
        await close_runtime(bundle)
        refreshed = await build_runtime(
            cwd=self._cwd,
            model=self._model,
            max_turns=self._max_turns,
            system_prompt=build_ohmo_system_prompt(self._cwd, workspace=self._workspace, extra_prompt=None),
            active_profile=self._provider_profile,
            session_backend=self._session_backend,
            enforce_max_turns=self._max_turns is not None,
            restore_messages=[message.model_dump(mode="json") for message in snapshot],
            extra_skill_dirs=(str(get_skills_dir(self._workspace)),),
            extra_plugin_roots=(str(get_plugins_dir(self._workspace)),),
        )
        refreshed.session_id = prior_session_id
        await start_runtime(refreshed)
        refreshed.engine.set_system_prompt(self._runtime_system_prompt(refreshed, latest_user_prompt))
        self._bundles[session_key] = refreshed
        logger.info(
            "ohmo runtime refreshed session_key=%s session_id=%s message_count=%s",
            session_key,
            refreshed.session_id,
            len(refreshed.engine.messages),
        )
        return refreshed

    def _runtime_system_prompt(self, bundle: RuntimeBundle, latest_user_prompt: str | None) -> str:
        settings = bundle.current_settings()
        if not hasattr(settings, "system_prompt"):
            return build_ohmo_system_prompt(self._cwd, workspace=self._workspace, extra_prompt=None)
        return build_runtime_system_prompt(
            settings,
            cwd=self._cwd,
            latest_user_prompt=latest_user_prompt,
            extra_skill_dirs=getattr(bundle, "extra_skill_dirs", ()),
            extra_plugin_roots=getattr(bundle, "extra_plugin_roots", ()),
        )


def _content_snippet(text: str, *, limit: int = 160) -> str:
    """Return a compact single-line preview for logs."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _summarize_tool_input(tool_name: str, tool_input: dict[str, object]) -> str:
    if not tool_input:
        return ""
    for key in ("url", "query", "pattern", "path", "file_path", "command"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            return text if len(text) <= 120 else text[:120] + "..."
    try:
        raw = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    except TypeError:
        raw = str(tool_input)
    return raw if len(raw) <= 120 else raw[:120] + "..."


def _format_channel_progress(
    *,
    channel: str,
    kind: str,
    text: str,
    session_key: str,
    content: str,
) -> str:
    if channel not in {
        "feishu",
        "telegram",
        "slack",
        "discord",
        "matrix",
        "whatsapp",
        "email",
        "dingtalk",
        "qq",
        "wechat",
    }:
        return text
    prefers_chinese = _prefers_chinese_progress(content)
    if kind == "thinking":
        seed = f"{session_key}|{content}".encode("utf-8")
        phrases = _CHANNEL_THINKING_PHRASES if prefers_chinese else _CHANNEL_THINKING_PHRASES_EN
        idx = int(hashlib.sha256(seed).hexdigest(), 16) % len(phrases)
        return phrases[idx]
    if kind == "tool_hint":
        if prefers_chinese:
            if text.startswith("Using "):
                return "🛠️ " + text.replace("Using ", "正在使用 ", 1)
            return f"🛠️ {text}"
        return text if text.startswith("🛠️ ") else f"🛠️ {text}"
    if kind == "status":
        if text.startswith(("🤔", "🧠", "✨", "🔎", "🪄", "🛠️", "🫧")):
            return text
        return f"🫧 {text}"
    return text


def _build_inbound_user_message(message: InboundMessage) -> ConversationMessage:
    """Convert an inbound channel message into user content blocks."""
    content: list[TextBlock | ImageBlock] = []
    base = (message.content or "").strip()
    if base:
        content.append(TextBlock(text=base))

    attachment_notes = _build_attachment_notes(message.media)
    if attachment_notes:
        prefix = "\n\n" if base else ""
        content.append(TextBlock(text=prefix + attachment_notes))

    for media_path in message.media:
        if not _is_image_attachment(media_path):
            continue
        try:
            content.append(ImageBlock.from_path(media_path))
        except Exception:
            logger.exception("ohmo runtime failed to encode image attachment path=%s", media_path)

    return ConversationMessage.from_user_content(content)


def _build_attachment_notes(media_paths: list[str]) -> str:
    """Build textual attachment notes for non-image context and persistence."""
    if not media_paths:
        return ""
    lines = [
        "[Channel attachments]",
        "The following attachments were downloaded locally for this message.",
        "Inspect them by path if needed.",
    ]
    for media_path in media_paths:
        lines.append(f"- {_describe_media_path(media_path)}")
        summary = _summarize_attachment(media_path)
        if summary:
            for part in summary.splitlines():
                lines.append(f"  {part}")
    return "\n".join(lines).strip()


def _describe_media_path(media_path: str) -> str:
    """Return a short type + path description for an inbound attachment."""
    suffix = Path(media_path).suffix.lower()
    if _is_image_attachment(media_path):
        kind = "image"
    elif suffix in {".mp3", ".wav", ".m4a", ".opus", ".aac"}:
        kind = "audio"
    elif suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        kind = "video"
    else:
        kind = "file"
    filename = os.path.basename(media_path)
    return f"{kind}: {filename} (path: {media_path})"


def _is_image_attachment(media_path: str) -> bool:
    mime, _ = mimetypes.guess_type(media_path)
    return bool(mime and mime.startswith("image/"))


def _summarize_attachment(media_path: str) -> str:
    """Return a compact summary/header for a downloaded attachment."""
    path = Path(media_path)
    if not path.exists() or not path.is_file():
        return "summary: attachment is unavailable on disk"
    try:
        stat = path.stat()
    except OSError:
        return "summary: attachment metadata is unavailable"

    mime, _ = mimetypes.guess_type(str(path))
    summary_lines = [f"summary: size={stat.st_size} bytes mime={mime or 'unknown'}"]
    try:
        head = path.read_bytes()[:_TEXT_PREVIEW_BYTES]
    except OSError:
        return "\n".join(summary_lines)

    if _is_image_attachment(str(path)):
        return "\n".join(summary_lines)

    text_preview = _decode_text_preview(head)
    if text_preview is not None:
        summary_lines.append(f"text preview: {text_preview}")
        return "\n".join(summary_lines)

    head_hex = head[:_BINARY_HEAD_BYTES].hex(" ")
    if head_hex:
        summary_lines.append(f"binary header: {head_hex}")
    return "\n".join(summary_lines)


def _decode_text_preview(data: bytes) -> str | None:
    """Return a compact text preview when a file looks text-like."""
    if not data:
        return ""
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(1 for char in decoded if char in string.printable or char.isprintable() or char in "\n\r\t")
    if printable / max(len(decoded), 1) < 0.9:
        return None
    normalized = " ".join(decoded.split())
    if not normalized:
        return ""
    if len(normalized) > _TEXT_PREVIEW_CHARS:
        return normalized[: _TEXT_PREVIEW_CHARS - 3] + "..."
    return normalized


def _prefers_chinese_progress(content: str) -> bool:
    cjk_count = 0
    latin_count = 0
    for char in content:
        codepoint = ord(char)
        if (
            0x4E00 <= codepoint <= 0x9FFF
            or 0x3400 <= codepoint <= 0x4DBF
            or 0x20000 <= codepoint <= 0x2A6DF
            or 0x2A700 <= codepoint <= 0x2B73F
            or 0x2B740 <= codepoint <= 0x2B81F
            or 0x2B820 <= codepoint <= 0x2CEAF
            or 0xF900 <= codepoint <= 0xFAFF
        ):
            cjk_count += 1
        elif ("A" <= char <= "Z") or ("a" <= char <= "z"):
            latin_count += 1
    if cjk_count == 0:
        return False
    if latin_count == 0:
        return True
    return cjk_count >= latin_count
