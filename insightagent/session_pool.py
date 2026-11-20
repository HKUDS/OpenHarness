"""会话池：命名会话复用 + ephemeral 单轮；白名单注册表；SSE 事件转换。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from insightagent import capabilities, session_files, storage, users
from insightagent.config import InsightConfig
from insightagent.plugin_support import LoadedPlugin, PluginDeps, build_deps
from insightagent.prompts import build_capability_addendum, build_system_prompt
from openharness.engine.stream_events import (
    AssistantTextDelta,
    AssistantThinkingDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.tools.list_mcp_resources_tool import ListMcpResourcesTool
from openharness.tools.mcp_tool import McpToolAdapter
from openharness.tools.read_mcp_resource_tool import ReadMcpResourceTool
from openharness.tools.skill_tool import SkillTool
from openharness.ui.runtime import RuntimeBundle, build_runtime, close_runtime, start_runtime

logger = logging.getLogger("insightagent.session_pool")


class SessionBusy(RuntimeError):
    """同一命名会话已有回合在执行（HTTP 409）。"""


class AuthUnavailable(RuntimeError):
    """LLM 认证不可用（build_runtime 抛 SystemExit 转换而来）。"""


def _exit_to_message(exc: BaseException) -> str:
    text = str(exc).strip()
    if text and text not in {"1", "0"}:
        return text
    return (
        "LLM 认证不可用：请先运行 `oh auth login` 配置模型凭证，"
        "或设置 ANTHROPIC_API_KEY / OPENAI_API_KEY 环境变量（详见服务端日志）"
    )


@dataclass
class PooledSession:
    """一个命名会话的常驻运行时。"""

    session_id: str
    plugin_names: tuple[str, ...]
    bundle: RuntimeBundle
    mcp_names: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()
    profile: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.time)


async def _auto_approve(tool_name: str, reason: str) -> bool:
    return True


async def _noop_ask(question: str) -> str:
    return ""


def event_to_sse(event: Any) -> dict[str, Any] | None:
    """StreamEvent → SSE 载荷 dict（与 app.py stream-json 契约对齐）。"""
    if isinstance(event, AssistantTextDelta):
        return {"type": "assistant_delta", "text": event.text}
    if isinstance(event, AssistantThinkingDelta):
        return {"type": "thinking_delta", "text": event.text}
    if isinstance(event, AssistantTurnComplete):
        usage = None
        try:
            usage = event.usage.model_dump()
        except Exception:  # noqa: BLE001
            usage = None
        return {"type": "turn_complete", "text": event.message.text.strip(), "usage": usage}
    if isinstance(event, ToolExecutionStarted):
        return {"type": "tool_started", "tool_name": event.tool_name, "tool_input": event.tool_input}
    if isinstance(event, ToolExecutionCompleted):
        return {
            "type": "tool_completed",
            "tool_name": event.tool_name,
            "output": event.output,
            "is_error": event.is_error,
        }
    if isinstance(event, ErrorEvent):
        return {"type": "error", "message": event.message, "recoverable": event.recoverable}
    if isinstance(event, StatusEvent):
        return {"type": "status", "message": event.message}
    if isinstance(event, CompactProgressEvent):
        return {
            "type": "compact_progress",
            "phase": event.phase,
            "trigger": event.trigger,
            "attempt": event.attempt,
            "message": event.message,
        }
    return None


def _record_event(record: dict[str, Any], payload: dict[str, Any]) -> None:
    """把 SSE 事件归并进回合回放记录（thinking/answer 累积，工具事件截断存档）。"""
    etype = payload.get("type")
    if etype == "thinking_delta":
        record["thinking"] += payload.get("text") or ""
    elif etype == "assistant_delta":
        record["answer"] += payload.get("text") or ""
    elif etype == "turn_complete":
        text = payload.get("text") or ""
        if text and len(text) >= len(record.get("answer") or ""):
            record["answer"] = text
        if payload.get("usage"):
            record["usage"] = payload["usage"]
    elif etype == "error":
        record["error"] = payload.get("message") or "未知错误"
    elif etype == "tool_started":
        record["events"].append(
            {"type": "tool_started", "tool_name": payload.get("tool_name") or "tool",
             "input": str(payload.get("tool_input"))[:200]}
        )
    elif etype == "tool_completed":
        record["events"].append(
            {"type": "tool_completed", "tool_name": payload.get("tool_name") or "tool",
             "is_error": bool(payload.get("is_error"))}
        )


class SessionPool:
    """管理命名会话的 RuntimeBundle 池与 ephemeral 一次性运行时。"""

    def __init__(self, cfg: InsightConfig, deps: PluginDeps | None = None, user_home: Path | None = None) -> None:
        self._cfg = cfg
        self._deps = deps
        # 多用户：user_home 指向该用户独立 openharness home（None=系统级共享池）
        self._user_home = user_home
        self._plugin_roots: list[Path] = [user_home / "plugins"] if user_home is not None else []
        self._pool: OrderedDict[str, PooledSession] = OrderedDict()
        self._pool_lock = asyncio.Lock()
        self._concurrency = asyncio.Semaphore(cfg.server.max_concurrent)

    @property
    def deps(self) -> PluginDeps:
        if self._deps is None:
            self._deps = build_deps(self._cfg)
        return self._deps

    def plugin_state(self) -> dict[str, Any]:
        """当前池状态（/health 用）。"""
        return {
            "sessions": len(self._pool),
            "session_ids": list(self._pool.keys()),
        }

    async def try_acquire_slot(self) -> bool:
        """非阻塞获取并发槽；满时返回 False（服务层转 429）。"""
        try:
            await asyncio.wait_for(self._concurrency.acquire(), timeout=0.05)
            return True
        except TimeoutError:
            return False

    def release_slot(self) -> None:
        self._concurrency.release()

    def precheck(
        self,
        session_id: str | None,
        loaded: list[LoadedPlugin],
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        """流式响应开始前的并发校验；能力集变化允许，届时从快照重建会话。"""
        if session_id is None:
            return
        pooled = self._pool.get(session_id)
        if pooled is not None and pooled.lock.locked():
            raise SessionBusy(f"会话 {session_id} 正在处理上一条消息，请稍后再试")

    def _apply_capabilities(
        self,
        bundle: RuntimeBundle,
        loaded: list[LoadedPlugin],
        *,
        session_id: str | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> None:
        """把工具注册表裁剪为当前能力白名单并刷新系统提示；可重复调用（同会话切换能力时原地生效）。"""
        registry = bundle.tool_registry
        selected_servers = set(mcp_servers or [])
        skill_defs, _skipped = capabilities.resolve_skills(
            skills, self._cfg, user_home=self._user_home, extra_roots=self._plugin_roots or None
        )
        keep: list = []
        for tool in list(registry._tools.values()):
            if isinstance(tool, McpToolAdapter):
                if tool.server_name in selected_servers:
                    keep.append(tool)
            elif isinstance(tool, SkillTool):
                if skill_defs:
                    keep.append(tool)
            elif isinstance(tool, (ListMcpResourcesTool, ReadMcpResourceTool)) and selected_servers:
                keep.append(tool)
        registry._tools.clear()
        for tool in keep:
            registry.register(tool)
        for plugin in loaded:
            for tool in plugin.tools:
                # 插件可依赖 MCP 服务（如 report-search 走「报表检索」服务）：
                # 注入会话级客户端管理器，使插件内部能直接调用 MCP 工具。
                attach = getattr(tool, "attach_mcp", None)
                if callable(attach):
                    attach(bundle.mcp_manager)
                registry.register(tool)
        # 会话文件工具：读取附件/产出文件（按会话隔离目录）
        files_sid = session_id or f"eph-{time.strftime('%Y%m%d%H%M%S')}-{id(loaded):x}"
        registry.register(session_files.ReadSessionFileTool(self._cfg, files_sid))
        registry.register(session_files.WriteSessionFileTool(self._cfg, files_sid))
        addendum = build_capability_addendum(
            [t for t in keep if isinstance(t, McpToolAdapter)],
            skill_defs,
        )
        file_note = (
            "## 会话文件\n\n"
            "- `read_session_file(path)`: 读取当前会话上传的附件或已产出的文件全文；\n"
            "- `write_session_file(filename, content)`: 把报告/数据保存为会话产出文件（用户可下载）。\n"
            "用户消息中标注「附件」的内容来自上传文件，可用 read_session_file 读取全文。\n"
        )
        addendum = "\n\n".join(x for x in (addendum, file_note) if x)
        base = build_system_prompt(loaded, self._cfg)
        bundle.engine.set_system_prompt(f"{base}\n\n{addendum}" if addendum else base)

    async def _build_bundle(
        self,
        loaded: list[LoadedPlugin],
        restore_messages: list[dict] | None = None,
        *,
        session_id: str | None = None,
        profile: str | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> RuntimeBundle:
        """组装运行时并把工具注册表裁剪为：插件工具 + 所选 MCP 适配器（+ 选技能时的 skill 工具）+ 会话文件工具。

        profile 为本次会话选定的模型服务（settings.profiles 键）；None 时用 cfg.agent.profile。
        """
        plugin_skill_dirs = capabilities.plugin_skill_dirs(self._cfg, extra_roots=self._plugin_roots or None)
        active_profile = profile or self._cfg.agent.profile
        # 切换到非默认 profile 时让该 profile 的默认模型生效
        model = self._cfg.agent.model if active_profile == self._cfg.agent.profile else None
        # 多用户：切换 OPENHARNESS_CONFIG_DIR 到该用户 home 后再构建（profiles/凭证/MCP/skills 均取用户层）
        async with users.openharness_home(self._user_home):
            bundle = await build_runtime(
                system_prompt=build_system_prompt(loaded, self._cfg),
                model=model,
                active_profile=active_profile,
                max_turns=self._cfg.agent.max_turns,
                restore_messages=restore_messages,
                extra_plugin_roots=[str(self._cfg.plugin_root_path())]
                + [str(r) for r in self._plugin_roots],
                extra_skill_dirs=plugin_skill_dirs,
                permission_prompt=_auto_approve,
                ask_user_prompt=_noop_ask,
            )
        # 引擎持有同一 ToolRegistry 实例：清空默认 43+ 工具，按能力选择重建白名单。
        self._apply_capabilities(
            bundle,
            loaded,
            session_id=session_id,
            mcp_servers=mcp_servers,
            skills=skills,
        )
        await start_runtime(bundle)
        return bundle

    async def _evict_locked(self) -> None:
        """超容量时淘汰最久未使用且未被占用的会话。"""
        limit = self._cfg.server.max_sessions
        while len(self._pool) > limit:
            victim: PooledSession | None = None
            for pooled in self._pool.values():
                if not pooled.lock.locked():
                    victim = pooled
                    break
            if victim is None:
                break
            self._pool.pop(victim.session_id, None)
            try:
                await close_runtime(victim.bundle)
            except Exception:  # noqa: BLE001
                pass

    async def _acquire_named(
        self,
        session_id: str,
        loaded: list[LoadedPlugin],
        profile: str | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> PooledSession:
        names = tuple(p.name for p in loaded)
        mcp_names = tuple(dict.fromkeys(mcp_servers or []))
        skill_names = tuple(dict.fromkeys(skills or []))
        effective_profile = profile or self._cfg.agent.profile or ""
        stale: PooledSession | None = None
        async with self._pool_lock:
            pooled = self._pool.get(session_id)
            if pooled is not None:
                caps_changed = (
                    set(pooled.plugin_names) != set(names)
                    or set(pooled.mcp_names) != set(mcp_names)
                    or set(pooled.skill_names) != set(skill_names)
                )
                if pooled.profile != effective_profile:
                    # 模型服务变化：移除旧运行时，下面从快照重建（保留对话历史）
                    self._pool.pop(session_id, None)
                    stale = pooled
                elif caps_changed:
                    # 能力集变化：原地重裁工具白名单并刷新系统提示，历史与运行时都保留
                    self._apply_capabilities(
                        pooled.bundle,
                        loaded,
                        session_id=session_id,
                        mcp_servers=list(mcp_names),
                        skills=list(skill_names),
                    )
                    pooled.plugin_names = names
                    pooled.mcp_names = mcp_names
                    pooled.skill_names = skill_names
                    pooled.last_used = time.time()
                    self._pool.move_to_end(session_id)
                    logger.info(
                        "session capability switch (in place): %s plugins=%s mcp=%s skills=%s",
                        session_id,
                        list(names),
                        list(mcp_names),
                        list(skill_names),
                    )
                    return pooled
                else:
                    pooled.last_used = time.time()
                    self._pool.move_to_end(session_id)
                    return pooled
        if stale is not None:
            try:
                await close_runtime(stale.bundle)
            except Exception:  # noqa: BLE001
                pass
            logger.info(
                "session rebuild: %s plugins=%s mcp=%s skills=%s profile=%s (from snapshot)",
                session_id,
                list(names),
                list(mcp_names),
                list(skill_names),
                effective_profile,
            )

        snapshot = storage.load_snapshot(self._cfg, session_id)
        restore: list[dict] | None = (snapshot or {}).get("messages") or None

        bundle = await self._build_bundle(
            loaded,
            restore_messages=restore,
            session_id=session_id,
            profile=profile,
            mcp_servers=list(mcp_names),
            skills=list(skill_names),
        )
        pooled = PooledSession(
            session_id=session_id,
            plugin_names=names,
            bundle=bundle,
            mcp_names=mcp_names,
            skill_names=skill_names,
            profile=effective_profile,
        )
        async with self._pool_lock:
            self._pool[session_id] = pooled
            self._pool.move_to_end(session_id)
            await self._evict_locked()
        logger.info(
            "session created: %s plugins=%s mcp=%s skills=%s profile=%s restored=%d msgs",
            session_id,
            list(names),
            list(mcp_names),
            list(skill_names),
            effective_profile,
            len(restore or []),
        )
        return pooled

    async def _drop_named(self, session_id: str) -> bool:
        async with self._pool_lock:
            pooled = self._pool.pop(session_id, None)
        if pooled is None:
            return False
        try:
            await close_runtime(pooled.bundle)
        except Exception:  # noqa: BLE001
            pass
        return True

    async def stream_chat(
        self,
        *,
        message: str,
        session_id: str | None,
        loaded: list[LoadedPlugin],
        profile: str | None = None,
        mcp_servers: list[str] | None = None,
        skills: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """执行一个用户回合，产出 SSE 事件 dict 流。

        并发槽由调用方（服务层）通过 try_acquire_slot/release_slot 管理，满时 429。
        命名会话：复用/新建池内运行时，回合结束落盘快照；profile 变化时从快照重建（切模型）。
        ephemeral：每次新建运行时，回合结束即关闭。
        """
        if session_id is None:
            try:
                bundle = await self._build_bundle(loaded, profile=profile, mcp_servers=mcp_servers, skills=skills)
            except (Exception, SystemExit) as exc:  # noqa: BLE001
                # build_runtime 认证失败抛 SystemExit；转为错误事件而非打穿流
                yield {"type": "error", "message": _exit_to_message(exc), "recoverable": False}
                yield {"type": "turn_complete", "text": "", "usage": None, "aborted": True}
                return
            try:
                async for payload in self._run_turn(bundle, message):
                    yield payload
            finally:
                try:
                    await close_runtime(bundle)
                except Exception:  # noqa: BLE001
                    pass
            return

        try:
            pooled = await self._acquire_named(session_id, loaded, profile=profile, mcp_servers=mcp_servers, skills=skills)
        except SessionBusy:
            raise
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            yield {"type": "error", "message": _exit_to_message(exc), "recoverable": False}
            yield {"type": "turn_complete", "text": "", "usage": None, "aborted": True}
            return
        if pooled.lock.locked():
            raise SessionBusy(f"会话 {session_id} 正在处理上一条消息，请稍后再试")
        record: dict[str, Any] = {}
        async with pooled.lock:
            pooled.last_used = time.time()
            try:
                async for payload in self._run_turn(pooled.bundle, message, record=record):
                    yield payload
            finally:
                engine = pooled.bundle.engine
                try:
                    storage.save_snapshot(
                        self._cfg,
                        session_id=session_id,
                        plugins=list(pooled.plugin_names),
                        model=engine.model,
                        system_prompt=engine.system_prompt,
                        messages=engine.messages,
                        usage=engine.total_usage,
                        turn=record if record.get("message") is not None else None,
                    )
                except Exception:  # noqa: BLE001
                    pass

    async def _run_turn(self, bundle: RuntimeBundle, message: str, record: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        """执行一个用户回合；record 非空时收集回放数据（思考/回答/工具/用量）。"""
        engine = bundle.engine
        had_turn_complete = False
        if record is not None:
            record.update(message=message, thinking="", answer="", events=[], usage=None, error=None)
        logger.info("turn start: model=%s message=%r", engine.model, message[:80])
        try:
            async for event in engine.submit_message(message):
                if isinstance(event, ToolExecutionStarted):
                    logger.info("tool call: %s input=%s", event.tool_name, str(event.tool_input)[:120])
                payload = event_to_sse(event)
                if payload is not None:
                    if payload["type"] == "turn_complete":
                        had_turn_complete = True
                    if record is not None:
                        _record_event(record, payload)
                    yield payload
        except (Exception, SystemExit) as exc:
            logger.error("turn failed: %s", _exit_to_message(exc), exc_info=exc)
            err = {"type": "error", "message": _exit_to_message(exc), "recoverable": False}
            if record is not None:
                _record_event(record, err)
            yield err
        finally:
            logger.info(
                "turn end: turns=%d messages=%d ok=%s",
                len(engine.messages),
                len(engine.messages),
                had_turn_complete,
            )
            if not had_turn_complete:
                # 异常中断时兜底发 turn_complete，保证客户端回合边界完整
                payload = {
                    "type": "turn_complete",
                    "text": "",
                    "usage": None,
                    "aborted": True,
                }
                if record is not None:
                    record["error"] = record.get("error") or "回合异常中断"
                yield payload

    async def close_all(self) -> None:
        async with self._pool_lock:
            pooled_all = list(self._pool.values())
            self._pool.clear()
        for pooled in pooled_all:
            try:
                await close_runtime(pooled.bundle)
            except Exception:  # noqa: BLE001
                pass
