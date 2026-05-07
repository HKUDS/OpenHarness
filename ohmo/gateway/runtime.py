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
from openharness.commands import CommandContext, CommandResult
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock
from openharness.commands import CommandContext, CommandResult, lookup_skill_slash_command
from openharness.engine.messages import (
    ConversationMessage,
    ImageBlock,
    TextBlock,
    sanitize_conversation_messages,
)
from openharness.engine.query import MaxTurnsExceeded
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.prompts import build_runtime_system_prompt
from openharness.ui.runtime import RuntimeBundle, build_runtime, start_runtime

from ohmo.gateway.config import load_gateway_config
from ohmo.gateway.group_tool import CreateFeishuGroup, OhmoCreateFeishuGroupTool, PublishGroupWelcome
from ohmo.gateway.provider_commands import handle_gateway_model_command, handle_gateway_provider_command
from ohmo.group_registry import load_managed_group_record, normalize_cwd
from ohmo.memory import create_memory_command_backend
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
_IMAGE_FALLBACK_NOTE = (
    "[Image attachment omitted because the active model does not support image input. "
    "Use the attachment paths and summaries above if needed.]"
)
_NO_GROUP_REQUEST = object()
_GROUP_TOOL_NAME = "ohmo_create_feishu_group"
_GROUP_AGENT_PROMPT_PREFIX = "The user invoked `/group` from a Feishu private chat."
_GROUP_AGENT_PROMPT_REQUEST_MARKER = "User /group request:"
_GROUP_METADATA_KEYS = (
    "task_focus_state",
    "recent_work_log",
    "recent_verified_work",
    "compact_checkpoints",
    "compact_last",
)


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
        create_feishu_group: CreateFeishuGroup | None = None,
        publish_group_welcome: PublishGroupWelcome | None = None,
    ) -> None:
        self._cwd = str(Path(cwd).resolve())
        self._workspace = workspace
        self._provider_profile = provider_profile
        self._model = model
        self._max_turns = max_turns
        self._create_feishu_group = create_feishu_group
        self._publish_group_welcome = publish_group_welcome
        self._workspace = initialize_workspace(workspace)
        self._gateway_config = load_gateway_config(self._workspace)
        self._session_backend = OhmoSessionBackend(self._workspace)
        self._bundles: dict[str, RuntimeBundle] = {}

    @property
    def active_sessions(self) -> int:
        return len(self._bundles)

    def _remote_admin_allowed(self, command) -> bool:
        if not getattr(command, "remote_admin_opt_in", False):
            return False
        if not self._gateway_config.allow_remote_admin_commands:
            return False
        allowed = {
            str(name).strip().lower()
            for name in self._gateway_config.allowed_remote_admin_commands
            if str(name).strip()
        }
        return command.name.lower() in allowed

    def _handle_gateway_scoped_command(self, command_name: str, args: str) -> tuple[str, bool] | None:
        lowered = command_name.lower()
        if lowered == "provider":
            result = handle_gateway_provider_command(args, workspace=self._workspace)
        elif lowered == "model":
            result = handle_gateway_model_command(args, workspace=self._workspace)
        else:
            return None
        if result[1]:
            self._gateway_config = load_gateway_config(self._workspace)
            self._provider_profile = self._gateway_config.provider_profile
        return result

    async def get_bundle(
        self,
        session_key: str,
        latest_user_prompt: str | None = None,
        cwd: str | Path | None = None,
    ) -> RuntimeBundle:
        """Return an existing bundle or create a new one."""
        session_cwd = str(Path(cwd or self._cwd).expanduser().resolve())
        bundle = self._bundles.get(session_key)
        if bundle is not None:
            bundle_cwd = str(Path(getattr(bundle, "cwd", self._cwd)).resolve())
            if bundle_cwd != session_cwd:
                logger.info(
                    "ohmo runtime recreating session for cwd change session_key=%s old_cwd=%s new_cwd=%s",
                    session_key,
                    bundle_cwd,
                    session_cwd,
                )
                await close_runtime(bundle)
                self._bundles.pop(session_key, None)
            else:
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
            cwd=session_cwd,
            model=self._model,
            max_turns=self._max_turns,
            system_prompt=build_ohmo_system_prompt(session_cwd, workspace=self._workspace, extra_prompt=None),
            active_profile=self._provider_profile,
            session_backend=self._session_backend,
            enforce_max_turns=self._max_turns is not None,
            restore_messages=_sanitize_snapshot_messages(snapshot.get("messages") if snapshot else None),
            restore_tool_metadata=_sanitize_group_command_metadata(snapshot.get("tool_metadata") if snapshot else None),
            extra_skill_dirs=(str(get_skills_dir(self._workspace)),),
            extra_plugin_roots=(str(get_plugins_dir(self._workspace)),),
            memory_backend=create_memory_command_backend(self._workspace),
            include_project_memory=False,
        )
        if snapshot and snapshot.get("session_id"):
            bundle.session_id = str(snapshot["session_id"])
        self._register_gateway_tools(bundle)
        await start_runtime(bundle)
        bundle.engine.set_system_prompt(self._runtime_system_prompt(bundle, latest_user_prompt))
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
        command_prompt = (message.content or "").strip()
        session_cwd = self._cwd_for_message(message)
        bundle = await self.get_bundle(session_key, latest_user_prompt=user_prompt, cwd=session_cwd)
        logger.info(
            "ohmo runtime processing start channel=%s chat_id=%s session_key=%s session_id=%s content=%r",
            message.channel,
            message.chat_id,
            session_key,
            bundle.session_id,
            _content_snippet(user_prompt),
        )

        command_context: CommandContext | None = None

        def get_command_context() -> CommandContext:
            nonlocal command_context
            if command_context is None:
                command_context = CommandContext(
                    engine=bundle.engine,
                    hooks_summary=getattr(bundle, "hook_summary", lambda: "")(),
                    mcp_summary=getattr(bundle, "mcp_summary", lambda: "")(),
                    plugin_summary=getattr(bundle, "plugin_summary", lambda: "")(),
                    cwd=getattr(bundle, "cwd", str(self._cwd)),
                    tool_registry=getattr(bundle, "tool_registry", None),
                    app_state=getattr(bundle, "app_state", None),
                    session_backend=getattr(bundle, "session_backend", self._session_backend),
                    session_id=getattr(bundle, "session_id", None),
                    extra_skill_dirs=getattr(bundle, "extra_skill_dirs", ()),
                    extra_plugin_roots=getattr(bundle, "extra_plugin_roots", ()),
                    memory_backend=create_memory_command_backend(self._workspace),
                    include_project_memory=False,
                )
            return command_context

        parsed = bundle.commands.lookup(command_prompt)
        if parsed is None and not message.media:
            parsed = lookup_skill_slash_command(command_prompt, get_command_context())
        if parsed is not None and not message.media:
            command, args = parsed
            command_name = str(getattr(command, "name", "") or "")
            gateway_result = self._handle_gateway_scoped_command(command_name, args)
            if gateway_result is not None:
                message_text, refresh_runtime = gateway_result
                result = CommandResult(message=message_text, refresh_runtime=refresh_runtime)
                async for update in self._stream_command_result(
                    bundle=bundle,
                    message=message,
                    session_key=session_key,
                    user_prompt=user_prompt,
                    result=result,
                ):
                    yield update
                return
            remote_allowed = getattr(command, "remote_invocable", True)
            if not remote_allowed and self._remote_admin_allowed(command):
                remote_allowed = True
                logger.warning(
                    "ohmo gateway remote administrative command accepted channel=%s chat_id=%s sender_id=%s command=%s",
                    message.channel,
                    message.chat_id,
                    message.sender_id,
                    command_name,
                )
            if not remote_allowed:
                result = CommandResult(
                    message=f"/{command_name} is only available in the local OpenHarness UI."
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
            result = await command.handler(
                args,
                get_command_context(),
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
        async for event in bundle.engine.submit_message(user_message):
            if isinstance(event, AssistantTextDelta):
                reply_parts.append(event.text)
                continue
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
                        content=user_prompt,
                    ),
                    metadata={"_progress": True, "_session_key": session_key},
                )
                continue
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
                        content=user_prompt,
                    ),
                    metadata={
                        "_progress": True,
                        "_tool_hint": True,
                        "_session_key": session_key,
                    },
                )
                continue
            if isinstance(event, ToolExecutionCompleted):
                logger.info(
                    "ohmo runtime tool complete session_key=%s session_id=%s tool=%s",
                    session_key,
                    bundle.session_id,
                    event.tool_name,
                )
                continue
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
        reply = "".join(reply_parts).strip()
        previous_group_request = self._set_group_request_context(bundle, message, session_key)
        try:
            async for event in bundle.engine.submit_message(user_message):
                if isinstance(event, ErrorEvent) and _should_retry_without_image_input(
                    event.message,
                    bundle.engine.messages,
                ):
                    logger.warning(
                        "ohmo runtime image input rejected; retrying without image blocks session_key=%s session_id=%s message=%r",
                        session_key,
                        bundle.session_id,
                        _content_snippet(event.message),
                    )
                    _strip_image_blocks_from_engine_history(bundle.engine)
                    yield GatewayStreamUpdate(
                        kind="progress",
                        text=_format_channel_progress(
                            channel=message.channel,
                            kind="image_fallback",
                            text=event.message,
                            session_key=session_key,
                            content=user_prompt,
                        ),
                        metadata={"_progress": True, "_session_key": session_key, "_image_fallback": True},
                    )
                    async for retry_event in bundle.engine.continue_pending(max_turns=bundle.engine.max_turns):
                        async for update in self._convert_stream_event(
                            event=retry_event,
                            bundle=bundle,
                            message=message,
                            session_key=session_key,
                            content=user_prompt,
                            reply_parts=reply_parts,
                        ):
                            yield update
                    break
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
            self._restore_group_request_context(bundle, previous_group_request)
            await self._save_snapshot(bundle, session_key, user_prompt)
            return
        except Exception:
            self._restore_group_request_context(bundle, previous_group_request)
            raise
        self._restore_group_request_context(bundle, previous_group_request)
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
        if isinstance(event, CompactProgressEvent):
            logger.info(
                "ohmo runtime compact progress session_key=%s session_id=%s phase=%s trigger=%s attempt=%s",
                session_key,
                bundle.session_id,
                event.phase,
                event.trigger,
                event.attempt,
            )
            rendered = _format_channel_progress(
                channel=message.channel,
                kind="compact_progress",
                text=event.message or "",
                session_key=session_key,
                content=content,
                compact_phase=event.phase,
                compact_trigger=event.trigger,
                attempt=event.attempt,
            )
            if rendered:
                yield GatewayStreamUpdate(
                    kind="progress",
                    text=rendered,
                    metadata={"_progress": True, "_session_key": session_key, "_compact": True},
                )
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
        tool_metadata = _sanitize_group_command_metadata(getattr(bundle.engine, "tool_metadata", {}) or {})
        if isinstance(getattr(bundle.engine, "tool_metadata", None), dict) and isinstance(tool_metadata, dict):
            bundle.engine.tool_metadata.update(tool_metadata)
        messages = _sanitize_group_command_prompts(list(bundle.engine.messages))
        if messages != list(bundle.engine.messages):
            if hasattr(bundle.engine, "load_messages"):
                bundle.engine.load_messages(messages)
            else:
                bundle.engine.messages = messages
        self._session_backend.save_snapshot(
            cwd=getattr(bundle, "cwd", self._cwd),
            model=bundle.current_settings().model,
            system_prompt=self._runtime_system_prompt(bundle, user_prompt),
            messages=messages,
            usage=bundle.engine.total_usage,
            session_id=bundle.session_id,
            session_key=session_key,
            tool_metadata=tool_metadata,
        )
        logger.info(
            "ohmo runtime saved snapshot session_key=%s session_id=%s message_count=%s reply_chars=%s",
            session_key,
            bundle.session_id,
            len(bundle.engine.messages),
            len(reply),
        )
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

    async def _refresh_bundle(
        self,
        session_key: str,
        bundle: RuntimeBundle,
        latest_user_prompt: str | None,
    ) -> RuntimeBundle:
        snapshot = sanitize_conversation_messages(list(bundle.engine.messages))
        prior_session_id = bundle.session_id
        bundle_cwd = str(Path(getattr(bundle, "cwd", self._cwd)).resolve())
        await close_runtime(bundle)
        refreshed = await build_runtime(
            cwd=bundle_cwd,
            model=self._model,
            max_turns=self._max_turns,
            system_prompt=build_ohmo_system_prompt(bundle_cwd, workspace=self._workspace, extra_prompt=None),
            active_profile=self._provider_profile,
            session_backend=self._session_backend,
            enforce_max_turns=self._max_turns is not None,
            restore_messages=[message.model_dump(mode="json") for message in _sanitize_group_command_prompts(snapshot)],
            restore_tool_metadata=_sanitize_group_command_metadata(getattr(bundle.engine, "tool_metadata", {}) or {}),
            extra_skill_dirs=(str(get_skills_dir(self._workspace)),),
            extra_plugin_roots=(str(get_plugins_dir(self._workspace)),),
            memory_backend=create_memory_command_backend(self._workspace),
            include_project_memory=False,
        )
        refreshed.session_id = prior_session_id
        self._register_gateway_tools(refreshed)
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
        bundle_cwd = str(Path(getattr(bundle, "cwd", self._cwd)).resolve())
        if not hasattr(bundle, "current_settings"):
            return build_ohmo_system_prompt(bundle_cwd, workspace=self._workspace, extra_prompt=None)
        settings = bundle.current_settings()
        if not hasattr(settings, "system_prompt"):
            return build_ohmo_system_prompt(bundle_cwd, workspace=self._workspace, extra_prompt=None)
        return build_runtime_system_prompt(
            settings,
            cwd=bundle_cwd,
            latest_user_prompt=latest_user_prompt,
            extra_skill_dirs=getattr(bundle, "extra_skill_dirs", ()),
            extra_plugin_roots=getattr(bundle, "extra_plugin_roots", ()),
            include_project_memory=False,
        )

    def _cwd_for_message(self, message: InboundMessage) -> str:
        record = load_managed_group_record(
            workspace=self._workspace,
            channel=message.channel,
            chat_id=message.chat_id,
        )
        cwd = record.get("cwd") if record else None
        if not cwd:
            return self._cwd
        normalized = normalize_cwd(str(cwd))
        if not Path(normalized).is_dir():
            logger.warning(
                "ohmo managed group cwd does not exist channel=%s chat_id=%s cwd=%s",
                message.channel,
                message.chat_id,
                normalized,
            )
            return self._cwd
        return normalized

    def _register_gateway_tools(self, bundle: RuntimeBundle) -> None:
        self._unregister_group_tool(bundle)

    def _register_group_tool(self, bundle: RuntimeBundle) -> None:
        if self._create_feishu_group is None or not hasattr(bundle, "tool_registry"):
            return
        if bundle.tool_registry is None or bundle.tool_registry.get(_GROUP_TOOL_NAME) is not None:
            return
        bundle.tool_registry.register(
            OhmoCreateFeishuGroupTool(
                workspace=self._workspace,
                create_group=self._create_feishu_group,
                publish_group_welcome=self._publish_group_welcome,
            )
        )

    @staticmethod
    def _unregister_group_tool(bundle: RuntimeBundle) -> None:
        registry = getattr(bundle, "tool_registry", None)
        tools = getattr(registry, "_tools", None)
        if isinstance(tools, dict):
            tools.pop(_GROUP_TOOL_NAME, None)

    def _set_group_request_context(
        self,
        bundle: RuntimeBundle,
        message: InboundMessage,
        session_key: str,
    ) -> object:
        metadata = getattr(bundle.engine, "tool_metadata", {})
        previous = metadata.get("ohmo_group_request", _NO_GROUP_REQUEST)
        if not message.metadata.get("_ohmo_group_command"):
            metadata.pop("ohmo_group_request", None)
            metadata.pop("_suppress_next_user_goal", None)
            self._unregister_group_tool(bundle)
            return _NO_GROUP_REQUEST
        self._register_group_tool(bundle)
        metadata["_suppress_next_user_goal"] = True
        metadata["ohmo_group_request"] = {
            "channel": message.channel,
            "chat_type": str(message.metadata.get("chat_type") or "").strip().lower(),
            "sender_id": str(message.sender_id),
            "source_chat_id": str(message.chat_id),
            "source_session_key": session_key,
            "sender_display_name": message.metadata.get("sender_display_name"),
            "raw_request": message.metadata.get("_ohmo_group_raw_request") or "",
            "used": False,
        }
        return previous

    @staticmethod
    def _restore_group_request_context(bundle: RuntimeBundle, previous: object) -> None:
        metadata = getattr(bundle.engine, "tool_metadata", {})
        del previous
        metadata.pop("ohmo_group_request", None)
        metadata.pop("_suppress_next_user_goal", None)
        OhmoSessionRuntimePool._unregister_group_tool(bundle)


