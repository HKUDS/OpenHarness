"""能力插件解析：发现、配置自检、按请求/服务级参数装配工具与技能。"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from insightagent.config import InsightConfig
from insightagent.db.catalog import DatabaseCatalog
from insightagent.db.dbengine import QueryEngine
from insightagent.retrieve.embeddings import EmbeddingClient
from openharness.tools.base import BaseTool


class PluginResolutionError(ValueError):
    """插件装配失败（非法名/不在可选集）。"""


@dataclass
class LoadedPlugin:
    name: str
    description: str
    root: Path
    tools: list[BaseTool] = field(default_factory=list)
    skill_dirs: list[Path] = field(default_factory=list)
    mcp_server: str = ""
    ready: bool = True
    reason: str = ""
    scope: str = "system"


def _read_manifest(root: Path) -> dict | None:
    manifest_path = root / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_factory(plugin_root: Path):
    """按文件路径加载插件 tools/factory.py（插件目录名可含连字符，不走常规包导入）。"""
    factory_path = plugin_root / "tools" / "factory.py"
    if not factory_path.exists():
        return None
    mod_name = f"_insightagent_plugin_{plugin_root.name.replace('-', '_')}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, factory_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class PluginDeps:
    """注入插件工厂的共享引擎依赖。"""

    config: InsightConfig
    catalog: DatabaseCatalog
    query_engine: QueryEngine
    embeddings: EmbeddingClient | None = None


def build_deps(config: InsightConfig) -> PluginDeps:
    catalog = DatabaseCatalog(config)
    engine = QueryEngine(catalog, max_rows=config.agent.max_rows, timeout_seconds=config.agent.query_timeout_seconds)
    embeddings = EmbeddingClient(config.embedding) if config.embedding else None
    return PluginDeps(config=config, catalog=catalog, query_engine=engine, embeddings=embeddings)


def _configured_mcp_names(extra_roots: list[Path] | None = None) -> set[str]:
    """已配置的 MCP 服务器名：系统 settings + 用户 home settings（读取失败视为无配置）。"""
    names: set[str] = set()
    try:
        from insightagent import users
        from openharness.config.settings import load_settings

        paths = []
        home = users.system_home()
        if home is not None:
            paths.append(home / "settings.json")
        for root in extra_roots or []:
            settings_candidate = root.parent / "settings.json"
            if settings_candidate not in paths:
                paths.append(settings_candidate)
        for path in paths:
            try:
                names |= set((load_settings(path).mcp_servers or {}).keys())
            except Exception:  # noqa: BLE001
                continue
        if not paths:
            names |= set((load_settings().mcp_servers or {}).keys())
    except Exception:  # noqa: BLE001 - 配置缺失/损坏时按未配置处理
        return names
    return names


def _plugin_ready(
    name: str,
    cfg: InsightConfig,
    mcp_server: str = "",
    extra_roots: list[Path] | None = None,
) -> tuple[bool, str]:
    if name in ("mysql-query", "data-query"):
        if not cfg.databases:
            return False, "未配置 databases（~/.insightagent/config.yaml 或 .env 的 MYSQL_* 变量）"
        return True, ""
    if name == "report-search":
        server = mcp_server or "报表检索"
        mcp_names = _configured_mcp_names(extra_roots) if extra_roots else _configured_mcp_names()
        if server not in mcp_names:
            return False, f"未在 settings.json 的 mcp_servers 中配置「{server}」报表检索服务"
        return True, ""
    # 用户自定义插件（extra_roots 内发现的非内置名）默认就绪
    if extra_roots:
        return True, ""
    return False, f"未知插件: {name}"


def _scan_plugin_root(
    root: Path,
    cfg: InsightConfig,
    scope: str,
    extra_roots: list[Path] | None,
) -> list[LoadedPlugin]:
    found: list[LoadedPlugin] = []
    if not root.exists():
        return found
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        manifest = _read_manifest(path)
        if manifest is None:
            continue
        name = str(manifest.get("name", path.name))
        mcp_server = str((manifest.get("mcp") or {}).get("server") or "")
        ready, reason = _plugin_ready(name, cfg, mcp_server, extra_roots if scope == "user" else None)
        skills_dir = path / str(manifest.get("skills_dir", "skills"))
        found.append(
            LoadedPlugin(
                name=name,
                description=str(manifest.get("description", "")),
                root=path,
                skill_dirs=[skills_dir] if skills_dir.exists() else [],
                mcp_server=mcp_server,
                ready=ready,
                reason=reason,
                scope=scope,
            )
        )
    return found


def discover_plugins(cfg: InsightConfig, extra_roots: list[Path] | None = None) -> list[LoadedPlugin]:
    """扫描系统 plugin_root + 用户 extra_roots 下所有带 plugin.json 的目录（用户同名覆盖系统）。"""
    found = {p.name: p for p in _scan_plugin_root(cfg.plugin_root_path(), cfg, "system", None)}
    for root in extra_roots or []:
        for plugin in _scan_plugin_root(root, cfg, "user", extra_roots):
            found[plugin.name] = plugin
    return sorted(found.values(), key=lambda p: p.name)


def resolve_plugins(
    requested: list[str] | None,
    cfg: InsightConfig,
    deps: PluginDeps | None = None,
    extra_roots: list[Path] | None = None,
) -> tuple[list[LoadedPlugin], list[dict]]:
    """解析本次会话的插件集。

    返回 (已装配插件, skipped 说明)。requested 非法时抛 PluginResolutionError（服务层转 400）。
    extra_roots 指向用户插件目录：用户插件不受系统 default_plugins 白名单限制。
    """
    deps = deps or build_deps(cfg)
    available = {p.name: p for p in discover_plugins(cfg, extra_roots=extra_roots)}
    allowed = set(cfg.agent.default_plugins) | {
        name for name, p in available.items() if p.scope == "user"
    }

    if requested is not None:
        unknown = [name for name in requested if name not in available]
        if unknown:
            raise PluginResolutionError(f"未知插件: {unknown}，可用: {sorted(available)}")
        not_allowed = [name for name in requested if name not in allowed]
        if not_allowed:
            raise PluginResolutionError(f"插件不在服务可选集 default_plugins 内: {not_allowed}，可选: {sorted(allowed)}")
        names = list(dict.fromkeys(requested))
    else:
        names = [name for name in cfg.agent.default_plugins if name in available]

    loaded: list[LoadedPlugin] = []
    skipped: list[dict] = []
    for name in names:
        plugin = available[name]
        if not plugin.ready:
            skipped.append({"plugin": name, "reason": plugin.reason})
            continue
        factory = _load_factory(plugin.root)
        if factory is None or not hasattr(factory, "build_tools"):
            skipped.append({"plugin": name, "reason": "tools/factory.py 缺失或无 build_tools"})
            continue
        try:
            plugin.tools = list(factory.build_tools(deps))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"plugin": name, "reason": f"工具装配失败: {exc}"})
            continue
        loaded.append(plugin)
    return loaded, skipped
