"""能力发现：插件 / MCP 连接器 / 技能 / 模型服务 清单（/api/capabilities 与会话装配共用）。

多用户语义：MCP、模型 profiles、skills、plugins 均分 system（所有用户可用）与
user（该用户 home 内自定义）两层；user 同名覆盖 system。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from insightagent import users
from insightagent.config import InsightConfig
from insightagent.plugin_support import LoadedPlugin, discover_plugins
from openharness.config.settings import load_settings
from openharness.mcp.client import McpClientManager
from openharness.skills.loader import load_skill_registry
from openharness.skills.types import SkillDefinition

# MCP 探测：短超时 + 结果缓存，避免每次能力查询都阻塞在不可达端点上
_MCP_PROBE_TTL = 30.0
_MCP_PROBE_TIMEOUT = 8.0
_mcp_cache: dict[str, dict[str, Any]] = {}
_mcp_lock = asyncio.Lock()


def _system_settings_path() -> Path:
    home = users.system_home()
    if home is not None:
        return home / "settings.json"
    from openharness.config.paths import get_config_file_path

    return get_config_file_path()


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def plugin_skill_dirs(
    cfg: InsightConfig,
    plugins: list[LoadedPlugin] | None = None,
    extra_roots: list[Path] | None = None,
) -> list[str]:
    """所有插件自带技能目录（会话与能力清单共用同一来源）。"""
    if plugins is None:
        plugins = discover_plugins(cfg, extra_roots=extra_roots)
    return [str(d) for p in plugins for d in p.skill_dirs]


def load_skills(
    cfg: InsightConfig,
    plugins: list[LoadedPlugin] | None = None,
    user_home: Path | None = None,
    extra_roots: list[Path] | None = None,
) -> list[SkillDefinition]:
    """与运行时会话一致的技能注册表：内置 + 用户 + 项目 + 插件技能。

    user_home 非空时额外挂载该用户 home/skills 下的自定义技能。
    """
    extra_dirs = plugin_skill_dirs(cfg, plugins, extra_roots=extra_roots)
    if user_home is not None:
        user_skills = user_home / "skills"
        if user_skills.is_dir():
            extra_dirs.append(str(user_skills))
    registry = load_skill_registry(
        Path.cwd(),
        extra_skill_dirs=extra_dirs,
        extra_plugin_roots=[str(cfg.plugin_root_path())] + [str(r) for r in (extra_roots or [])],
    )
    return sorted(registry.list_skills(), key=lambda s: (s.source != "plugin", s.source, s.name))


def _skill_scope(skill: SkillDefinition, user_home: Path | None) -> str:
    if user_home is not None and skill.path:
        try:
            user_skills_root = (user_home / "skills").resolve()
            if user_skills_root == Path(skill.path).resolve() or user_skills_root in Path(skill.path).resolve().parents:
                return "user"
        except OSError:
            pass
    return "system"


def skill_payload(
    cfg: InsightConfig,
    plugins: list[LoadedPlugin] | None = None,
    user_home: Path | None = None,
    extra_roots: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """技能清单（/api/capabilities 用），标注 system/user 归属。"""
    return [
        {
            "name": s.name,
            "description": s.description,
            "source": s.source,
            "path": s.path,
            "scope": _skill_scope(s, user_home),
        }
        for s in load_skills(cfg, plugins, user_home=user_home, extra_roots=extra_roots)
    ]


def resolve_skills(
    names: list[str] | None,
    cfg: InsightConfig,
    plugins: list[LoadedPlugin] | None = None,
    user_home: Path | None = None,
    extra_roots: list[Path] | None = None,
) -> tuple[list[SkillDefinition], list[dict[str, Any]]]:
    """按请求挑选技能；未知名称进入 skipped 说明而不整体失败。"""
    if not names:
        return [], []
    available = {
        s.name: s for s in load_skills(cfg, plugins, user_home=user_home, extra_roots=extra_roots)
    }
    loaded: list[SkillDefinition] = []
    skipped: list[dict[str, Any]] = []
    for name in dict.fromkeys(names):
        skill = available.get(name) or available.get(name.lower()) or available.get(name.title())
        if skill is None:
            skipped.append({"skill": name, "reason": "未注册的技能名"})
        else:
            loaded.append(skill)
    return loaded, skipped


def _merged_mcp_configs(user_home: Path | None) -> dict[str, tuple[Any, str]]:
    """合并系统 + 用户 MCP 配置：{名称: (config 对象, scope)}，用户同名覆盖。"""
    merged: dict[str, tuple[Any, str]] = {}
    try:
        for name, conf in (load_settings(_system_settings_path()).mcp_servers or {}).items():
            merged[name] = (conf, "system")
    except Exception:  # noqa: BLE001
        pass
    if user_home is not None:
        try:
            for name, conf in (load_settings(user_home / "settings.json").mcp_servers or {}).items():
                merged[name] = (conf, "user")
        except Exception:  # noqa: BLE001
            pass
    return merged


def invalidate_mcp_cache(user_home: Path | None = None) -> None:
    """配置变更后清除探测缓存（按 home 维度）。"""
    _mcp_cache.pop(str(user_home) if user_home is not None else "system", None)


async def mcp_server_payload(force: bool = False, user_home: Path | None = None) -> list[dict[str, Any]]:
    """MCP 连接器清单：系统 + 用户配置合并，一次真实连接探测（按 home 缓存 30s）。"""
    cache_key = str(user_home) if user_home is not None else "system"
    async with _mcp_lock:
        now = time.monotonic()
        cached = _mcp_cache.get(cache_key)
        if not force and cached is not None and now - cached["ts"] < _MCP_PROBE_TTL:
            return cached["servers"]
        configs = _merged_mcp_configs(user_home)
        servers: list[dict[str, Any]] = []
        if configs:
            try:
                # 连接与关闭放在独立任务内完成：MCP 客户端的 anyio cancel scope 是任务局部的，
                # 与请求任务混用会污染其取消栈，导致后续回合被误取消。
                servers = await asyncio.wait_for(
                    asyncio.create_task(_probe_servers(configs)),
                    timeout=_MCP_PROBE_TIMEOUT,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 探测失败时返回空清单，不阻断接口
                servers = []
        _mcp_cache[cache_key] = {"ts": now, "servers": servers}
        return servers


async def _probe_servers(configs: dict[str, tuple[Any, str]]) -> list[dict[str, Any]]:
    """一次性连接探测（同一任务内连接并关闭），返回各服务器状态与工具清单（含 scope）。"""
    manager = McpClientManager({name: conf for name, (conf, _scope) in configs.items()})
    try:
        await manager.connect_all()
        return [
            {
                "name": status.name,
                "url": getattr(configs.get(status.name), "url", "") or getattr(configs[status.name][0], "url", "") or "",
                "transport": status.transport,
                "state": status.state,
                "detail": status.detail,
                "ready": status.state == "connected",
                "scope": configs.get(status.name, (None, "system"))[1],
                "tools": [
                    {"name": t.name, "description": t.description}
                    for t in status.tools
                ],
            }
            for status in manager.list_statuses()
        ]
    finally:
        try:
            await manager.close()
        except Exception:  # noqa: BLE001
            pass


def _raw_profile_models(path: Path) -> dict[str, Any] | None:
    """读取指定 settings.json 中 profiles 的原始 default_model（null 与未配置需区分）。"""
    raw = _read_raw(path)
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        return None
    return {
        name: (p.get("default_model") if isinstance(p, dict) else None)
        for name, p in profiles.items()
    }


def _profile_ready(profile: Any, name: str, settings: Any, env_home: Path | None) -> bool:
    """凭证可解析性探测（在指定 env home 下执行，api-key 型 profile 才检查）。"""
    from openharness.auth.storage import load_credential
    from openharness.config.settings import (
        auth_source_uses_api_key,
        credential_storage_provider_name,
        resolve_auth_env_value,
    )

    if not auth_source_uses_api_key(profile.auth_source):
        return True
    with users.openharness_home_sync(env_home):
        slot = credential_storage_provider_name(name, profile)
        ready = (
            load_credential(slot, "api_key", use_keyring=False) is not None
            or load_credential(slot, "api_key") is not None
        )
        if not ready and resolve_auth_env_value(profile.auth_source):
            ready = True
        if not ready and not profile.credential_slot and settings.api_key:
            ready = True  # 顶层 api_key 对无独立槽位的 profile 生效
    return ready


def _profile_signature(profile: Any) -> tuple[Any, ...]:
    """profile 定义的稳定签名，用于判断用户配置是否只是系统副本。"""
    fields = (
        "label",
        "provider",
        "api_format",
        "auth_source",
        "default_model",
        "base_url",
        "credential_slot",
    )
    return tuple(getattr(profile, f, None) for f in fields) + (
        tuple(getattr(profile, "allowed_models", None) or ()),
    )


def profile_payload(cfg: InsightConfig, user_home: Path | None = None) -> dict[str, Any]:
    """模型服务清单：系统内置（仅 default_model 已配置的）+ 用户自定义，标注 scope（不含密钥）。

    用户侧若只是系统 profile 的副本则归为 system；用户同名改写则视为自定义覆盖。
    default 优先取用户 settings 的 active_profile；其次系统侧（cfg.agent.profile → 系统 active）。
    """
    sys_path = _system_settings_path()
    user_path = user_home / "settings.json" if user_home is not None else None

    try:
        sys_settings = load_settings(sys_path)
    except Exception:  # noqa: BLE001
        sys_settings = None
    try:
        user_settings = load_settings(user_path) if user_path is not None else None
    except Exception:  # noqa: BLE001
        user_settings = None

    raw_sys = _raw_profile_models(sys_path)
    raw_user = _raw_profile_models(user_path) if user_path is not None else None

    sys_home = users.system_home()
    entries: dict[str, dict[str, Any]] = {}
    sys_profiles = (sys_settings.profiles if sys_settings is not None else None) or {}
    user_profiles = (user_settings.profiles if user_settings is not None else None) or {}

    def _is_configured(name: str, p: Any, raw_models: dict[str, Any] | None) -> bool:
        if raw_models is None:
            return p.default_model is not None
        raw_model = raw_models.get(name)
        return isinstance(raw_model, str) and bool(raw_model.strip())

    def _add(name: str, p: Any, settings: Any, raw_models: dict[str, Any] | None, scope: str) -> None:
        model = (raw_models.get(name) if raw_models else None) or p.resolved_model or p.default_model or ""
        entries[name] = {
            "name": name,
            "label": p.label,
            "model": model,
            "provider": p.provider,
            "api_format": p.api_format,
            "ready": _profile_ready(p, name, settings, user_home if scope == "user" else sys_home) if settings is not None else False,
            "configured": True,
            "scope": scope,
        }

    # 系统内置：只暴露已配置默认模型的 profile
    if sys_settings is not None:
        for name, p in sys_profiles.items():
            if _is_configured(name, p, raw_sys):
                _add(name, p, sys_settings, raw_sys, "system")
    # 用户自定义：跳过系统副本；同名改写覆盖内置项
    if user_settings is not None:
        for name, p in user_profiles.items():
            sys_p = sys_profiles.get(name)
            if sys_p is not None and _profile_signature(p) == _profile_signature(sys_p):
                continue
            if not _is_configured(name, p, raw_user):
                continue
            _add(name, p, user_settings, raw_user, "user")

    default = ""
    if user_settings is not None and user_path is not None:
        default = str(_read_raw(user_path).get("active_profile") or "")
    if default not in entries:
        default = ""
    if not default:
        candidate = cfg.agent.profile or (sys_settings.active_profile if sys_settings is not None else "")
        default = candidate if candidate in entries else (next(iter(entries), ""))
    return {"default": default, "items": list(entries.values())}