def _content_snippet(text: str, *, limit: int = 160) -> str:
    """Return a compact single-line preview for logs."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _sanitize_snapshot_messages(raw_messages: object) -> list[dict[str, object]] | None:
    """Validate and sanitize restored messages from persisted ohmo snapshots."""
    if not raw_messages or not isinstance(raw_messages, list):
        return None
    messages: list[ConversationMessage] = []
    for raw in raw_messages:
        try:
            messages.append(ConversationMessage.model_validate(raw))
        except Exception:
            logger.warning("ohmo runtime skipped invalid restored message while sanitizing snapshot")
    return [message.model_dump(mode="json") for message in _sanitize_group_command_prompts(messages)]


def _sanitize_group_command_prompts(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    """Replace internal /group tool-driving prompts with durable user-facing history."""
    return [_sanitize_group_command_prompt(message) for message in messages]


def _sanitize_group_command_prompt(message: ConversationMessage) -> ConversationMessage:
    changed = False
    content: list[TextBlock | ImageBlock] = []
    for block in message.content:
        if isinstance(block, TextBlock) and _GROUP_AGENT_PROMPT_PREFIX in block.text:
            content.append(TextBlock(text=_format_group_command_history_note(block.text)))
            changed = True
        else:
            content.append(block)
    if not changed:
        return message
    return message.model_copy(update={"content": content})


def _format_group_command_history_note(prompt: str) -> str:
    raw_request = prompt
    if _GROUP_AGENT_PROMPT_REQUEST_MARKER in prompt:
        raw_request = prompt.split(_GROUP_AGENT_PROMPT_REQUEST_MARKER, 1)[1].strip()
    raw_request = raw_request.strip() or "(empty request)"
    return f"[Handled /group request]\nThe user asked ohmo to create a Feishu group:\n{raw_request}"


def _sanitize_group_command_metadata(raw_metadata: object) -> object:
    """Remove internal /group tool-driving text from compact carry-over metadata."""
    if not isinstance(raw_metadata, dict):
        return raw_metadata
    sanitized = dict(raw_metadata)
    for key in _GROUP_METADATA_KEYS:
        if key in sanitized:
            sanitized[key] = _sanitize_group_command_metadata_value(sanitized[key])
    return sanitized


def _sanitize_group_command_metadata_value(value: object) -> object:
    if isinstance(value, str):
        if _GROUP_AGENT_PROMPT_PREFIX in value:
            return _format_group_command_history_note(value)
        return value
    if isinstance(value, dict):
        return {key: _sanitize_group_command_metadata_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_group_command_metadata_value(item) for item in value]
    return value


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
    compact_phase: str | None = None,
    compact_trigger: str | None = None,
    attempt: int | None = None,
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
    if kind == "image_fallback":
        if prefers_chinese:
            return "🖼️ 当前模型不支持图片输入，我先改用附件路径和摘要继续。"
        return "🖼️ The active model does not support image input. I’ll retry with attachment paths and summaries."
    if kind == "status":
        normalized = text.strip()
        if normalized == "Auto-compacting conversation memory to keep things fast and focused.":
            if prefers_chinese:
                return "🧠 聊天有点长啦，我先帮你蹦蹦跳跳压缩一下记忆，马上带着重点回来～"
            return "🧠 This chat is getting long — I’m doing a quick memory squeeze and hopping right back with the good bits."
        if text.startswith(("🤔", "🧠", "✨", "🔎", "🪄", "🛠️", "🫧")):
            return text
        return f"🫧 {text}"
    if kind == "compact_progress":
        if compact_phase == "hooks_start":
            if prefers_chinese:
                if compact_trigger == "reactive":
                    return "🫧 上下文有点超长，我先准备压缩一下记忆，然后立刻继续重试～"
                return "🫧 我先把上下文和记忆准备一下，马上开始压缩重点～"
            if compact_trigger == "reactive":
                return "🫧 The context got too large. I’m preparing a quick memory compaction before retrying."
            return "🫧 Let me get the context ready before I compact the conversation."
        if compact_phase == "context_collapse_start":
            if prefers_chinese:
                return "🫧 我先把太长的上下文折叠一下，让后面的压缩更快一点～"
            return "🫧 I’m collapsing the oversized context first so compaction can move faster."
        if compact_phase == "context_collapse_end":
            if prefers_chinese:
                return "🫧 上下文已经先收紧了一层，继续压缩重点～"
            return "🫧 The context is trimmed down now. Continuing with the main compaction."
        if compact_phase in {"session_memory_start", "compact_start"}:
            if prefers_chinese:
                if compact_phase == "session_memory_start":
                    return "🧠 我先把前面的聊天重点悄悄捋顺一下，马上继续～"
                if compact_trigger == "reactive":
                    return "🧠 这轮上下文太长了，我先压缩一下记忆，然后马上继续重试～"
                return "🧠 聊天有点长啦，我先帮你悄悄压缩一下记忆，马上继续～"
            if compact_phase == "session_memory_start":
                return "🧠 Let me quickly condense the earlier parts of this chat, then I’ll keep going."
            if compact_trigger == "reactive":
                return "🧠 The context is too large for this turn. I’ll compact the memory and retry."
            return "🧠 This chat is getting long. I’ll compact the memory and keep going."
        if compact_phase == "compact_retry":
            suffix = f" (attempt {attempt})" if attempt is not None else ""
            if prefers_chinese:
                return f"🔁 压缩记忆这一步有点卡，我换个方式再试一次{suffix}。"
            return f"🔁 Compaction got stuck, trying a lighter retry{suffix}."
        if compact_phase == "compact_failed":
            if prefers_chinese:
                return "⚠️ 这次记忆压缩没成功，我先跳过它继续处理你的消息。"
            return "⚠️ Memory compaction did not complete. I’m skipping it and continuing."
        return ""
    return text


def _build_inbound_user_message(message: InboundMessage) -> ConversationMessage:
    """Convert an inbound channel message into user content blocks."""
    content: list[TextBlock | ImageBlock] = []
    speaker_context = _build_speaker_context(message)
    base = (message.content or "").strip()
    if speaker_context:
        content.append(TextBlock(text=speaker_context))
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


def _should_retry_without_image_input(error_message: str, messages: list[ConversationMessage]) -> bool:
    """Return True when a provider rejects image input and history contains images."""
    if not _history_has_image_blocks(messages):
        return False
    normalized = error_message.lower()
    image_signal = any(
        phrase in normalized
        for phrase in (
            "image input",
            "image_url",
            "multimodal",
            "vision",
            "image content",
        )
    )
    rejection_signal = any(
        phrase in normalized
        for phrase in (
            "no endpoints found",
            "not support",
            "does not support",
            "unsupported",
            "cannot support",
            "can't support",
        )
    )
    return image_signal and rejection_signal


def _history_has_image_blocks(messages: list[ConversationMessage]) -> bool:
    return any(any(isinstance(block, ImageBlock) for block in message.content) for message in messages)


def _strip_image_blocks_from_engine_history(engine) -> None:
    messages = _strip_image_blocks_from_messages(list(engine.messages))
    if hasattr(engine, "load_messages"):
        engine.load_messages(messages)
    else:
        engine.messages = messages


def _strip_image_blocks_from_messages(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    return [_strip_image_blocks_from_message(message) for message in messages]


def _strip_image_blocks_from_message(message: ConversationMessage) -> ConversationMessage:
    if not any(isinstance(block, ImageBlock) for block in message.content):
        return message
    content = [block for block in message.content if not isinstance(block, ImageBlock)]
    if not any(isinstance(block, TextBlock) for block in content):
        content.append(TextBlock(text=_IMAGE_FALLBACK_NOTE))
    return message.model_copy(update={"content": content})


def _build_speaker_context(message: InboundMessage) -> str:
    """Return a lightweight speaker header for group-chat messages."""
    metadata = message.metadata or {}
    chat_type = str(metadata.get("chat_type") or "").strip().lower()
    sender_label = (
        str(metadata.get("sender_display_name") or "").strip()
        or str(metadata.get("sender_label") or "").strip()
        or str(message.sender_id).strip()
    )
    if chat_type != "group":
        return ""
    if not sender_label:
        sender_label = "unknown"
    return (
        "[Channel speaker]\n"
        f"This message was sent in a group chat by: {sender_label}\n"
        f"Sender id: {message.sender_id}"
    )


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
