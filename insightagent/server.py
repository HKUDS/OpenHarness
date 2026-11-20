"""统一 HTTP + SSE 服务（多用户版）。

- /api/auth/*：注册 / 登录 / 登出 / 我的信息 / 修改密码
- /api/chat、/api/sessions*、/api/capabilities：登录用户隔离（数据目录与运行时按用户分桶）
- /api/user/*：用户自定义模型 profiles、MCP、home 管理
- /：Vue3 前端（frontend/dist，桌面端与移动端自适应）
"""

from __future__ import annotations

import copy
import csv
import html
import json
import logging
import os
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from insightagent import capabilities as caps
from insightagent import session_files, storage, users
from insightagent.config import InsightConfig, load_config
from insightagent.plugin_support import (
    PluginResolutionError,
    build_deps,
    discover_plugins,
    resolve_plugins,
)
from insightagent.session_pool import SessionBusy, SessionPool

logger = logging.getLogger("insightagent")


def _mask_dsn(dsn: str) -> str:
    """DSN 脱敏：隐藏密码段。"""
    if "://" not in dsn:
        return dsn
    scheme, _, rest = dsn.partition("://")
    if "@" not in rest:
        return dsn
    creds, _, hostpart = rest.rpartition("@")
    user = creds.split(":", 1)[0] if ":" in creds else creds
    return f"{scheme}://{user}:***@{hostpart}"


def _print_startup_banner(cfg: InsightConfig, port: int | None = None) -> None:
    """启动横幅：配置、数据源（脱敏）、插件就绪状态、关键端点。"""
    lines = [
        "",
        "=" * 62,
        " insightagent 服务已启动（多用户模式）",
        "=" * 62,
        f"  配置文件    : {cfg.config_path}",
    ]
    if port:
        lines.append(f"  监听端口    : http://127.0.0.1:{port}  (GET /health)")
    lines.append(f"  会话根目录  : {cfg.sessions.dir}")
    if cfg.databases:
        lines.append(f"  数据源({len(cfg.databases)}):")
        for db in cfg.databases:
            lines.append(f"    - [{db.id}] {db.type} {_mask_dsn(db.dsn)}")
    else:
        lines.append("  数据源      : 无")
    if cfg.milvus:
        lines.append(f"  Milvus      : {cfg.milvus.uri} / collection={cfg.milvus.collection}")
    lines.append(f"  会话并发    : max_sessions={cfg.server.max_sessions} 并发上限={cfg.server.max_concurrent}/用户")
    for p in discover_plugins(cfg):
        state = "就绪" if p.ready else f"未就绪({p.reason})"
        mark = "+" if p.name in cfg.agent.default_plugins else "-"
        lines.append(f"  [{mark}] 插件 {p.name:<14} {state}")
    lines.append("=" * 62)
    print("\n".join(lines), file=sys.stderr, flush=True)
    logger.info(
        "insightagent started: config=%s sessions_dir=%s databases=%d plugins_ready=%s",
        cfg.config_path,
        cfg.sessions.dir,
        len(cfg.databases),
        [p.name for p in discover_plugins(cfg) if p.ready],
    )


# ── 会话文件在线预览：纯标准库解析（csv / xlsx / docx），md/txt 直接回文本 ──
_PREVIEW_TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".log", ".json", ".py", ".yaml", ".yml",
    ".sql", ".toml", ".ini", ".xml", ".js", ".ts", ".sh", ".bat", ".ps1",
}
_PREVIEW_MAX_ROWS = 300
_PREVIEW_MAX_COLS = 40
_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _table_html(rows: list[list[str]]) -> str:
    if not rows:
        return '<div class="pv-empty">（空文件）</div>'

    def _row(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{_esc(c)}</{tag}>" for c in cells) + "</tr>"

    head, *body = rows
    parts = ["<table><thead>", _row(head, "th"), "</thead><tbody>"]
    parts.extend(_row(r, "td") for r in body)
    parts.append("</tbody></table>")
    return "".join(parts)


def _csv_preview_html(path: Path) -> str:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if i >= _PREVIEW_MAX_ROWS:
                rows.append([f"…（仅显示前 {_PREVIEW_MAX_ROWS} 行）"])
                break
            rows.append(row[:_PREVIEW_MAX_COLS])
    return _table_html(rows)


def _xlsx_preview_html(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            si_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{_XLSX_NS}t")) for si in si_root.findall(f"{_XLSX_NS}si")]
        sheet = next(
            (n for n in sorted(zf.namelist()) if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
            None,
        )
        if sheet is None:
            return '<div class="pv-empty">（未找到工作表）</div>'
        root = ET.fromstring(zf.read(sheet))
    rows: list[list[str]] = []
    for r_i, row in enumerate(root.iter(f"{_XLSX_NS}row")):
        if r_i >= _PREVIEW_MAX_ROWS:
            rows.append([f"…（仅显示前 {_PREVIEW_MAX_ROWS} 行）"])
            break
        cells: list[str] = []
        for c in row.findall(f"{_XLSX_NS}c"):
            if len(cells) >= _PREVIEW_MAX_COLS:
                break
            ctype = c.get("t")
            if ctype == "s":
                v = c.find(f"{_XLSX_NS}v")
                idx = int(v.text) if v is not None and v.text and v.text.strip().lstrip("-").isdigit() else -1
                cells.append(shared[idx] if 0 <= idx < len(shared) else "")
            elif ctype == "inlineStr":
                cells.append("".join(t.text or "" for t in c.iter(f"{_XLSX_NS}t")))
            else:
                v = c.find(f"{_XLSX_NS}v")
                cells.append((v.text or "") if v is not None else "")
        rows.append(cells)
    return _table_html(rows)


def _docx_preview_html(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        if "word/document.xml" not in zf.namelist():
            return '<div class="pv-empty">（未找到文档正文）</div>'
        root = ET.fromstring(zf.read("word/document.xml"))

    def _para_text(node: ET.Element) -> str:
        return "".join(t.text or "" for t in node.iter(f"{_DOCX_NS}t"))

    parts: list[str] = []
    for child in list(root.find(f"{_DOCX_NS}body") or []):
        if child.tag == f"{_DOCX_NS}p":
            text = _para_text(child)
            parts.append(f"<p>{_esc(text)}</p>" if text else "<p><br></p>")
        elif child.tag == f"{_DOCX_NS}tbl":
            trs = [
                "<tr>" + "".join(f"<td>{_esc(_para_text(tc))}</td>" for tc in tr.findall(f"{_DOCX_NS}tc")) + "</tr>"
                for tr in child.findall(f"{_DOCX_NS}tr")
            ]
            parts.append("<table>" + "".join(trs) + "</table>")
    return "".join(parts) or '<div class="pv-empty">（空文档）</div>'


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    plugins: list[str] | None = None
    mcp_servers: list[str] | None = None
    skills: list[str] | None = None
    files: list[str] | None = None
    profile: str | None = None
    stream: bool = True


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=1, max_length=128)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    label: str = ""
    provider: str = ""
    api_format: str = "openai"
    base_url: str = ""
    default_model: str = ""
    api_key: str | None = None  # None=不变；""=清除；非空=写入
    context_window_tokens: int | None = None


class McpUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=512)


# 允许写入用户 settings.json profiles 的白名单字段
_PROFILE_FIELDS = (
    "label", "provider", "api_format", "auth_source", "default_model",
    "base_url", "credential_slot", "context_window_tokens",
    "auto_compact_threshold_tokens", "allowed_models",
)
_AUTH_SOURCE_BY_FORMAT = {"anthropic": "anthropic_api_key", "openai": "openai_api_key"}


def create_app(cfg: InsightConfig | None = None) -> FastAPI:
    """构建 insightagent FastAPI 应用；cfg 缺省时加载配置文件。"""
    if cfg is None:
        cfg = load_config()
    # OpenHarness 侧（settings.json / credentials / MCP 配置）与本服务配置文件同目录，
    # 否则会回落到 ~/.openharness，导致 MCP 与自定义模型服务「不可用」。
    if cfg.config_path is not None and not os.environ.get("OPENHARNESS_CONFIG_DIR"):
        home = cfg.config_path.parent
        if (home / "settings.json").exists():
            os.environ["OPENHARNESS_CONFIG_DIR"] = str(home)
    # 多用户初始化：固化系统 home；凭据强制文件后端（各用户 home 独立，避免 keyring 全局串号）
    users.set_system_home(Path(os.environ["OPENHARNESS_CONFIG_DIR"]) if os.environ.get("OPENHARNESS_CONFIG_DIR") else None)
    users.disable_keyring_for_multuser()

    app = FastAPI(title="insightagent", version="0.2.0")
    app.state.base_cfg = cfg
    app.state.user_cfgs: dict[str, InsightConfig] = {}
    app.state.user_pools: dict[str, SessionPool] = {}
    app.state.shared_deps = None  # lifespan 预热

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conf: InsightConfig = app.state.base_cfg
        # 启动预热：共享依赖（embedding/Milvus 客户端懒加载，失败不阻断启动）
        if app.state.shared_deps is None:
            app.state.shared_deps = build_deps(conf)
        port = getattr(app.state, "banner_port", None)
        _print_startup_banner(conf, port=port)
        logger.info("lifespan: multi-user server ready (db=%d sources)", len(conf.databases))
        yield
        pools: dict[str, SessionPool] = app.state.user_pools
        for pool in pools.values():
            await pool.close_all()
        pools.clear()
        logger.info("lifespan: all user sessions closed, shutdown complete")

    app.router.lifespan_context = lifespan

    # ── 用户上下文：鉴权 + 每用户 cfg / pool / home ──

    def _require_user(request: Request) -> dict[str, Any]:
        """Bearer token（或 ?token= 兜底，供文件预览等链接直用）→ 用户；失败 401。"""
        auth = request.headers.get("authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        token = token or request.query_params.get("token", "")
        user = users.authenticate(app.state.base_cfg, token)
        if user is None:
            raise HTTPException(status_code=401, detail="未登录或登录已过期")
        users.ensure_user_home(app.state.base_cfg, user["user_id"])
        return user

    def _user_cfg(user: dict[str, Any]) -> InsightConfig:
        """该用户的隔离配置：sessions 指向 <root>/users/<uid>/sessions。"""
        uid = user["user_id"]
        cfgs: dict[str, InsightConfig] = app.state.user_cfgs
        if uid not in cfgs:
            cloned = copy.deepcopy(app.state.base_cfg)
            cloned.sessions.dir = str(users.user_sessions_dir(app.state.base_cfg, uid))
            cfgs[uid] = cloned
        return cfgs[uid]

    def _user_home(user: dict[str, Any]) -> Path:
        return users.user_home_dir(app.state.base_cfg, user["user_id"])

    def _plugin_roots(user: dict[str, Any]) -> list[Path]:
        root = users.user_plugins_dir(app.state.base_cfg, user["user_id"])
        return [root] if root.is_dir() else []

    def _pool_for(user: dict[str, Any]) -> SessionPool:
        uid = user["user_id"]
        pools: dict[str, SessionPool] = app.state.user_pools
        if uid not in pools:
            pools[uid] = SessionPool(
                _user_cfg(user),
                deps=app.state.shared_deps,
                user_home=users.user_home_dir(app.state.base_cfg, uid),
            )
        return pools[uid]

    def _plugins_payload(user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        conf: InsightConfig = app.state.base_cfg
        extra = _plugin_roots(user) if user else []
        return [
            {
                "name": p.name,
                "description": p.description,
                "enabled": p.name in conf.agent.default_plugins or p.scope == "user",
                "ready": p.ready,
                "reason": p.reason,
                "scope": p.scope,
            }
            for p in discover_plugins(conf, extra_roots=extra)
        ]

    # ── 健康检查（无需登录） ──
    @app.get("/health")
    async def health() -> dict[str, Any]:
        pools: dict[str, SessionPool] = app.state.user_pools
        return {
            "status": "ok",
            "users_online_pools": len(pools),
            "sessions": {uid: pool.plugin_state() for uid, pool in pools.items()},
        }

    # ── 认证 ──
    @app.post("/api/auth/register")
    async def register(req: RegisterRequest) -> dict[str, Any]:
        try:
            user = users.register(app.state.base_cfg, req.username, req.password, req.display_name)
        except users.UserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _, token = users.login(app.state.base_cfg, req.username, req.password)
        return {"user": user, "token": token}

    @app.post("/api/auth/login")
    async def login(req: LoginRequest) -> dict[str, Any]:
        try:
            user, token = users.login(app.state.base_cfg, req.username, req.password)
        except users.UserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"user": user, "token": token}

    @app.post("/api/auth/logout")
    async def logout(request: Request, user: dict = Depends(_require_user)) -> dict[str, Any]:
        auth = request.headers.get("authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        users.logout(app.state.base_cfg, token)
        return {"ok": True}

    @app.get("/api/auth/me")
    async def me(user: dict = Depends(_require_user)) -> dict[str, Any]:
        return {"user": user}

    @app.post("/api/auth/password")
    async def change_password(req: PasswordChangeRequest, user: dict = Depends(_require_user)) -> dict[str, Any]:
        try:
            users.change_password(app.state.base_cfg, user["user_id"], req.old_password, req.new_password)
        except users.UserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "message": "密码已修改，全部登录已失效，请重新登录"}

    @app.post("/api/auth/profile")
    async def update_user_profile(
        payload: dict[str, Any], user: dict = Depends(_require_user)
    ) -> dict[str, Any]:
        display = str(payload.get("display_name") or "")
        return {"user": users.update_profile(app.state.base_cfg, user["user_id"], display)}

    # ── 能力发现（用户层合并视图） ──
    @app.get("/api/plugins")
    async def plugins(user: dict = Depends(_require_user)) -> dict[str, Any]:
        return {"plugins": _plugins_payload(user)}

    @app.get("/api/capabilities")
    async def capabilities(user: dict = Depends(_require_user)) -> dict[str, Any]:
        """能力发现：插件 / MCP 连接器（含连接探测与工具清单） / 技能 / 模型服务 四组（system+user 合并）。"""
        conf = _user_cfg(user)
        home = _user_home(user)
        return {
            "plugins": _plugins_payload(user),
            "mcp_servers": await caps.mcp_server_payload(user_home=home),
            "skills": caps.skill_payload(conf, user_home=home, extra_roots=_plugin_roots(user)),
            "profiles": caps.profile_payload(conf, user_home=home),
        }

    # ── 用户自定义：模型 profiles ──
    @app.get("/api/user/settings")
    async def get_user_settings(user: dict = Depends(_require_user)) -> dict[str, Any]:
        conf = _user_cfg(user)
        home = _user_home(user)
        raw = users.load_user_settings(app.state.base_cfg, user["user_id"])
        profiles = caps.profile_payload(conf, user_home=home)
        # 用户层 profile 标注是否已配置密钥（不回传密钥本体）
        for item in profiles["items"]:
            if item["scope"] != "user":
                continue
            name = item["name"]
            p = (raw.get("profiles") or {}).get(name) or {}
            item["has_api_key"] = _user_credential_exists(home, p, name)
            item["base_url"] = p.get("base_url")
        return {"active_profile": raw.get("active_profile"), "profiles": profiles, "raw_user_profiles": raw.get("profiles", {})}

    @app.put("/api/user/profiles")
    async def upsert_profile(req: ProfileUpdateRequest, user: dict = Depends(_require_user)) -> dict[str, Any]:
        """新增/更新用户模型服务；api_key 非空时写入用户 home 凭据文件。"""
        uid = user["user_id"]
        raw = users.load_user_settings(app.state.base_cfg, uid)
        profiles = raw.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            profiles = raw["profiles"] = {}
        entry: dict[str, Any] = dict(profiles.get(req.name) or {})
        api_format = req.api_format or "openai"
        entry.update(
            {
                "label": req.label or req.name,
                "provider": req.provider or ("anthropic" if api_format == "anthropic" else "openai"),
                "api_format": api_format,
                "auth_source": _AUTH_SOURCE_BY_FORMAT.get(api_format, "openai_api_key"),
                "credential_slot": req.name,
            }
        )
        for field in ("base_url", "default_model"):
            value = getattr(req, field)
            if value:
                entry[field] = value
        if req.context_window_tokens:
            entry["context_window_tokens"] = req.context_window_tokens
        profiles[req.name] = entry
        if "mcp_servers" not in raw and not raw.get("active_profile"):
            raw.setdefault("mcp_servers", {})
        users.save_user_settings(app.state.base_cfg, uid, raw)
        if req.api_key is not None:
            _store_user_api_key(_user_home(user), req.name, req.api_key)
        caps.invalidate_mcp_cache()  # profile 变化可能影响 readiness 展示
        return {"ok": True, "profile": req.name}

    @app.delete("/api/user/profiles/{name}")
    async def delete_profile(name: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        uid = user["user_id"]
        raw = users.load_user_settings(app.state.base_cfg, uid)
        profiles = raw.get("profiles") or {}
        if name not in profiles:
            raise HTTPException(status_code=404, detail=f"用户配置中不存在模型服务: {name}")
        del profiles[name]
        if raw.get("active_profile") == name:
            raw["active_profile"] = None
        users.save_user_settings(app.state.base_cfg, uid, raw)
        _store_user_api_key(_user_home(user), name, "")  # 顺带清除凭据
        return {"ok": True}

    @app.put("/api/user/active-profile")
    async def set_active_profile(payload: dict[str, Any], user: dict = Depends(_require_user)) -> dict[str, Any]:
        name = str(payload.get("profile") or "")
        conf = _user_cfg(user)
        known = {p["name"] for p in caps.profile_payload(conf, user_home=_user_home(user))["items"]}
        if name and name not in known:
            raise HTTPException(status_code=400, detail=f"未注册的模型服务: {name}")
        uid = user["user_id"]
        raw = users.load_user_settings(app.state.base_cfg, uid)
        raw["active_profile"] = name or None
        users.save_user_settings(app.state.base_cfg, uid, raw)
        return {"ok": True, "active_profile": name}

    # ── 用户自定义：MCP 服务器 ──
    @app.get("/api/user/mcp")
    async def get_user_mcp(user: dict = Depends(_require_user)) -> dict[str, Any]:
        raw = users.load_user_settings(app.state.base_cfg, user["user_id"])
        servers = raw.get("mcp_servers") or {}
        return {"mcp_servers": [{"name": n, "url": (c or {}).get("url", "")} for n, c in servers.items()]}

    @app.put("/api/user/mcp")
    async def upsert_mcp(req: McpUpsertRequest, user: dict = Depends(_require_user)) -> dict[str, Any]:
        if not req.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="MCP 地址需以 http:// 或 https:// 开头")
        uid = user["user_id"]
        raw = users.load_user_settings(app.state.base_cfg, uid)
        servers = raw.setdefault("mcp_servers", {})
        servers[req.name] = {"type": "http", "url": req.url}
        users.save_user_settings(app.state.base_cfg, uid, raw)
        caps.invalidate_mcp_cache(_user_home(user))
        return {"ok": True, "server": req.name}

    @app.delete("/api/user/mcp/{name}")
    async def delete_mcp(name: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        uid = user["user_id"]
        raw = users.load_user_settings(app.state.base_cfg, uid)
        servers = raw.get("mcp_servers") or {}
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"用户配置中不存在 MCP 服务器: {name}")
        del servers[name]
        users.save_user_settings(app.state.base_cfg, uid, raw)
        caps.invalidate_mcp_cache(_user_home(user))
        return {"ok": True}

    # ── 用户 home 重置（settings/credentials 回到系统默认快照） ──
    @app.post("/api/user/home/reset")
    async def reset_home(user: dict = Depends(_require_user)) -> dict[str, Any]:
        users.reset_user_home(app.state.base_cfg, user["user_id"])
        caps.invalidate_mcp_cache(_user_home(user))
        await _pool_for(user).close_all()
        return {"ok": True}

    # ── 会话（用户隔离） ──
    @app.get("/api/sessions")
    async def sessions(user: dict = Depends(_require_user)) -> dict[str, Any]:
        conf = _user_cfg(user)
        items = storage.list_sessions(conf)
        return {
            "sessions": [
                {
                    "session_id": item.get("session_id"),
                    "summary": item.get("summary", ""),
                    "message_count": item.get("message_count", 0),
                    "plugins": item.get("plugins", []),
                    "updated_at": item.get("updated_at"),
                }
                for item in items
            ]
        }

    @app.get("/api/sessions/{session_id}/transcript")
    async def transcript(session_id: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        """会话回放：逐回合的用户输入/思考/回答/工具事件/用量（来自 SQLite turns 表）。"""
        conf = _user_cfg(user)
        data = storage.load_transcript(conf, session_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        return data

    @app.get("/api/sessions/{session_id}/history")
    async def history(session_id: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        conf = _user_cfg(user)
        snapshot = storage.load_snapshot(conf, session_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        return {
            "session_id": session_id,
            "model": snapshot.get("model", ""),
            "messages": [
                {"role": m.get("role"), "content": m.get("content")}
                for m in snapshot.get("messages") or []
            ],
        }

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        conf = _user_cfg(user)
        dropped = await _pool_for(user)._drop_named(session_id)
        removed = storage.delete_session(conf, session_id)
        if not (dropped or removed):
            raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        return {"deleted": session_id}

    async def _resolve(request: ChatRequest, user: dict[str, Any]) -> tuple[list, list[dict[str, Any]]]:
        try:
            return resolve_plugins(
                request.plugins, _user_cfg(user), deps=_pool_for(user).deps, extra_roots=_plugin_roots(user)
            )
        except PluginResolutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _resolve_capabilities(
        request: ChatRequest, user: dict[str, Any]
    ) -> tuple[list[str] | None, list[str] | None, list[dict[str, Any]]]:
        """解析 MCP 连接器与技能选择：未知 MCP 报 400；未连通/未注册降级为 skipped。"""
        skipped: list[dict[str, Any]] = []
        mcp_servers: list[str] | None = None
        if request.mcp_servers:
            servers = {s["name"]: s for s in await caps.mcp_server_payload(user_home=_user_home(user))}
            mcp_servers = []
            for name in dict.fromkeys(request.mcp_servers):
                server = servers.get(name)
                if server is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"未注册的 MCP 服务器: {name}（可用: {sorted(servers) or '无'}）",
                    )
                if not server.get("ready"):
                    skipped.append({"mcp": name, "reason": f"连接不可用: {server.get('detail') or server.get('state')}"})
                else:
                    mcp_servers.append(name)
            if not mcp_servers:
                mcp_servers = None
        skill_defs, skill_skipped = caps.resolve_skills(
            request.skills, _user_cfg(user), user_home=_user_home(user), extra_roots=_plugin_roots(user)
        )
        skipped.extend(skill_skipped)
        skills = [s.name for s in skill_defs] or None
        return mcp_servers, skills, skipped

    @app.post("/api/chat")
    async def chat(request: ChatRequest, user: dict = Depends(_require_user)):
        pool = _pool_for(user)
        conf = _user_cfg(user)
        loaded, skipped = await _resolve(request, user)
        mcp_servers, skills, cap_skipped = await _resolve_capabilities(request, user)
        skipped = skipped + cap_skipped

        # 附件：读取上传文件头部内容拼入消息，供模型直接感知；全文可由 read_session_file 读取
        files_sid = request.session_id or f"eph-{uuid.uuid4().hex[:10]}"
        message = request.message
        if request.files:
            previews: list[str] = []
            uploads_root = session_files.uploads_dir(conf, files_sid)
            for raw_name in dict.fromkeys(request.files):
                fname = session_files.safe_name(raw_name)
                path = uploads_root / fname
                if path.is_file():
                    head = path.read_text(encoding="utf-8", errors="replace")[:16000]
                    previews.append(f"［附件 {fname}｜内容预览］\n{head}")
                else:
                    skipped.append({"name": fname, "reason": "附件未上传或已删除"})
            if previews:
                message = (
                    "\n\n".join(previews)
                    + "\n\n［以上为用户上传附件的预览，可用 read_session_file(path) 读取全文；以下是用户的提问］\n\n"
                    + message
                )

        # 模型服务选择校验：必须是系统或用户 settings.profiles 中已注册的 profile
        profile = request.profile
        if profile:
            known = caps.profile_payload(conf, user_home=_user_home(user)).get("items") or []
            if profile not in {p["name"] for p in known}:
                raise HTTPException(status_code=400, detail=f"未注册的模型服务: {profile}（可用: {sorted(p['name'] for p in known) or '无'}）")

        logger.info(
            "chat start: user=%s session=%s plugins=%s mcp=%s skills=%s profile=%s message=%r",
            user["username"],
            request.session_id,
            [p.name for p in loaded],
            mcp_servers,
            skills,
            profile,
            request.message[:80],
        )

        try:
            pool.precheck(request.session_id, loaded, mcp_servers=mcp_servers, skills=skills)
        except SessionBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if not await pool.try_acquire_slot():
            raise HTTPException(status_code=429, detail="并发已达上限，请稍后重试")

        async def _sse_stream() -> AsyncIterator[bytes]:
            try:
                if skipped:
                    yield ("data: " + json.dumps({"type": "skipped", "skipped": skipped}, ensure_ascii=False) + "\n\n").encode("utf-8")
                async for payload in pool.stream_chat(
                    message=message,
                    session_id=request.session_id,
                    loaded=loaded,
                    profile=profile,
                    mcp_servers=mcp_servers,
                    skills=skills,
                ):
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            except SessionBusy as exc:
                payload = {"type": "error", "message": str(exc), "recoverable": False, "status": 409}
                logger.warning("chat conflict: session=%s err=%s", request.session_id, exc)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            except Exception as exc:
                payload = {"type": "error", "message": str(exc) or exc.__class__.__name__, "recoverable": False}
                logger.exception("chat failed: session=%s", request.session_id)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            finally:
                pool.release_slot()
                logger.info("chat done: session=%s", request.session_id)
            yield b"data: [DONE]\n\n"

        if request.stream:
            return StreamingResponse(_sse_stream(), media_type="text/event-stream")

        # stream=false：聚合事件，返回报告文本与事件列表
        events: list[dict[str, Any]] = []
        report_parts: list[str] = []
        try:
            async for payload in pool.stream_chat(
                message=message,
                session_id=request.session_id,
                loaded=loaded,
                profile=profile,
                mcp_servers=mcp_servers,
                skills=skills,
            ):
                events.append(payload)
                if payload.get("type") == "turn_complete" and payload.get("text"):
                    report_parts.append(payload["text"])
        finally:
            pool.release_slot()
        result: dict[str, Any] = {"report": "\n".join(report_parts).strip(), "events": events}
        if skipped:
            result["skipped"] = skipped
        return result

    # ── 会话文件：上传附件 / 产出列表与下载 ──
    @app.post("/api/sessions/{session_id}/uploads")
    async def upload_file(session_id: str, file: UploadFile, user: dict = Depends(_require_user)) -> dict[str, Any]:
        """上传一个附件到会话 uploads 目录（multipart 字段名 file）。"""
        name = session_files.safe_name(file.filename or "upload.bin")
        data = await file.read()
        if len(data) > session_files.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"附件过大（>20MB）: {name}")
        dest = session_files.uploads_dir(_user_cfg(user), session_id) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("upload saved: user=%s session=%s name=%s size=%d", user["username"], session_id, name, len(data))
        return {"name": name, "size": len(data)}

    @app.delete("/api/sessions/{session_id}/uploads/{name}")
    async def delete_upload(session_id: str, name: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        path = session_files.uploads_dir(_user_cfg(user), session_id) / session_files.safe_name(name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"附件不存在: {name}")
        path.unlink()
        return {"deleted": path.name}

    @app.get("/api/sessions/{session_id}/artifacts")
    async def list_artifacts(session_id: str, user: dict = Depends(_require_user)) -> dict[str, Any]:
        """会话产出文件列表（outputs 目录，含上传附件以便核对）。"""
        conf = _user_cfg(user)
        return {
            "outputs": session_files.list_dir(session_files.outputs_dir(conf, session_id)),
            "uploads": session_files.list_dir(session_files.uploads_dir(conf, session_id)),
        }

    @app.get("/api/sessions/{session_id}/artifacts/{name:path}")
    async def download_artifact(session_id: str, name: str, user: dict = Depends(_require_user)) -> FileResponse:
        path = session_files.resolve_under(session_files.outputs_dir(_user_cfg(user), session_id), name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"产出文件不存在: {name}")
        return FileResponse(path, filename=path.name)

    @app.get("/api/sessions/{session_id}/uploads/{name:path}")
    async def download_upload(session_id: str, name: str, user: dict = Depends(_require_user)) -> FileResponse:
        path = session_files.resolve_under(session_files.uploads_dir(_user_cfg(user), session_id), name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"附件不存在: {name}")
        return FileResponse(path, filename=path.name)

    @app.get("/api/sessions/{session_id}/preview/{kind}/{name:path}")
    async def preview_session_file(session_id: str, kind: str, name: str, user: dict = Depends(_require_user)):
        """会话文件在线预览：md/txt 等文本原样返回，csv/xlsx 渲染表格，docx 渲染段落。"""
        conf = _user_cfg(user)
        root = (
            session_files.outputs_dir(conf, session_id)
            if kind == "outputs"
            else session_files.uploads_dir(conf, session_id)
        )
        path = session_files.resolve_under(root, name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {name}")
        ext = path.suffix.lower()
        try:
            if ext in _PREVIEW_TEXT_EXTS:
                text = path.read_text(encoding="utf-8", errors="replace")
                return PlainTextResponse(text)
            if ext == ".csv":
                return HTMLResponse(_csv_preview_html(path))
            if ext == ".xlsx":
                return HTMLResponse(_xlsx_preview_html(path))
            if ext == ".docx":
                return HTMLResponse(_docx_preview_html(path))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"预览失败（{path.name}）: {exc}") from exc
        raise HTTPException(status_code=415, detail=f"该格式（{ext or '无扩展名'}）暂不支持在线预览，请下载查看")

    # ── Web 控制台：Vue3 构建产物 ──
    dist_dir = Path(__file__).parent / "frontend" / "dist"
    if (dist_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    def _spa() -> FileResponse:
        index = dist_dir / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=503,
                detail="前端尚未构建，请先在 insightagent/frontend 目录运行 npm run build",
            )
        return FileResponse(index, media_type="text/html; charset=utf-8")

    @app.get("/", include_in_schema=False)
    async def web_console() -> FileResponse:
        return _spa()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str) -> FileResponse:
        """前端路由回退（/api、/docs 等已注册路由优先匹配）。"""
        if path.startswith(("api/", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = dist_dir / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return _spa()

    return app


# ── 用户凭据助手 ──


def _store_user_api_key(user_home: Path, profile_name: str, api_key: str) -> None:
    """在用户 home 下写入/清除 API Key（文件后端 credentials.json，槽位与运行时一致）。"""
    from openharness.auth.storage import clear_provider_credentials, store_credential

    # 自定义 profile 的 credential_slot 即 profile 名，运行时槽位为 "profile:<name>"
    slot = f"profile:{profile_name}"
    with users.openharness_home_sync(user_home):
        if api_key:
            store_credential(slot, "api_key", api_key, use_keyring=False)
        else:
            try:
                clear_provider_credentials(slot, use_keyring=False)
            except Exception:  # noqa: BLE001
                pass


def _user_credential_exists(user_home: Path, entry: dict[str, Any], profile_name: str) -> bool:
    from openharness.auth.storage import load_credential
    from openharness.config.settings import auth_source_provider_name

    slot_name = entry.get("credential_slot")
    slot = f"profile:{slot_name}" if slot_name else auth_source_provider_name(
        str(entry.get("auth_source") or "openai_api_key")
    )
    with users.openharness_home_sync(user_home):
        return load_credential(slot, "api_key", use_keyring=False) is not None


def serve(cfg: InsightConfig | None = None, host: str | None = None, port: int | None = None) -> None:
    """启动 uvicorn 服务（cli serve 入口）。"""
    import uvicorn

    # 控制台 INFO 日志：insightagent 关键路径 + uvicorn 访问/错误日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    conf = cfg or load_config()
    app = create_app(conf)
    app.state.banner_port = port or conf.server.port
    uvicorn.run(app, host=host or conf.server.host, port=port or conf.server.port, log_level="info")
